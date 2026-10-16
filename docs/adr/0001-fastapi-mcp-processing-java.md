# ADR-0001: FastAPI API and optional MCP adapter; keep Processing Java renderer native

- **Status:** Proposed
- **Date:** 2026-10-16
- **Decision owners:** mppdp5 maintainers

## Context

mppdp5 interprets camera pose once in Python and sends derived values to multiple renderers:
- p5.js browser renderer over FastAPI/WebSocket
- Processing 4 Java-mode renderer over OSC/UDP

We want an API and MCP surface without duplicating pose interpretation, while retaining the existing Java projection. We also want to understand whether the Java sketch can be embedded in a static browser page / GitHub Pages.

## Decision

1. **FastAPI remains the local runtime/API boundary.** Keep camera capture, MediaPipe, pose interpretation, WebSocket publishing, and OSC publishing in the Python process. Add REST endpoints only for explicit, useful operations such as health/status, current derived state, and validated configuration.
2. **MCP is an adapter, not a second domain implementation.** Expose a small set of safe, documented tools through FastMCP that call the same Python service layer used by FastAPI. Start with local stdio for developer use. If remote MCP transport is later required, add it deliberately with authentication and network-boundary review. Do not duplicate pose logic inside MCP tool handlers.
3. **Keep Processing in Java mode as a native/local renderer.** It can continue receiving OSC/UDP from Python and does not need to be rewritten. A normal Java-mode Processing sketch cannot be embedded and executed directly inside modern browsers or GitHub Pages; Java browser applets are obsolete/unsupported.
4. **Use the existing p5.js renderer for browser embedding.** If a browser-hosted projection is required, implement that renderer in JavaScript/p5.js and consume the same derived state contract. Treat it as a separate renderer, not as a conversion of the Java sketch at runtime.
5. **Preserve privacy and separation.** Raw camera frames stay in memory and are never exposed through REST, WebSocket, or MCP. Only derived pose/motion data and explicitly permitted configuration/status may cross these boundaries. Bind local services to loopback by default; do not add remote camera-control or arbitrary-code-execution tools.

## Architecture

```text
Camera -> OpenCV/MediaPipe -> Pose Interpreter -> Shared domain/service layer
                                                 |-> FastAPI REST + WebSocket -> p5.js (browser)
                                                 |-> OSC/UDP -----------------> Processing Java (local)
                                                 |-> FastMCP tools (local stdio initially)
```

## Consequences

### Positive
- One pose interpretation pipeline; no duplicated business logic.
- Existing Processing Java effects and OSC contract remain usable.
- API, MCP tools, and renderers can evolve independently.
- Browser publishing remains compatible with static hosting.

### Trade-offs
- Processing Java stays a separately launched desktop/local process; it is not a Java sketch embedded in a webpage.
- MCP adds a protocol adapter and must be kept small and permission-limited.
- REST endpoints and MCP tools require explicit schemas, validation, and tests.

## Initial scope

- Add a health/status endpoint without exposing raw frames.
- Define a typed, versioned schema for derived state and configuration.
- Add FastMCP tools for read-only status/current derived state first.
- Keep camera start/stop and calibration mutation out of the first MCP release unless separately validated.
- Add contract tests for REST, WebSocket, OSC, and MCP consistency.

## Rejected alternatives

- **Put all logic in MCP handlers:** rejected because it duplicates domain behavior and couples the system to one transport.
- **Replace Processing Java with p5.js immediately:** rejected because it discards the existing Java renderer unnecessarily.
- **Embed Java mode directly in the browser:** rejected because modern browsers do not support Java applets and GitHub Pages cannot execute a desktop Java sketch.
- **Expose raw video to API/MCP:** rejected on privacy and data-minimization grounds.

## Acceptance criteria for implementation

- REST and MCP return only derived data / approved configuration; no raw frames.
- Shared service functions are used by REST and MCP.
- Processing Java continues to receive the existing OSC contract without changes to pose interpretation.
- Browser renderer remains available as static HTML/JavaScript.
- Automated tests cover schema validation, tracking loss / neutral reset, and transport contract behavior.
