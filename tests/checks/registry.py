"""Tiny check registry for the mppdp5 test suite (no third-party deps)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Check:
    id: str
    fn: Callable[[], None]
    level: str = "fast"          # fast | slow | live
    desc: str = ""
    depends_on: tuple[str, ...] = field(default_factory=tuple)

    @property
    def group(self) -> str:
        return self.id.split(".", 1)[0]


CHECKS: list[Check] = []
_SEEN: set[str] = set()


class Skip(Exception):
    """Raised by a check that cannot run in this environment."""


def check(
    id: str,
    *,
    level: str = "fast",
    desc: str = "",
    depends_on: tuple[str, ...] = (),
):
    """Register a check. The function must raise AssertionError on failure."""

    def decorate(fn: Callable[[], None]) -> Callable[[], None]:
        if id in _SEEN:
            raise RuntimeError(f"duplicate check id: {id}")
        if level not in ("fast", "slow", "live"):
            raise RuntimeError(f"bad level for {id}: {level}")
        _SEEN.add(id)
        CHECKS.append(Check(id=id, fn=fn, level=level, desc=desc, depends_on=depends_on))
        return fn

    return decorate
