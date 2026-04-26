# MTG Microsoft Auth

Windows-first Microsoft Graph auth helpers for Midtown dev toys.

## Features

- `msal` public client authentication
- Windows broker runtime for WAM-first sign-in
- Windows DPAPI-backed token cache via `msal_extensions` when available
- WAM/broker-first login flow on Windows
- Interactive browser and device-code fallbacks
- Thin authenticated Graph client with retry and pagination helpers

On Windows, the token cache is persisted under `%USERPROFILE%\.config\<cache-namespace>\token_cache.bin`. The Midtown toys now default to a shared cache namespace, `mtg-shared-microsoft-auth`, so WAM sign-in state can be reused across `todo`, `mail-triage`, `file-finder`, and other Graph-backed toys instead of prompting per toy.

The recommended default auth mode for the toys is `wam`. In the shared auth library, `wam` now means broker-first only; browser and device-code fallbacks are reserved for `auto`, `interactive`, or `device-code` modes so a WAM-first tool does not unexpectedly fan out into multiple interactive prompts.

## Install

```powershell
python -m pip install -e .[dev]
```

## Usage

```python
from mtg_microsoft_auth import AuthConfig, AuthMode, GraphAuthSession, GraphClient

config = AuthConfig(
    client_id="00000000-0000-0000-0000-000000000000",
    tenant_id="11111111-1111-1111-1111-111111111111",
    scopes=["Tasks.Read", "Tasks.ReadWrite"],
    mode=AuthMode.AUTO,
    cache_namespace="todo-cli",
)

session = GraphAuthSession(config)
client = GraphClient(session)
payload = client.get("/me")
```

## Scope Bundles

The shared auth library leaves scope choice with the consuming toy. These are the standard delegated bundles we use across the Midtown toy chest:

- Todo default scope: `["Tasks.Read"]`
- Todo read-write: `["Tasks.Read", "Tasks.ReadWrite"]`
- Own-mail triage + mutate: `["Mail.ReadWrite"]`
- Own-mail triage + send: `["Mail.ReadWrite", "Mail.Send"]`
- Own + shared mail triage + send: `["Mail.ReadWrite", "Mail.Send", "Mail.ReadWrite.Shared", "Mail.Send.Shared"]`

Example for a write-capable mail consumer:

```python
config = AuthConfig(
    client_id="00000000-0000-0000-0000-000000000000",
    tenant_id="11111111-1111-1111-1111-111111111111",
    scopes=["Mail.ReadWrite", "Mail.Send"],
    mode=AuthMode.WAM,
    cache_namespace="mail-agent",
)
```

Example for a shared-mail-capable consumer:

```python
config = AuthConfig(
    client_id="00000000-0000-0000-0000-000000000000",
    tenant_id="11111111-1111-1111-1111-111111111111",
    scopes=[
        "Mail.ReadWrite",
        "Mail.Send",
        "Mail.ReadWrite.Shared",
        "Mail.Send.Shared",
    ],
    mode=AuthMode.WAM,
    cache_namespace="shared-mail-agent",
)
```

## Shared Cache

The recommended default cache namespace for Midtown toys is:

```text
mtg-shared-microsoft-auth
```

Override it only when you intentionally want isolation:

```powershell
$env:MTG_AUTH_CACHE_NAMESPACE='my-isolated-cache'
```

If your Windows broker cache contains multiple Entra accounts, set a shared account hint so silent token reuse prefers the right one before prompting:

```powershell
$env:MTG_AUTH_ACCOUNT_HINT='thomas@midtowntg.com'
```
