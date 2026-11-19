# Build and Release Desktop Installers

## Build on Your Mac

1. Install dependencies and the Windows cross-compiler:
   ```bash
   just setup
   ```
2. Run the linter and the test suite first:
   ```bash
   just check
   ```
3. Build both the macOS and Windows release bundles:
   ```bash
   just build
   ```
   You can also run `just build-macos` or `just build-windows` separately.
4. Find the installers under `src-tauri/target/`:
   - macOS: `release/bundle/dmg/*.dmg` and `release/bundle/macos/`.
   - Windows: `x86_64-pc-windows-msvc/release/bundle/nsis/*-setup.exe`.

## Publish a Release

Releases live in the public repository `thetaplex/thea`. Your Mac builds both the macOS and Windows installers, and copies the user docs there before it makes the tag.

1. Update the user docs in `docs/` and move the `[Unreleased]` items in `CHANGELOG.md` under the new version. The docs and the notes of the release come from `main` as it is when you run the release.
2. Set the same version in `package.json`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, and `agent/pyproject.toml`.
3. Run `just check` and merge the changes to `main`.
4. On `main`, up to date with `origin` and with no local changes, run:
   ```bash
   just release
   ```
   This command stops if `main` has local changes or is not the same as `origin/main`. Then it builds the `.dmg` and `-setup.exe` installers, copies `docs/` (without `docs/dev/`), `CHANGELOG.md`, and `LICENSE` to `thetaplex/thea`, pushes the tag `v<version>` to this repository, creates the release in `thetaplex/thea` if it does not exist, and uploads both installers.

The docs live in this repository, so they need no separate publish step.

The builds have no code signature. `macOS Gatekeeper` and `Windows SmartScreen` show a warning on the first launch.
