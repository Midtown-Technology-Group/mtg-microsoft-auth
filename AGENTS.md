# MTG Microsoft Auth

This Python 3.10+ library supplies shared Microsoft Graph authentication for MTG operator toys. Read [README.md](README.md) for modes, scope bundles, shared-cache configuration, and account selection. `src/mtg_microsoft_auth` owns the library and `mtg-auth` CLI; pytest targets `tests/` through `pyproject.toml`.

Install development dependencies in an isolated environment with `python -m pip install -e .[dev]`. Run `python -m pytest` for affected behavior. Use fake MSAL/broker/cache/HTTP boundaries when testing token reuse, retries, pagination, and error handling; do not require a real Graph tenant or prompt for live sign-in merely to test source.

Preserve Windows WAM/broker-first behavior and DPAPI-backed persisted cache protection. `wam` mode is broker-first only: browser and device-code fallbacks belong to `auto`, `interactive`, and `device-code`, preventing unexpected prompt cascades. Non-Windows installations use the separately declared MSAL dependency path.

Scope selection belongs to consuming tools; authentication success does not authorize mail, task, or file mutations. Do not silently widen scopes, switch accounts/tenants, or change consent requirements. Preserve the shared `mtg-shared-microsoft-auth` cache namespace default and intentional isolation overrides. Account hints should select the intended account before interactive prompting, not expose account details in diagnostics.

Never print tokens, decrypted cache contents, authorization headers, or sensitive Graph payloads. Do not delete or migrate an operator's shared cache as a troubleshooting shortcut. Changes to authentication defaults affect multiple toys: document compatibility, platform behavior, account selection, and any required operator action. Report unit-test evidence separately from explicitly authorized live authentication checks.

## Secret gate before publication

Before publishing the current PR branch, commit the complete candidate and run
`python3 -I scripts/secret_gate.py --base refs/remotes/origin/main`.
On native Windows PowerShell, run
`& "$env:MTG_SECRET_GATE_PYTHON" -I scripts/secret_gate.py --base refs/remotes/origin/main`.
Require the gate's exit code 0 (`$LASTEXITCODE` in PowerShell);
missing tooling/authentication, scan errors and skipped scans block publication.
Then run the existing repository gates. Repeat after changing outgoing commits.
Push exactly the scanned HEAD. This PR scan covers the current branch against its
fetched intended base; other refs, multi-ref pushes and rewritten history require
`--pre-push` with Git's complete ref-update stream. Stop if any pushed ref is
uncovered. See [secret scanning](SECRET-SCANNING.md) for base selection, new branches,
pre-push input and prerequisites. Preserve GitGuardian App, CI and Gitleaks checks.

For a non-default PR target, fetch its destination and pass that exact ref to
`--base`; the remote default is not a substitute for a release/maintenance base.

The secret gate requires Python 3.11+ and approved ggshield >=1.56.1,<2.

Explicit bases require fully qualified refs such as `refs/remotes/origin/main`
or full commit SHAs; ambiguous short names block with exit 20.
