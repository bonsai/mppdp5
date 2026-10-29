"""MCP server checks: source invariants (fast) and live stdio sessions (live)."""

from __future__ import annotations

import asyncio
import json
import os

from .common import PYTHON, ROOT, read
from .registry import Skip, check

SENDER = "mcp-servers/sender/server.py"
EXPECTED_TOOLS = {
    "list_cameras", "start_contour", "start_pose", "start_segment",
    "start_pipeline", "stop_process", "get_status", "get_logs",
}


@check("mcp.sender.source.tools", desc="sender exposes exactly 8 @mcp.tool() functions")
def sender_tools_count() -> None:
    text = read(SENDER)
    count = text.count("@mcp.tool()")
    assert count == 8, f"expected 8 @mcp.tool() decorators, found {count}"


@check("mcp.sender.source.process_group", desc="child processes get CREATE_NEW_PROCESS_GROUP")
def sender_process_group() -> None:
    text = read(SENDER)
    assert "CREATE_NEW_PROCESS_GROUP" in text, (
        "stop_process sends CTRL_BREAK_EVENT without CREATE_NEW_PROCESS_GROUP; "
        "it signals the MCP server's own process group and kills the session"
    )


@check("mcp.sender.source.log_pump", desc="child stdout is drained into st['logs']")
def sender_log_pump() -> None:
    text = read(SENDER)
    has_reader = ('st["logs"].append' in text) or ("st['logs'].append" in text)
    has_thread = "Thread" in text or "readline" in text or "communicate" in text
    assert has_reader and has_thread, (
        "stdout=subprocess.PIPE is never read: get_logs is always empty and a full "
        "pipe can block the child"
    )


@check("mcp.sender.source.stop_terminate", desc="stop_process falls back to terminate()")
def sender_stop_terminate() -> None:
    assert "proc.terminate()" in read(SENDER), "no terminate() fallback in stop_process"


@check("mcp.query.package", desc="query MCP has index.js + node_modules")
def query_package() -> None:
    assert (ROOT / "mcp-servers" / "server" / "index.js").exists(), "index.js missing"
    assert (ROOT / "mcp-servers" / "server" / "node_modules").exists(), (
        "node_modules missing: cd mcp-servers/server && npm install"
    )
    manifest = json.loads((ROOT / "mcp-servers" / "server" / "package.json").read_text(encoding="utf-8"))
    deps = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    assert "@modelcontextprotocol/sdk" in deps, f"MCP SDK not declared: {sorted(deps)}"


# ── live stdio session ────────────────────────────────────────────────
def _with_session(body):
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:  # pragma: no cover
        raise Skip(f"mcp client unavailable: {exc}") from exc

    env = dict(os.environ)
    env["MPPDP5_ROOT"] = str(ROOT)
    env["MPPDP5_PYTHON"] = PYTHON
    env.setdefault("PYTHONIOENCODING", "utf-8")
    params = StdioServerParameters(
        command=PYTHON,
        args=[str(ROOT / SENDER)],
        cwd=str(ROOT),
        env=env,
    )

    async def runner():
        async with stdio_client(params) as (streams_read, streams_write):
            async with ClientSession(streams_read, streams_write) as session:
                await session.initialize()
                return await asyncio.wait_for(body(session), timeout=90)

    return asyncio.run(runner())


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if getattr(c, "text", None))


def _flatten(exc: BaseException) -> str:
    if exc.__class__.__name__ == "ExceptionGroup" and getattr(exc, "exceptions", None):
        return _flatten(exc.exceptions[0])
    return f"{exc.__class__.__name__}: {exc}"


@check("mcp.sender.live.tools", desc="live session lists the 8 expected tools", level="live",
       depends_on=("env.mcp.client",))
def live_tools() -> None:
    try:
        tools = _with_session(lambda s: _tools(s))
    except Skip:
        raise
    except BaseException as exc:  # noqa: BLE001
        raise AssertionError(f"MCP session failed: {_flatten(exc)}") from None
    names = {tool.name for tool in tools}
    assert names == EXPECTED_TOOLS, f"tool mismatch: {sorted(names ^ EXPECTED_TOOLS)}"


async def _tools(session):
    return (await session.list_tools()).tools


@check("mcp.sender.live.status", desc="get_status returns 3 idle stages", level="live",
       depends_on=("env.mcp.client",))
def live_status() -> None:
    async def body(session):
        result = await session.call_tool("get_status", {})
        return json.loads(_text(result))

    try:
        status = _with_session(body)
    except Skip:
        raise
    except BaseException as exc:  # noqa: BLE001
        raise AssertionError(f"MCP session failed: {_flatten(exc)}") from None
    assert set(status) == {"contour", "pose", "segment"}, f"unexpected stages: {sorted(status)}"
    for stage, info in status.items():
        assert "running" in info, f"{stage} has no running flag"
        assert info["running"] is False, f"{stage} unexpectedly running"


@check(
    "mcp.sender.live.stop_survives",
    desc="start_pose -> stop_process keeps the MCP session alive",
    level="live",
    depends_on=("env.mcp.client",),
)
def live_stop_survives() -> None:
    async def body(session):
        await session.call_tool("start_pose", {
            "input_source": "work/does_not_exist.mp4",
            "output": "work/check_mcp_pose.jsonl",
            "max_frames": 1,
        })
        await asyncio.sleep(1.0)
        stopped = await session.call_tool("stop_process", {"stage": "pose"})
        status = await session.call_tool("get_status", {})
        return _text(stopped), json.loads(_text(status))

    try:
        stopped_text, status = _with_session(body)
    except BaseException as exc:  # noqa: BLE001
        raise AssertionError(
            "session died on stop_process: " + _flatten(exc)
            + " (expected while CTRL_BREAK_EVENT lacks CREATE_NEW_PROCESS_GROUP)"
        ) from None
    assert "stopped" in stopped_text or "not_running" in stopped_text, stopped_text
    assert status["pose"]["running"] is False, "pose still reported as running after stop"
