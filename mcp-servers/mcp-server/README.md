# mppose-manga-mcp

MCP server for querying the mp-py-p5-java demo's SQLite database (sessions, screenshots, frames).

## Setup

```bash
cd mcp-server
npm install
```

## Tools

- `list_sessions` - List all pose capture sessions
- `get_session` - Get details of a specific session (includes screenshots and pose stats)
- `list_screenshots` - List all captured screenshots (optionally filtered by session_id)
- `get_screenshot` - Get details of a specific screenshot
- `list_frames` - List frame records for a session
- `get_stats` - Get overall statistics

## Configuration

Set `MPPOSE_DB` environment variable to override DB path (default: `../processing/MPPoseManga/data/mppose_manga.db`)

## Usage with MCP clients

Add to your MCP config:

```json
{
  "mcpServers": {
    "mppose-manga": {
      "command": "node",
      "args": ["C:\\Users\\0501JP\\demos\\mp-py-p5-java\\mcp-server\\index.js"]
    }
  }
}
```
