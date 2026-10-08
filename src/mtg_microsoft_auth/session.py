from __future__ import annotations

import base64
import json
import logging
import os
import platform
import shutil
import subprocess

import msal

from .models import AuthConfig, AuthMode

try:
    import msal_extensions

    HAS_MSAL_EXTENSIONS = True
except ImportError:  # pragma: no cover - depends on platform extras
    msal_extensions = None
    HAS_MSAL_EXTENSIONS = False


logger = logging.getLogger(__name__)
CONSUMER_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"


def _get_console_window_handle() -> int | None:
    if "WAM_WINDOW_HANDLE" in os.environ:
        return int(os.environ["WAM_WINDOW_HANDLE"], 0)

    if platform.system() == "Windows":
        return msal.PublicClientApplication.CONSOLE_WINDOW_HANDLE
    return None


class GraphAuthSession:
    def __init__(self, config: AuthConfig, app_factory=None) -> None:
        self.config = config
        self.cache, self._cache_persistence = self._create_cache()
        self._app_factory = app_factory or self._default_app_factory
        self.app = self._app_factory(config, self.cache)

    def _default_app_factory(self, config: AuthConfig, cache):
        return msal.PublicClientApplication(
            client_id=config.client_id,
            authority=f"https://login.microsoftonline.com/{config.tenant_id}",
            token_cache=cache,
            allow_broker=config.allow_broker,
        )

    def _create_cache(self):
        if platform.system() == "Windows" and HAS_MSAL_EXTENSIONS:
            cache_path = self.config.cache_path()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            persistence = msal_extensions.FilePersistenceWithDataProtection(
                str(cache_path)
            )
            return msal_extensions.PersistedTokenCache(persistence), persistence
        return msal.SerializableTokenCache(), None

    def _candidate_accounts(self):
        accounts = self.app.get_accounts() or []
        hint = (self.config.account_hint or "").strip().lower()
        if not hint:
            return accounts

        return [
            account
            for account in accounts
            if str(account.get("username", "")).strip().lower() == hint
        ]

    def _azure_cli_token_matches_config(self, token: str) -> bool:
        """Reject CLI identities or delegated grants that differ from caller intent."""
        try:
            payload = token.split(".")[1]
            claims = json.loads(
                base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )
        except (IndexError, ValueError, TypeError):
            return False
        if not isinstance(claims, dict):
            return False
        if claims.get("aud") not in {
            "https://graph.microsoft.com",
            "00000003-0000-0000-c000-000000000000",
        }:
            return False
        if (
            str(claims.get("azp") or claims.get("appid") or "").lower()
            != self.config.client_id.lower()
        ):
            return False
        tenant = str(claims.get("tid") or "").lower()
        requested_tenant = self.config.tenant_id.lower()
        if requested_tenant == "consumers" and tenant != CONSUMER_TENANT_ID:
            return False
        if requested_tenant == "organizations" and (
            not tenant or tenant == CONSUMER_TENANT_ID
        ):
            return False
        if (
            requested_tenant not in {"common", "organizations", "consumers"}
            and tenant != requested_tenant
        ):
            return False
        granted = {scope.casefold() for scope in str(claims.get("scp") or "").split()}
        requested = {
            scope.rsplit("/", 1)[-1].casefold() for scope in self.config.scopes
        }
        if not requested or requested != granted:
            return False
        if self.config.account_hint:
            identity = (
                claims.get("preferred_username")
                or claims.get("upn")
                or claims.get("unique_name")
                or ""
            )
            if (
                str(identity).strip().casefold()
                != self.config.account_hint.strip().casefold()
            ):
                return False
        return True

    def _try_azure_cli_token(self) -> str | None:
        if self.config.mode != AuthMode.AZURE_CLI:
            return None
        az_executable = shutil.which("az.cmd") or shutil.which("az")
        if not az_executable:
            return None
        scopes = [
            (
                scope
                if scope.startswith("https://graph.microsoft.com/")
                else f"https://graph.microsoft.com/{scope}"
            )
            for scope in self.config.scopes
        ]
        command = [az_executable, "account", "get-access-token", "--scope", *scopes]
        if self.config.tenant_id not in {"common", "organizations", "consumers"}:
            command.extend(["--tenant", self.config.tenant_id])
        command.extend(["--query", "accessToken", "-o", "tsv"])
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
        except Exception:
            return None
        token = result.stdout.strip()
        if token and not self._azure_cli_token_matches_config(token):
            raise RuntimeError(
                "Azure CLI token does not match configured Graph identity or scopes"
            )
        return token or None

    def _try_wam_token(self) -> str | None:
        if self.config.mode not in {AuthMode.AUTO, AuthMode.WAM}:
            return None
        accounts = self._candidate_accounts()
        for account in accounts:
            result = self.app.acquire_token_silent_with_error(
                self.config.scopes,
                account=account,
                force_refresh=False,
            )
            if result and "access_token" in result:
                return result["access_token"]
        try:
            interactive_kwargs = {
                "scopes": self.config.scopes,
                "parent_window_handle": _get_console_window_handle(),
                "timeout": 300,
            }
            if self.config.account_hint:
                interactive_kwargs["login_hint"] = self.config.account_hint
            elif not accounts:
                interactive_kwargs["prompt"] = "select_account"
            result = self.app.acquire_token_interactive(**interactive_kwargs)
        except Exception as exc:
            logger.warning("WAM auth unavailable: %s", exc)
            return None
        return result.get("access_token")

    def _try_interactive_token(self) -> str | None:
        if self.config.mode not in {AuthMode.AUTO, AuthMode.INTERACTIVE}:
            return None
        accounts = self._candidate_accounts()
        for account in accounts:
            result = self.app.acquire_token_silent(self.config.scopes, account=account)
            if result and "access_token" in result:
                return result["access_token"]
        try:
            interactive_kwargs = {"scopes": self.config.scopes, "timeout": 300}
            if self.config.allow_broker:
                interactive_kwargs["parent_window_handle"] = (
                    _get_console_window_handle()
                )
            if self.config.account_hint:
                interactive_kwargs["login_hint"] = self.config.account_hint
            result = self.app.acquire_token_interactive(**interactive_kwargs)
        except Exception as exc:
            logger.warning("Interactive auth unavailable: %s", exc)
            return None
        return result.get("access_token")

    def _try_device_code_token(self) -> str | None:
        if self.config.mode not in {AuthMode.AUTO, AuthMode.DEVICE_CODE}:
            return None
        flow = self.app.initiate_device_flow(scopes=self.config.scopes)
        if "user_code" not in flow:
            error = flow.get("error")
            description = flow.get("error_description")
            if error or description:
                logger.warning(
                    "Device-code auth unavailable: %s %s", error, description
                )
            return None
        print(flow["message"], flush=True)
        result = self.app.acquire_token_by_device_flow(flow)
        if result and "access_token" not in result:
            logger.warning(
                "Device-code auth failed: %s %s",
                result.get("error"),
                result.get("error_description"),
            )
        return result.get("access_token")

    def acquire_token(self) -> str:
        token = self._try_azure_cli_token()
        if token:
            return token
        token = self._try_wam_token()
        if token:
            return token
        token = self._try_interactive_token()
        if token:
            return token
        token = self._try_device_code_token()
        if token:
            return token
        raise RuntimeError(
            "Unable to acquire Microsoft Graph access token. "
            "Tried: azure-cli, WAM broker, interactive browser, device code."
        )
