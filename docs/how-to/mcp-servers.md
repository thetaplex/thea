# Connect a `stdio` `MCP` Server

Thea can start `MCP` servers over `stdio` and expose their tools to the agent.

1. Click **Settings** in the left sidebar and select the **MCP** tab.
2. Click **New Server**.
3. Type a server name, such as `filesystem`.
4. Type the executable in the command field, such as `npx` or `uvx`.
5. Type the space-separated arguments, such as `-y @modelcontextprotocol/server-filesystem /tmp`.
6. Check `Run without approval` only if the server is read-only and safe to run without prompts.
7. Click **Save Server**.
8. Click `Discover Tools` on the saved server row to test the connection and list its tools.
