# `justfile` Commands and `eval` Flags

## `just` Commands

| Command | Action |
|---|---|
| `just setup` | Runs `pnpm install --frozen-lockfile`, installs `nsis`, `llvm`, and `cargo-xwin` for Windows builds, and runs `uv sync --locked` for the agent. |
| `just run` | Runs `pnpm tauri dev`. |
| `just test` | Runs `pnpm test` (`vitest`), `cargo test`, and `pytest` for the agent. |
| `just lint` | Runs `pnpm lint` (`biome check`), `pnpm typecheck` (`tsc --noEmit`), `cargo clippy -- -D warnings`, and `ruff check` for the agent. |
| `just fmt` | Formats TypeScript and CSS with `biome`, Rust with `cargo fmt`, and Python with `ruff format`. |
| `just check` | Runs `just lint` and `just test`. |
| `just searxng` | Starts the `thea-searxng` Docker container on `127.0.0.1:8888`. |
| `just build` | Runs `just build-macos` and `just build-windows` to create the `.dmg` and `-setup.exe` installers. |
| `just release` | Runs `just build`, pushes the version tag, and uploads both installers to `thetaplex/thea`. |
| `just eval [model] [suite] [flags]` | Runs the headless evaluation of `suite` (`research` or `assistant`, default `research`) with `promptfoo` against `model` (default `gemma4:e4b`). It gives the `flags` to `promptfoo eval`. |

## `eval` Flags

`just eval` gives these `promptfoo eval` flags after `[suite]`:

| Flag | Description |
|---|---|
| `--filter-pattern <REGEX>` | Run only the cases whose identifier matches `REGEX`. |
| `--repeat <N>` | Run each case `N` times. |
| `--filter-first-n <N>` | Run only the first `N` cases. |

The case `.json` files take these fields:

| Field | Value |
|---|---|
| `id` | The name of the case. |
| `prompt` | The request of the user. |
| `min_sources` | The number of keys that the drafts must cite. The default is `2`. |
| `persona` | A persona ID in the database of the app. The default is `research-assistant`. |
| `seed_files` | Files to put in the workspace before the turn. |
| `deliverable` | The file that the user asked for: `glob`, and `words` as `[min, max]`. |
| `event` | The calendar event that the user asked for: `start`, `end`, and `location`, as in the `.ics` file. |
