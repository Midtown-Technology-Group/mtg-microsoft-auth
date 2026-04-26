# MTG Microsoft Auth

Windows-first Microsoft Graph auth helpers for Midtown dev toys.

## Features

- `msal` public client authentication
- Windows broker runtime for WAM-first sign-in
- Windows DPAPI-backed token cache via `msal_extensions` when available
- WAM/broker-first login flow on Windows
- Interactive browser and device-code fallbacks
- Thin authenticated Graph client with retry and pagination helpers

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
