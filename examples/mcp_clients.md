# Use XFINLAB from MCP clients

Endpoint: `https://api.xfinlab.com/api/mcp` (Streamable HTTP). Header: `X-API-Key`.

## Claude Desktop (via mcp-remote)
```json
{
  "mcpServers": {
    "xfinlab": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://api.xfinlab.com/api/mcp", "--header", "X-API-Key:${XFINLAB_API_KEY}"],
      "env": { "XFINLAB_API_KEY": "xfl_..." }
    }
  }
}
```

## Cursor (`~/.cursor/mcp.json`)
```json
{ "mcpServers": { "xfinlab": { "url": "https://api.xfinlab.com/api/mcp", "headers": { "X-API-Key": "xfl_..." } } } }
```

## Claude Code
```
claude mcp add --transport http xfinlab https://api.xfinlab.com/api/mcp --header "X-API-Key: xfl_..."
```

Tools: `get_market_events`, `get_sentiment`, `get_technical_analysis`, `get_intelligence_feed`, `get_global_market_map`.
Try asking: "What is the technical outlook for NVDA and how is sentiment?"
