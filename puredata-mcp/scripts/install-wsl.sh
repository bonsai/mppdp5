#!/usr/bin/env bash
set -Eeuo pipefail

# Install bonsai/mppdp5 puredata-mcp on Ubuntu/Debian under WSL2.
# Run from the repository root:
#   bash puredata-mcp/scripts/install-wsl.sh

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MCP_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$MCP_DIR/.." && pwd)"
VENV_DIR="$MCP_DIR/.venv"
CONFIG_OUT="$REPO_ROOT/mcp-config.wsl.json"

say() { printf '\n[ puredata-mcp ] %s\n' "$*"; }
die() { printf '\n[ puredata-mcp ] ERROR: %s\n' "$*" >&2; exit 1; }

if ! grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
  say "Warning: WSL was not detected; continuing because this may still work on Linux."
fi

if ! command -v apt-get >/dev/null 2>&1; then
  die "This installer expects an Ubuntu/Debian-based WSL distribution with apt-get."
fi

if ! command -v sudo >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then
  die "Install sudo or run this script as root so apt packages can be installed."
fi

APT=(apt-get)
if [ "$(id -u)" -ne 0 ]; then APT=(sudo apt-get); fi

say "Installing system dependencies (Python venv, pip, Git, Pure Data, ALSA utilities)."
"${APT[@]}" update
"${APT[@]}" install -y python3 python3-venv python3-pip git puredata alsa-utils

command -v python3 >/dev/null 2>&1 || die "python3 was not found after installation."
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"' \
  || die "puredata-mcp requires Python 3.11 or newer."

say "Creating isolated Python environment: $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -e "$MCP_DIR"

say "Writing MCP client configuration example: $CONFIG_OUT"
CONFIG_OUT="$CONFIG_OUT" VENV_DIR="$VENV_DIR" MCP_DIR="$MCP_DIR" python3 <<'PY'
import json
import os
from pathlib import Path

config_path = Path(os.environ["CONFIG_OUT"])
venv_dir = Path(os.environ["VENV_DIR"])
mcp_dir = Path(os.environ["MCP_DIR"])
config = {
    "mcpServers": {
        "puredata-mcp": {
            "command": str(venv_dir / "bin" / "puredata-mcp"),
            "args": [],
            "env": {
                "PD_OSC_HOST": "127.0.0.1",
                "PD_OSC_PORT": "9000",
                "PD_SONG_ROOT": str(mcp_dir / "songs"),
            },
        }
    }
}
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

say "Checking installed command and Python test dependencies."
"$VENV_DIR/bin/puredata-mcp" --help >/dev/null 2>&1 || {
  say "The MCP entry point did not accept --help; checking import instead."
  "$VENV_DIR/bin/python" -c 'import puredata_mcp.server'
}

say "Installation complete."
printf '\nNext steps:\n'
printf '  1. Open Pure Data with the OSC patch:\n'
printf '     pd "%s"\n' "$MCP_DIR/pd/main.pd"
printf '  2. Add the contents of %s to your MCP client configuration.\n' "$CONFIG_OUT"
printf '  3. Restart the MCP client so it loads puredata-mcp.\n'
printf '  4. Run tests (if pytest is installed):\n'
printf '     cd "%s" && "%s/bin/python" -m pytest\n' "$MCP_DIR" "$VENV_DIR"
printf '\nNote: UDP delivery does not confirm that Pure Data is running or producing sound.\n'
printf 'The current Pd patch is an initial scaffold; parameter/effect/panic routes need further implementation.\n'
