from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

import msal

from .models import AuthConfig, AuthMode

try:
    import msal_extensions

    HAS_MSAL_EXTENSIONS = True
except ImportError:  # pragma: no cover - depends on platform extras
    msal_extensions = None
    HAS_MSAL_EXTENSIONS = False


logger = logging.getLogger(__name__)


def _get_console_window_handle() -> int | None:
    if "WAM_WINDOW_HANDLE" in os.environ:
        return int(os.environ["WAM_WINDOW_HANDLE"], 0)

    if platform.system() == "Windows":
        try:
            import ctypes

            return ctypes.windll.kernel32.GetConsoleWindow()
        except Exception:
            return None
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
            persistence = msal_extensions.FilePersistenceWithDataProtection(str(cache_path))
            return msal_extensions.PersistedTokenCache(persistence), persistence
        return msal.SerializableTokenCache(), None

    def _try_azure_cli_token(self) -> str | None:
        if self.config.mode != AuthMode.AZURE_CLI:
            return None
        az_executable = shutil.which("az.cmd") or shutil.which("az")
        if not az_executable:
            return None
        try:
            result = subprocess.run(
                [
                    az_executable,
                    "account",
                    "get-access-token",
                    "--resource-type",
                    "ms-graph",
                    "--query",
                    "accessToken",
                    "-o",
                    "tsv",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception:
            return None
        token = result.stdout.strip()
        return token or None

    def _try_wam_token(self) -> str | None:
        if self.config.mode not in {AuthMode.AUTO, AuthMode.WAM}:
            return None
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent_with_error(
                self.config.scopes,
                account=accounts[0],
                force_refresh=False,
            )
            if result and "access_token" in result:
                return result["access_token"]
        try:
            result = self.app.acquire_token_interactive(
                scopes=self.config.scopes,
                parent_window_handle=_get_console_window_handle(),
                timeout=300,
                prompt="select_account" if not accounts else None,
            )
        except Exception as exc:
            logger.warning("WAM auth unavailable: %s", exc)
            return None
        return result.get("access_token")

    def _try_interactive_token(self) -> str | None:
        if self.config.mode not in {AuthMode.AUTO, AuthMode.INTERACTIVE, AuthMode.WAM}:
            return None
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(self.config.scopes, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]
        try:
            result = self.app.acquire_token_interactive(scopes=self.config.scopes, timeout=300)
        except Exception as exc:
            logger.warning("Interactive auth unavailable: %s", exc)
            return None
        return result.get("access_token")

    def _try_device_code_token(self) -> str | None:
        if self.config.mode not in {
            AuthMode.AUTO,
            AuthMode.INTERACTIVE,
            AuthMode.WAM,
            AuthMode.DEVICE_CODE,
        }:
            return None
        flow = self.app.initiate_device_flow(scopes=self.config.scopes)
        if "user_code" not in flow:
            return None
        print(flow["message"])
        result = self.app.acquire_token_by_device_flow(flow)
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
