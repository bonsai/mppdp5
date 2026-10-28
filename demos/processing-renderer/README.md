# Processing Renderer Demos

Processing sketches that consume JSONL output from mppdp5 adapters.

## ContourRenderer

Renders contour lines from `contour.jsonl` (output of ContourAdapter).

### Usage

1. **Generate contour data:**
   ```bash
   cd ../adapter-contour
   python demo_contour.py --input video.mp4 --output ../work/contour.jsonl --mode landmarks
   ```

2. **Open in Processing:**
   - Open `ContourRenderer/ContourRenderer.pde` in Processing IDE
   - Press `L` to load `work/contour.jsonl`
   - Press `P` to play/pause
   - Press `S` to save frames as PNG sequence
   - Left/Right arrows to step through frames

### Controls

| Key | Action |
|-----|--------|
| `L` | Load JSONL file |
| `P` | Play/Pause |
| `S` | Toggle frame saving |
| `←` `→` | Step frame |
| `R` | Reset to frame 0 |
| `+` `-` | Adjust playback speed |

### JSONL Format Expected

```json
{
  "stage_id": "contour",
  "frame_index": 0,
  "timestamp": 0.033,
  "success": true,
  "points": [[0.5, 0.3], [0.52, 0.35], ...],
  "connections": [[0, 1], [1, 2], ...],
  "image_width": 640,
  "image_height": 480
}
```

## PoseRenderer (Planned)

Will render pose keypoints from `pose.jsonl` (output of PoseAdapter).

## SegmentRenderer (Planned)

Will render segmentation masks from mask PNG sequence.