"""The train / held-out split is frozen and the held-out set is guarded."""
import json

import pytest

from usdm4_assure.eval.split import (
    HELD_OUT,
    TRAIN,
    HeldOutGuard,
    check_explicit,
    log_heldout_run,
    studies_for,
)


def test_train_and_held_out_never_overlap_and_cover_the_eight_studies():
    assert not set(TRAIN) & set(HELD_OUT)
    assert len(TRAIN) + len(HELD_OUT) == 8


def test_train_is_the_default_safe_set():
    assert studies_for("train") == list(TRAIN)


def test_held_out_needs_explicit_confirmation():
    with pytest.raises(HeldOutGuard):
        studies_for("heldout")
    with pytest.raises(HeldOutGuard):
        studies_for("all")
    assert studies_for("heldout", confirm_heldout=True) == list(HELD_OUT)


def test_an_explicit_list_is_guarded_too():
    with pytest.raises(HeldOutGuard):
        check_explicit(["C5091017", HELD_OUT[0]])
    assert check_explicit(["C5091017"]) == ["C5091017"]


def test_unknown_set_is_rejected():
    with pytest.raises(ValueError):
        studies_for("everything")


def test_only_held_out_runs_are_logged(tmp_path):
    log = tmp_path / "heldout.jsonl"
    log_heldout_run(log, list(TRAIN), "deterministic", 0.5)
    assert not log.exists()
    log_heldout_run(log, list(TRAIN) + [HELD_OUT[0]], "llm", 0.4)
    row = json.loads(log.read_text(encoding="utf-8").strip())
    assert row["studies"] == [HELD_OUT[0]] and row["mode"] == "llm"
