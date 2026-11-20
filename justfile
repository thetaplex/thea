default:
    @just --list

# Install JS deps and Windows cross-compilation tools
setup:
    pnpm install --frozen-lockfile
    brew list nsis >/dev/null 2>&1 || brew install nsis
    brew list llvm >/dev/null 2>&1 || brew install llvm
    brew list lld >/dev/null 2>&1 || brew install lld
    rustup target add x86_64-pc-windows-msvc
    PATH="$HOME/.cargo/bin:$PATH" command -v cargo-xwin >/dev/null 2>&1 || cargo install --locked cargo-xwin
    uv sync --project agent --locked

test:
    pnpm test
    cargo test --manifest-path src-tauri/Cargo.toml
    uv run --project agent pytest agent/tests

lint:
    pnpm lint
    pnpm typecheck
    cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
    uv run --project agent ruff check agent evals/promptfoo

fmt:
    pnpm fmt
    cargo fmt --manifest-path src-tauri/Cargo.toml
    uv run --project agent ruff format agent evals/promptfoo

check: lint test

run:
    pnpm tauri dev

# Start the local SearXNG search engine used by web_search (needs Docker)
searxng:
    docker rm -f thea-searxng >/dev/null 2>&1 || true
    docker run -d --name thea-searxng --restart unless-stopped -p 127.0.0.1:8888:8080 -e SEARXNG_SECRET=$(openssl rand -hex 32) -v "$PWD/docker/searxng:/etc/searxng" searxng/searxng:latest

# Build the bundled Python runtime for a target triple into agent/dist/python
bundle-agent triple:
    #!/usr/bin/env bash
    set -euo pipefail
    unset VIRTUAL_ENV
    tag=20261026
    case "{{triple}}" in
        aarch64-apple-darwin) sha=8392b6ea51d94391befb2c31ebe75463f045d0b69dfcf5e1bb3234e1f5fa3405; site=lib/python3.13/site-packages ;;
        x86_64-pc-windows-msvc) sha=7369f7a35f261222a6ac8b3a87c1c88eeebee8af945d85346202591a64038dd3; site=Lib/site-packages ;;
        *) echo "unsupported triple: {{triple}}" >&2; exit 1 ;;
    esac
    archive="cpython-3.13.18+$tag-{{triple}}-install_only_stripped.tar.gz"
    dist=agent/dist
    mkdir -p "$dist/cache"
    if [ ! -f "$dist/cache/$archive" ]; then
        curl -fSL "https://github.com/astral-sh/python-build-standalone/releases/download/$tag/${archive//+/%2B}" -o "$dist/cache/$archive.part"
        mv "$dist/cache/$archive.part" "$dist/cache/$archive"
    fi
    echo "$sha  $dist/cache/$archive" | shasum -a 256 -c - || { rm -f "$dist/cache/$archive"; exit 1; }
    rm -rf "$dist/python" "$dist/wheel"
    tar -xzf "$dist/cache/$archive" -C "$dist"
    rm -rf "$dist/python/$site"/pip "$dist/python/$site"/pip-*  # the runtime never installs packages
    # Tauri copies symlinks as files, so keep one real interpreter: bin/python3, what sidecar.rs runs
    if [ -d "$dist/python/bin" ]; then
        mv "$dist/python/bin/python3.13" "$dist/python/python3"
        rm -rf "$dist/python/bin"
        mkdir "$dist/python/bin"
        mv "$dist/python/python3" "$dist/python/bin/python3"
    fi
    uv export --project agent --no-dev --frozen --no-emit-project -o "$dist/req.txt" >/dev/null
    uv build --project agent --wheel -o "$dist/wheel"
    for r in "-r $dist/req.txt" "--no-deps $dist/wheel/*.whl"; do
        uv pip install --python-platform {{triple}} --python-version 3.13 --only-binary :all: --target "$dist/python/$site" $r
    done
    # Precompile so the app never writes __pycache__ into its own (later signed) bundle
    uv run --no-project --python 3.13 python -m compileall -q -j0 --invalidation-mode unchecked-hash "$dist/python/$(dirname "$site")"

build: build-macos build-windows

build-macos: (bundle-agent "aarch64-apple-darwin")
    CI=true pnpm tauri build
    # A bundle without a full signature opens as "damaged" once it is downloaded
    codesign --verify --deep --strict src-tauri/target/release/bundle/macos/Thea.app

build-windows: (bundle-agent "x86_64-pc-windows-msvc")
    #!/usr/bin/env bash
    set -euo pipefail
    brew list lld >/dev/null 2>&1 || brew install lld
    cache_dir="src-tauri/target/.tauri-cache"
    mkdir -p "$cache_dir"
    [ -f "$cache_dir/nsis_tauri_utils.dll" ] || curl -4 -fSL "https://github.com/tauri-apps/nsis-tauri-utils/releases/download/nsis_tauri_utils-v0.5.3/nsis_tauri_utils.dll" -o "$cache_dir/nsis_tauri_utils.dll"
    rm -rf "$HOME/Library/Caches/tauri/NSIS"
    python3 -m http.server 18923 --bind 127.0.0.1 --directory "$cache_dir" >/dev/null 2>&1 &
    server_pid=$!
    trap 'kill "$server_pid" 2>/dev/null || true' EXIT
    TAURI_BUNDLER_TOOLS_GITHUB_MIRROR_TEMPLATE="http://127.0.0.1:18923/<asset>" \
    PATH="$HOME/.cargo/bin:$(brew --prefix llvm)/bin:$(brew --prefix lld)/bin:$PATH" \
        pnpm tauri build --runner cargo-xwin --target x86_64-pc-windows-msvc --bundles nsis

# Run an eval suite (research or assistant) with promptfoo against a local Ollama model (needs Ollama running).
# Extra flags go to promptfoo, e.g. `just eval gemma4:e4b research --filter-pattern reflexion`.
[positional-arguments]
eval model="gemma4:e4b" suite="research" *flags:
    uv sync --project agent --locked --quiet
    shift 2; THEA_EVAL_MODEL="{{model}}" PROMPTFOO_PYTHON="{{justfile_directory()}}/agent/.venv/bin/python" PROMPTFOO_DISABLE_TELEMETRY=1 \
        npx -y promptfoo@0.125.1 eval -c evals/promptfoo/promptfooconfig.yaml --no-cache -j 1 \
        --filter-metadata suite={{suite}} -o "evals/results/promptfoo/{{suite}}-$(echo '{{model}}' | tr -c 'A-Za-z0-9.\n-' '-')-$(date +%F).json" "$@"

# Check that this is main, up to date with origin, with no local changes: the
# release tags HEAD, so a branch or an unmerged change would be released.
_on-main:
    #!/usr/bin/env bash
    set -euo pipefail
    git fetch -q origin main
    [ "$(git branch --show-current)" = main ] || { echo "release from main" >&2; exit 1; }
    git diff --quiet HEAD || { echo "commit or stash local changes first" >&2; exit 1; }
    [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "main is not origin/main: pull or push first" >&2; exit 1; }

# Tag main as v<version>; the Release workflow builds both installers and publishes the release.
release: _on-main
    tag=v$(node -p "require('./package.json').version"); \
    git tag "$tag" && git push origin "$tag" && \
    echo "Release workflow: https://github.com/thetaplex/thea/actions/workflows/release.yml"
