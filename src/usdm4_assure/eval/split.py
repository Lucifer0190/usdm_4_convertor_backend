"""The frozen train / held-out split of the benchmark studies.

Readers are developed and tuned on ``TRAIN`` only. ``HELD_OUT`` exists to measure how the
system does on protocols it has never been tuned on, so it is scored rarely and every run
that touches it is recorded (``spikes/reports/heldout_runs.jsonl``). Changing this split
after results have been quoted invalidates them: add a decision to ``docs/ai/DECISIONS.md``
if it ever has to change.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

TRAIN: tuple[str, ...] = ("C5091017", "C4601003", "C4891001", "C4891002", "C4891006")
HELD_OUT: tuple[str, ...] = ("C4891023", "C4891024", "C4891026")

_SETS = {"train": TRAIN, "heldout": HELD_OUT, "all": TRAIN + HELD_OUT}


class HeldOutGuard(RuntimeError):
    """Raised when held-out studies are requested without an explicit confirmation."""


def studies_for(which: str, *, confirm_heldout: bool = False) -> list[str]:
    """Studies in the named set. Held-out studies need ``confirm_heldout=True``."""
    if which not in _SETS:
        raise ValueError(f"unknown set {which!r}; choose one of {sorted(_SETS)}")
    chosen = list(_SETS[which])
    if any(s in HELD_OUT for s in chosen) and not confirm_heldout:
        raise HeldOutGuard(
            "The held-out studies are scored rarely so they stay a fair test. "
            "Pass --confirm-heldout to run them; the run is logged.")
    return chosen


def check_explicit(studies: list[str], *, confirm_heldout: bool = False) -> list[str]:
    """Same guard for an explicit study list (``--studies``)."""
    if any(s in HELD_OUT for s in studies) and not confirm_heldout:
        raise HeldOutGuard(
            "The list includes held-out studies. Pass --confirm-heldout to run them; the run is logged.")
    return studies


def log_heldout_run(log_path: Path, studies: list[str], mode: str, accuracy: float) -> None:
    """Append one line recording that held-out studies were scored."""
    used = [s for s in studies if s in HELD_OUT]
    if not used:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "studies": used, "mode": mode,
           "accuracy": round(accuracy, 4)}
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
