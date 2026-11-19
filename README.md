# Thea

Thea is a chat app for your desktop, like `ChatGPT`. It also runs as an agent over your own project folder. Each project has a persona, Personal Assistant or Research Assistant, and a chat without a project is a plain chat. The agent reads and edits files, runs commands, searches the web, and keeps a ledger of sources. It works with local models through `Ollama` or any server that speaks the `OpenAI` protocol, and with hosted providers such as `OpenRouter`. Every write and command waits for your approval.

To use Thea, download the macOS or Windows installer from [Releases](https://github.com/thetaplex/thea/releases) and follow [Install Thea](docs/how-to/install-thea.md). Thea is in beta, and the installers are not code-signed.

The rest of this README is for people who build Thea from source. User documentation is in [`docs/`](docs/README.md).

## Prerequisites

- [Rust](https://rustup.rs)
- [pnpm](https://pnpm.io/installation)
- [uv](https://docs.astral.sh/uv/getting-started/installation/), for the Python agent
- [just](https://github.com/casey/just#installation)
- [Ollama](https://ollama.com) or another model provider
- [Docker](https://docs.docker.com/get-docker/), only for local web search
- [Node.js](https://nodejs.org) 24 or later, only for the `npx` `MCP` presets

```bash
just setup
just run
```

## Commands

| Command | What it does |
|---|---|
| `just run` | Start the desktop app in development mode |
| `just check` | Run linters and test suites (`lint` + `test`) |
| `just build` | Build macOS (`.dmg`) and Windows (`-setup.exe`) installers (`build-macos` + `build-windows`) |
| `just release` | Build the macOS and Windows installers locally and upload them to the GitHub release for the current version. |
| `just searxng` | Start `SearXNG` in Docker on `127.0.0.1:8888` |
| `just eval [model]` | Run the 5-case headless research evaluation against an `Ollama` model (default `gemma4:e4b`) |

## Documentation

- [User documentation](docs/README.md): tutorials, how-to guides, reference, and explanation for the installed app.
- [Developer documentation](docs/dev/README.md): evaluation, installers, architecture, and design documents.
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Known Limitations

- `run_command` asks for approval, but it does not run in a sandbox. Approved commands run with your user permissions.
- The `iframe` for the `HTML` preview can block network connections, but it does not block image loads. A preview page can still send data through the `URL` of an image.
- Thea stores the environment variables for `MCP` servers as plain text in `~/.thea/mcp.json`.
- Builds are not code-signed. `macOS Gatekeeper` and `Windows SmartScreen` warn on first launch.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
