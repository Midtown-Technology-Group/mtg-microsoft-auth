# MTG Microsoft Auth

This Python 3.10+ library supplies shared Microsoft Graph authentication for MTG operator toys. Read [README.md](README.md) for modes, scope bundles, shared-cache configuration, and account selection. `src/mtg_microsoft_auth` owns the library and `mtg-auth` CLI; pytest targets `tests/` through `pyproject.toml`.

Install development dependencies in an isolated environment with `python -m pip install -e .[dev]`. Run `python -m pytest` for affected behavior. Use fake MSAL/broker/cache/HTTP boundaries when testing token reuse, retries, pagination, and error handling; do not require a real Graph tenant or prompt for live sign-in merely to test source.

Preserve Windows WAM/broker-first behavior and DPAPI-backed persisted cache protection. `wam` mode is broker-first only: browser and device-code fallbacks belong to `auto`, `interactive`, and `device-code`, preventing unexpected prompt cascades. Non-Windows installations use the separately declared MSAL dependency path.

Scope selection belongs to consuming tools; authentication success does not authorize mail, task, or file mutations. Do not silently widen scopes, switch accounts/tenants, or change consent requirements. Preserve the shared `mtg-shared-microsoft-auth` cache namespace default and intentional isolation overrides. Account hints should select the intended account before interactive prompting, not expose account details in diagnostics.

Never print tokens, decrypted cache contents, authorization headers, or sensitive Graph payloads. Do not delete or migrate an operator's shared cache as a troubleshooting shortcut. Changes to authentication defaults affect multiple toys: document compatibility, platform behavior, account selection, and any required operator action. Report unit-test evidence separately from explicitly authorized live authentication checks.
