# puredata-mcp

A local MCP server for controlling a running [Pure Data](https://puredata.info/) patch over OSC/UDP. This starter implementation is intended for the `bonsai/mppdp5` body-controlled rhythm game.

## Architecture

- **MCP server:** Python 3.11+
- **Sound engine:** Pure Data patch files (`.pd`)
- **Runtime control:** OSC/UDP via `python-osc`
- **Song interchange:** validated JSON
- **Game renderer:** Java / Processing remains independent of Pd internals

The MCP server does not execute shell commands or generate arbitrary Pd patch code. It sends a small set of documented OSC events to a patch already opened in Pd.

## Install

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .\puredata-mcp
```

Install Pure Data separately from the official site. Start Pd and open `puredata-mcp/pd/main.pd`. The patch listens on UDP port `9000`; set `PD_OSC_HOST` and `PD_OSC_PORT` to change the destination used by the MCP server.

## MCP client configuration

Example for an MCP client that supports stdio servers:

```json
{
  "mcpServers": {
    "puredata-mcp": {
      "command": "python",
      "args": ["-m", "puredata_mcp.server"],
      "env": {
        "PD_OSC_HOST": "127.0.0.1",
        "PD_OSC_PORT": "9000",
        "PD_SONG_ROOT": "C:\\path\\to\\bonsai\\mppdp5\\puredata-mcp\\songs"
      }
    }
  }
}
```

Use an absolute path for `PD_SONG_ROOT`. The default is `./songs` relative to the process working directory.

## MCP tools

| Tool | Purpose |
|---|---|
| `pd_status` | Show configured endpoint and basic local UDP availability. UDP has no connection handshake, so this cannot prove Pd is running. |
| `pd_note_on(note, velocity=90, channel=1)` | Send `/pd/note/on`. MIDI note and velocity are 0–127; channel is 1–16. |
| `pd_note_off(note, channel=1)` | Send `/pd/note/off`. |
| `pd_set_parameter(name, value)` | Send allowlisted `/pd/param`; see ranges below. |
| `pd_play_effect(name)` | Trigger a registered game effect. |
| `pd_panic()` | Send all-notes-off / panic event. |
| `pd_list_presets()` | List the named starter presets. |
| `pd_load_song(filename)` | Validate a JSON song under `PD_SONG_ROOT`; does not schedule playback. |

Allowlisted parameters: `master_volume` (0–1), `cutoff` (20–20000 Hz), `reverb` (0–1), `attack` (0.001–5 s), `release` (0.01–10 s).

Registered effects: `hit`, `dodge`, `collision`, `game_over`, `level_up`.

## OSC contract

| Address | Arguments |
|---|---|
| `/pd/note/on` | integer note, integer velocity, integer channel |
| `/pd/note/off` | integer note, integer channel |
| `/pd/param` | string name, numeric value |
| `/pd/effect` | string effect name |
| `/pd/panic` | integer flag |

The Pd patch included here is a starter receiver and test tone. Parameter/effect/panic routes are currently diagnostic print hooks; production voice management, true note-off handling, polyphony, and parameter wiring remain follow-up work. Confirm audible playback manually on the target machine.

## Song JSON schema

See [songs/demo.json](songs/demo.json). Version 1 supports `version`, `title`, `bpm`, `preset`, and a non-empty `notes` array. Each note supports `beat`, `midi`, optional `velocity`, and optional `duration`. The loader rejects unknown fields and out-of-range values.

## Smoke test

From the repository root:

```powershell
python -m pip install -e .\puredata-mcp
python -c "from puredata_mcp.server import validate_song; import json; print(validate_song(json.load(open('puredata-mcp/songs/demo.json', encoding='utf-8'))))"
```

Open the Pd patch, then use an MCP client to call `pd_note_on(note=60, velocity=90)`. Call `pd_panic` as needed. If no sound is heard, verify Pd DSP is enabled, the OSC port matches, and the selected audio output device is available.

## Limitations

- This is a first implementation, not a full DAW or generative audio model.
- `pd_load_song` validates and returns song data; the Processing/game runtime is responsible for scheduling events.
- Preset names and effect names are an allowlist contract; the starter Pd patch does not yet implement distinct timbres/effects.
- UDP is best-effort and has no delivery acknowledgement.
