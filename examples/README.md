# XFINLAB examples

Copy-paste starting points. Get a free API key at https://www.xfinlab.com/intelligence-api.html (free tier: 300 weighted calls/day; first 7 days get a higher AI debate/intel cap). Check `X-RateLimit-Remaining` on any response to see what's left.

| File | What it shows |
|---|---|
| `curl.sh` | Technical analysis, sentiment and events with curl |
| `python_quickstart.py` | Same calls in Python, with rate-limit handling |
| `daily_brief.py` | A small script that prints a daily watchlist brief |
| `mcp_clients.md` | Claude Desktop / Cursor / Claude Code MCP config |
| `agent_tool.py` | Wrap XFINLAB as a tool for any LLM agent (LangChain-style) |

Set your key first: `export XFINLAB_API_KEY=xfl_...`
