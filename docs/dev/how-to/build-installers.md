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

The `Release` workflow in GitHub Actions builds the macOS installer on a macOS runner and the Windows installer on a Windows runner, then publishes them.

1. Update the user docs in `docs/` and move the `[Unreleased]` items in `CHANGELOG.md` under the new version. The release notes come from that section.
2. Set the same version in `package.json`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, and `agent/pyproject.toml`.
3. Run `just check` and merge the changes to `main`.
4. On `main`, up to date with `origin` and with no local changes, run:
   ```bash
   just release
   ```
   This command stops if `main` has local changes or is not the same as `origin/main`. Then it pushes the tag `v<version>`. The tag starts the `Release` workflow, which builds the `.dmg` and `-setup.exe` installers, creates the release if it does not exist, and uploads both installers.

To build the installers without publishing, run the `Release` workflow by hand from the Actions tab. The installers are attached to the run as artifacts.

The builds have no code signature. `macOS Gatekeeper` and `Windows SmartScreen` show a warning on the first launch.
