# Set Up Local Web Search with `SearXNG`

The `web_search` tool queries a local `SearXNG` container first. If `SearXNG` is not running, Thea falls back to `Tavily` in keyless mode and then to `DuckDuckGo`.

1. Start Docker on your computer.
2. Run this command in the repository folder, which holds the `SearXNG` configuration:
   ```bash
   docker run -d --name thea-searxng --restart unless-stopped \
     -p 127.0.0.1:8888:8080 -e SEARXNG_SECRET=$(openssl rand -hex 32) \
     -v "$PWD/docker/searxng:/etc/searxng" searxng/searxng:latest
   ```
   This command starts the `searxng/searxng:latest` container on `127.0.0.1:8888` with the configuration in `docker/searxng/settings.yml`.
3. To change the `SearXNG` address, open **Settings**, go to the **Models** tab, and edit `SearXNG URL`.
4. Leave `SearXNG URL` blank if you want `web_search` to skip `SearXNG` and use the fallback search engines directly.
5. Click **Save Settings**.
