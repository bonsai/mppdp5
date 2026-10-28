# Java Renderer (PoseRenderer)

Java-based renderer for pose/contour data. Consumes JSONL from mppdp5 adapters and renders using Java2D.

## Building

```bash
javac PoseRenderer.java
```

## Running

```bash
java PoseRenderer work/contour.jsonl
```

## Features

- Reads contour.jsonl or pose.jsonl
- Real-time playback with configurable FPS
- Exports PNG sequence
- Configurable line styles, colors, thickness

## Integration with mppdp5

The Java renderer can be called from the pipeline as a final stage:

```yaml
stages:
  - id: contour
    provider: mppdp5-contour
    output: ./work/contour.jsonl
  
  - id: render
    provider: java-renderer
    input: ./work/contour.jsonl
    output:
      dir: ./output/rendered
      format: png
```