# mppdp5 MCP Servers

Two MCP (Model Context Protocol) servers for integrating with mppdp5.

## 1. Sender MCP (`mcp/sender/`)

Controls the extraction processes (contour, pose, segment, pipeline) via MCP tools.

### Tools

| Tool | Description |
|------|-------------|
| `list_cameras` | List available camera devices |
| `start_contour` | Start contour extraction |
| `start_pose` | Start pose estimation |
| `start_segment` | Start segmentation |
| `start_pipeline` | Start full pipeline (all three) |
| `stop_process` | Stop running process(es) |
| `get_status` | Get process status |
| `get_logs` | Get recent logs |

### Usage

```bash
# Install dependencies
pip install mcp

# Run server
cd mcp/sender
python server.py
```

### Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `MPPDP5_ROOT` | Auto-detected | mppdp5 root directory |
| `MPPDP5_PYTHON` | `sys.executable` | Python interpreter to use |

---

## 2. Query MCP (`mcp/server/`)

Queries the SQLite database created by the Processing renderer.

### Tools

| Tool | Description |
|------|-------------|
| `list_sessions` | List all sessions |
| `get_session` | Get session details |
| `list_screenshots` | List screenshots |
| `get_screenshot` | Get screenshot details |
| `list_frames` | List frame records |
| `list_poses` | List pose keypoints |
| `get_stats` | Get overall statistics |

### Usage

```bash
# Install dependencies
cd mcp/server
npm install

# Run server
npm start
# Or directly:
node index.js
```

### Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `MPPDP5_DB` | `demos/processing-renderer/data/mppose_manga.db` | SQLite database path |

---

## Integration with video2storyboard

Both servers can be registered in video2storyboard's MCP configuration:

```json
{
  "mcpServers": {
    "mppdp5-sender": {
      "command": "python",
      "args": ["-m", "mcp", "run", "mcp/sender/server.py"],
      "cwd": "/path/to/mppdp5"
    },
    "mppdp5-query": {
      "command": "node",
      "args": ["mcp/server/index.js"],
      "cwd": "/path/to/mppdp5"
    }
  }
}
```

Or use with `uvx`/`npx`:

```json
{
  "mcpServers": {
    "mppdp5-sender": {
      "command": "uvx",
      "args": ["--from", "/path/to/mppdp5", "python", "-m", "cli.main"],
      "env": { "MPPDP5_ROOT": "/path/to/mppdp5" }
    }
  }
}
```