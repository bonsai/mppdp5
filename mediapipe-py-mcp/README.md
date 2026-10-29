# mediapipe-py-mcp

A local MCP server that runs [MediaPipe Pose](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)
over local images and the local camera, for the `bonsai/mppdp5` body-controlled
game. It is the pose counterpart to `puredata-mcp` in the same repository.

## Architecture

- **MCP server:** Python 3.11+ (stdio transport)
- **Pose model:** MediaPipe Pose Landmarker, Tasks API (`.task` bundle)
- **Renderer link:** OSC/UDP via `python-osc`, same contract as `mpp5/server.py`
- **Frame source:** image files under `MP_MEDIA_ROOT`, or the local camera

The server never executes shell commands and never writes image data. Frames are
analysed in memory and only numeric pose features are returned or forwarded.

> MediaPipe removed the legacy `mp.solutions.pose` API (it is absent in 0.10.35
> and 1.x). This package therefore targets the Tasks API. The original
> `mppdp5/server.py` still uses `mp.solutions.pose` and needs the same migration.

## Install

From the `mediapipe-py-mcp` directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Or run the installer, which also downloads the model bundle and writes an MCP
client config:

```powershell
.\scripts\install-windows.ps1
```

The installer downloads `pose_landmarker_lite.task` (~5.8 MB) into `models/`.
That file is **not committed**; set `MP_MODEL_PATH` to use a different bundle.

## MCP client configuration

```jsonc
"mediapipe-py-mcp": {
  "type": "local",
  "command": ["C:\\Users\\0501JP\\mppdp5\\mediapipe-py-mcp\\.venv\\Scripts\\mediapipe-py-mcp.exe"],
  "environment": {
    "MP_MEDIA_ROOT": "C:\\Users\\0501JP\\mppdp5\\mediapipe-py-mcp\\media",
    "MP_MODEL_PATH": "C:\\Users\\0501JP\\mppdp5\\mediapipe-py-mcp\\models\\pose_landmarker_lite.task",
    "MP_OSC_HOST": "127.0.0.1",
    "MP_OSC_PORT": "12000"
  },
  "enabled": true
}
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `MP_MEDIA_ROOT` | `./media` | Root directory the tools may read images from |
| `MP_MODEL_PATH` | `models/pose_landmarker_lite.task` | Pose model bundle |
| `MP_OSC_HOST` / `MP_OSC_PORT` | `127.0.0.1` / `12000` | Processing renderer destination |
| `MP_CAMERA_INDEX` | `0` | Camera index for `mp_analyze_frame` |

## MCP tools

| Tool | Description |
| --- | --- |
| `mp_status` | MediaPipe version, model presence, media root, OSC endpoint |
| `mp_list_media` | List analysable images under `MP_MEDIA_ROOT` |
| `mp_analyze_image` | Pose detection on one image; returns landmarks and features |
| `mp_analyze_frame` | Capture one camera frame and analyse it; keeps tracking state |
| `mp_emit_osc` | Analyse an image and forward the pose contract over OSC |
| `mp_reset_tracking` | Clear the camera wrist-speed and hip-sway history |

## OSC contract

Identical to `mpp5/server.py`, so the p5.js and Processing renderers need no
change:

| Address | Payload |
| --- | --- |
| `/pose/points` | 13 filtered landmarks + hip centre, `x, y` each (28 floats); hidden points are `-1.0` |
| `/left_speed` | Left wrist pixel distance since the previous frame |
| `/right_speed` | Right wrist pixel distance since the previous frame |
| `/hip_sway` | Hip sway intensity, `0.0`–`1.5` |

Visibility gates: a landmark below `0.35` is emitted as `-1.0`; `arms_spread`
also requires both wrists above `0.45`.

## Tests

```powershell
python -m pip install -e ".[dev]"
pytest
```

`tests/test_pose.py` covers the pure interpretation logic and needs no MediaPipe
model, mirroring how `puredata-mcp` tests song validation without Pd.

## Notes and limitations

- Pose detection is local; camera frames are never saved or sent anywhere.
- `mp_analyze_image` reports wrist speed and hip sway as `0` because they need
  consecutive frames — use `mp_analyze_frame` for those.
- The camera path needs Windows camera access; failure is reported, not retried.
