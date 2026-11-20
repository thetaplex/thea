# 3. Keep API Keys in a Credentials File

Date: 2026-11-20

## Status

Accepted.

## Context

Thea kept provider `API` keys in the operating system keychain, with one item for each provider, under the service name `app.thetaplex.thea`.

On macOS, the keychain gives access to an item by the code signature of the app. Thea is signed ad hoc (`"signingIdentity": "-"`), so each build has a new signature:

- Each dev build asks for the login password, once for each item. Because Thea read the keys again on each settings or provider lookup, it asked many times, and again each time the model changed.
- Each release asks again after an update.

A Developer ID certificate would give Thea a stable signature and stop the prompts. Thea does not have that certificate.

We had three options:

- **A. Keep the keychain and reduce the prompts.** Put all keys in one item, cache it in memory, and write only changed keys. The prompt still comes after each build and each update.
- **B. A credentials file.** Keep the keys in `~/.thea/credentials`, an `INI` file like `~/.aws/credentials`, readable only by the user.
- **C. Sign Thea with a Developer ID.** This fixes the prompts for releases, but not for dev builds, and it costs a yearly fee.

## Decision

We use option B. Each provider has a `[provider-id]` section with an `api_key = ...` line. Thea creates the file with mode `600` and writes it through a temporary file and a rename. Users can edit the file. Thea changes only `api_key` lines, keeps all other lines, and does not write the file when a key is unchanged.

The agent's file tools deny `**/.thea/credentials`, as they deny `**/.env*`.

Thea reads the file once, when the app starts, and keeps the keys in memory. When a key changes in Settings, Thea writes the file and then reloads the keys from what it wrote. A change made by hand while Thea runs takes effect at the next start, and a later save from Settings keeps it.

The code is the same on macOS, Windows, and Linux. On Windows, the file gets the access rules of the user profile folder, which only the user and administrators can open.

Thea does not move keys from the keychain. Thea had no users when it made this change. We removed the `keyring` crate.

## Consequences

- Thea shows no keychain prompts.
- The keys are not encrypted. Backups and file sync tools copy them as plain text. This is the same trade-off that the `AWS` CLI, the GitHub CLI, and Docker make.
- An approved `run_command` call can read the file. The approval shows the command before it runs.
- Users can see, change, back up, and remove their keys with any text editor.
- If Thea gets a Developer ID certificate later, the keychain is an option again. That change needs a new ADR that supersedes this one.
