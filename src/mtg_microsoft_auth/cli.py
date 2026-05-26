from __future__ import annotations

import argparse
import logging
import os
import sys

from .client import GraphClient
from .models import AuthConfig, AuthMode
from .session import GraphAuthSession

DEFAULT_CLIENT_ID = "e02be6f7-063a-46a6-b2cc-109d5f51055c"
DEFAULT_TENANT_ID = "a3599b15-c39c-4b41-a219-7e24dd5b5190"
DEFAULT_CACHE_NAMESPACE = "mtg-shared-microsoft-auth"
DEFAULT_SCOPES = [
    "User.Read",
    "Calendars.Read",
    "Mail.Read",
    "Mail.ReadBasic",
    "Chat.Read",
    "Files.Read",
    "Tasks.Read",
]


def _scope_list(raw: str | None) -> list[str]:
    if not raw:
        return DEFAULT_SCOPES.copy()
    return [scope.strip() for scope in raw.split(",") if scope.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mtg-auth",
        description="Shared Microsoft Graph auth helpers for Midtown tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser(
        "login",
        help="Sign in once and warm the shared Microsoft Graph token cache.",
    )
    login.add_argument(
        "--client-id",
        default=os.environ.get("MTG_AUTH_CLIENT_ID", DEFAULT_CLIENT_ID),
        help="Entra public client application ID.",
    )
    login.add_argument(
        "--tenant-id",
        default=os.environ.get("MTG_AUTH_TENANT_ID", DEFAULT_TENANT_ID),
        help="Entra tenant ID or common/organizations/consumers.",
    )
    login.add_argument(
        "--cache-namespace",
        default=os.environ.get("MTG_AUTH_CACHE_NAMESPACE", DEFAULT_CACHE_NAMESPACE),
        help="Shared token-cache namespace.",
    )
    login.add_argument(
        "--account",
        default=os.environ.get("MTG_AUTH_ACCOUNT_HINT"),
        help="Preferred signed-in account UPN.",
    )
    login.add_argument(
        "--mode",
        choices=[mode.value for mode in AuthMode],
        default=os.environ.get("MTG_AUTH_MODE", AuthMode.AUTO.value),
        help="Authentication mode.",
    )
    login.add_argument(
        "--scopes",
        default=os.environ.get("MTG_AUTH_SCOPES"),
        help="Comma-separated delegated scopes. Defaults to the Midtown toy read bundle.",
    )
    login.set_defaults(func=_login)
    return parser


def _login(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    scopes = _scope_list(args.scopes)
    config = AuthConfig(
        client_id=args.client_id,
        tenant_id=args.tenant_id,
        scopes=scopes,
        mode=AuthMode(args.mode),
        cache_namespace=args.cache_namespace,
        account_hint=args.account,
        allow_broker=True,
    )
    session = GraphAuthSession(config)
    client = GraphClient(session)
    profile = client.get("/me", params={"$select": "displayName,userPrincipalName"})
    upn = profile.get("userPrincipalName") or args.account or "signed-in account"
    print(f"Authenticated {upn}")
    print(f"Cache namespace: {args.cache_namespace}")
    print("Scopes: " + ", ".join(scopes))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
