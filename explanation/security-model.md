# Security Boundaries and Known Limits

This guide explains the security boundaries of Thea and their limits.

- **Sandbox for paths in the workspace**: for each path, Thea finds the canonical form and checks the ancestors. This check stops `..` segments and symlinks from escaping the project root.
- **Secret file exclusion**: `list_dir`, `read_file`, and `search` block any file with a name that starts with `.env`. This rule keeps your secrets out of model prompts.
- **`SSRF` protection in `fetch_url`**: `fetch_url` allows only `http` and `https`, and blocks `localhost`, `.local`, and `.internal`. It resolves `DNS` before every hop (up to `5` redirects) and rejects loopback, private, link-local, carrier-grade `NAT`, and unspecified `IP` addresses.
- **Keychain storage**: provider `API` keys live in the operating system keychain (`macOS Keychain`, `Windows Credential Manager`, or Linux `Secret Service`). When it loads `~/.thea/providers.json` or `~/.thea/settings.json`, it moves any keys in plain text into the keychain and blanks them on disk.
- **Approval gate**: `write_file`, `edit_file`, `add_source`, `run_command`, and non-auto-approved `MCP` tools pause. They wait until the user clicks `Approve Once`, `Always Allow for Project`, or `Reject`.
- **Shell commands are not sandboxed**: `run_command` never offers `Always Allow for Project`, and it asks for approval on every call. Once approved, the command runs in your configured shell (`zsh` or `pwsh`) with your user permissions.
- **Preview `iframe` policy**: the pane for Artifacts shows a preview of the HTML in `<iframe sandbox="allow-scripts">` with `Content-Security-Policy: connect-src 'none'; form-action 'none'`. This blocks `fetch`, `XMLHttpRequest`, and `WebSocket` calls, but an `<img>` tag in the HTML can still load an external image `URL`.
