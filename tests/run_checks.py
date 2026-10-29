#!/usr/bin/env python3
"""Small-step check runner for mppdp5 (stdlib only, no pytest required).

    python tests/run_checks.py              # everything
    python tests/run_checks.py --fast       # skip subprocess / live MCP checks
    python tests/run_checks.py --list
    python tests/run_checks.py --group mcp
    python tests/run_checks.py --only cli.pose --only cli.contour
    python tests/run_checks.py --fail-fast -v

Each check is independent and reports PASS / FAIL / SKIP. Checks that depend on
an earlier failing check are SKIPped, so one broken stage does not hide the rest.
Exit code: 0 when nothing failed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for p in (ROOT, TESTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from checks.registry import CHECKS, Skip  # noqa: E402

LEVEL_ORDER = {"fast": 0, "slow": 1, "live": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mppdp5 small-step checks")
    parser.add_argument("--list", action="store_true", help="list checks and exit")
    parser.add_argument("--only", action="append", default=[], help="run checks whose id starts with this")
    parser.add_argument("--group", action="append", default=[], help="run a group (env/api/adapters/cli/mcp/contract/demo)")
    parser.add_argument("--fast", action="store_true", help="only level=fast checks")
    parser.add_argument("--fail-fast", action="store_true", help="stop at the first failure")
    parser.add_argument("-v", "--verbose", action="store_true", help="full tracebacks")
    parser.add_argument("--json", action="store_true", help="JSON summary")
    return parser.parse_args()


def selected(args) -> list:
    chosen = []
    for item in CHECKS:
        if args.fast and item.level != "fast":
            continue
        if args.group and item.group not in args.group:
            continue
        if args.only and not any(item.id.startswith(prefix) for prefix in args.only):
            continue
        chosen.append(item)
    return chosen


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = parse_args()
    checks = selected(args)

    if args.list:
        width = max((len(c.id) for c in checks), default=10)
        for item in checks:
            print(f"{item.id:<{width}}  {item.level:4s}  {item.desc}")
        print(f"\n{len(checks)} check(s)")
        return 0

    if not checks:
        print("no checks selected")
        return 0

    width = max(len(c.id) for c in checks)
    status: dict[str, str] = {}
    reasons: dict[str, str] = {}
    timings: dict[str, float] = {}
    started = time.perf_counter()

    for index, item in enumerate(checks, start=1):
        prefix = f"[{index:2d}/{len(checks)}]"

        blocked = next((dep for dep in item.depends_on if status.get(dep) != "PASS"), None)
        if blocked:
            status[item.id] = "SKIP"
            reasons[item.id] = f"blocked by {blocked}"
            print(f"{prefix} SKIP  {item.id:<{width}}  {reasons[item.id]}")
            continue

        began = time.perf_counter()
        try:
            item.fn()
        except Skip as exc:
            status[item.id] = "SKIP"
            reasons[item.id] = str(exc)
        except AssertionError as exc:
            status[item.id] = "FAIL"
            reasons[item.id] = str(exc) or "assertion failed"
        except Exception as exc:  # noqa: BLE001
            status[item.id] = "FAIL"
            reasons[item.id] = f"{exc.__class__.__name__}: {exc}"
            if args.verbose:
                reasons[item.id] += "\n" + traceback.format_exc()
        else:
            status[item.id] = "PASS"
        finally:
            timings[item.id] = (time.perf_counter() - began) * 1000

        ms = timings.get(item.id, 0.0)
        line = f"{prefix} {status[item.id]:4s}  {item.id:<{width}}  {ms:7.1f}ms"
        if status[item.id] != "PASS":
            line += f"  {reasons.get(item.id, '')}"
        print(line)

        if status[item.id] == "FAIL" and args.fail_fast:
            rest = checks[index:]
            for remaining in rest:
                status[remaining.id] = "SKIP"
                reasons[remaining.id] = "fail-fast"
            break

    elapsed = (time.perf_counter() - started) * 1000
    counts = {name: sum(1 for value in status.values() if value == name) for name in ("PASS", "FAIL", "SKIP")}
    failed = [cid for cid, value in status.items() if value == "FAIL"]

    if args.json:
        import json

        print(json.dumps(
            {
                "counts": counts,
                "elapsed_ms": round(elapsed, 1),
                "results": [
                    {"id": cid, "status": value, "reason": reasons.get(cid, ""),
                     "ms": round(timings.get(cid, 0.0), 1)}
                    for cid, value in status.items()
                ],
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(
            f"\n{counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped "
            f"in {elapsed / 1000:.1f}s"
        )
        if failed:
            print("failed: " + ", ".join(failed))

    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
