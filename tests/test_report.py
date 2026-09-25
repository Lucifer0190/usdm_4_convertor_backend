"""`usdm4 eval` scoreboard (task 4.4): coverage/burden/error math on hand cases."""
from __future__ import annotations

import pytest

from usdm4_assure.contracts import AssuredField, Decision
from usdm4_assure.eval.labels import FieldLabel
from usdm4_assure.eval.report import DomainScoreboard, build_scoreboard, render_markdown
from usdm4_assure.eval.score import score_fields


def _field(domain: str, name: str, value: str | None, decision: Decision) -> AssuredField:
    return AssuredField(field=name, value=value, candidates=[], methods_agree=True,
                        n_methods=2, verifier="supported", confidence=0.9, decision=decision,
                        domain=domain)


def _label(domain: str, name: str, value: str, ftype: str = "scalar") -> FieldLabel:
    return FieldLabel("S1", domain, name, value, ftype, "test", "2026-01-01T00:00:00Z")


# --- DomainScoreboard properties ------------------------------------------------ #
def test_empty_board_has_none_ratios():
    sb = DomainScoreboard("metadata")
    assert sb.auto_accept_coverage is None and sb.review_burden is None
    assert sb.realized_error is None and sb.accuracy_of_found is None


def test_ratios_hand_computed():
    sb = DomainScoreboard("metadata", n_fields=10, n_auto_accept=6, n_review=3, n_block=1,
                          n_labelled=4, n_labelled_auto_accept=3,
                          n_labelled_auto_accept_correct=2,
                          verdicts={"exact": 2, "miss": 1, "predicted_absent": 1})
    assert sb.auto_accept_coverage == 0.6 and sb.review_burden == 0.3
    assert sb.realized_error == pytest.approx(1 / 3)
    assert sb.accuracy_of_found == 2 / 3   # 2 correct of 3 attempted (excludes predicted_absent)


# --- build_scoreboard: one study, hand-checkable ---------------------------------- #
def test_build_scoreboard_single_study():
    fields = [
        _field("metadata", "studyPhase", "Phase 2", Decision.AUTO_ACCEPT),   # labelled, correct
        _field("metadata", "sponsorName", "Wrong Co", Decision.AUTO_ACCEPT),  # labelled, wrong
        _field("metadata", "studyTitle", None, Decision.BLOCK),              # unlabelled
        _field("design", "studyType", "Interventional", Decision.REVIEW),    # labelled, review
    ]
    labels = [_label("metadata", "studyPhase", "Phase 2"),
             _label("metadata", "sponsorName", "Acme Corp"),
             _label("design", "studyType", "Interventional")]
    predicted = {(a.domain, a.field): a.value for a in fields}
    scores = score_fields(predicted, labels)

    sb = build_scoreboard([("S1", fields, scores)])
    assert sb.studies == ["S1"] and sb.n_labels_total == 3

    o = sb.overall
    assert (o.n_fields, o.n_auto_accept, o.n_review, o.n_block) == (4, 2, 1, 1)
    assert o.n_labelled == 3 and o.n_labelled_auto_accept == 2
    assert o.n_labelled_auto_accept_correct == 1     # studyPhase right, sponsorName wrong
    assert o.realized_error == 0.5
    assert o.auto_accept_coverage == 0.5 and o.review_burden == 0.25

    meta = sb.by_domain["metadata"]
    assert (meta.n_fields, meta.n_auto_accept, meta.n_labelled) == (3, 2, 2)
    assert meta.realized_error == 0.5
    design = sb.by_domain["design"]
    assert (design.n_fields, design.n_auto_accept, design.n_labelled) == (1, 0, 1)
    assert design.realized_error is None   # nothing auto-accepted in this domain


def test_build_scoreboard_aggregates_across_studies():
    f1 = [_field("metadata", "studyPhase", "Phase 2", Decision.AUTO_ACCEPT)]
    f2 = [_field("metadata", "studyPhase", "Phase 3", Decision.AUTO_ACCEPT)]
    s1 = score_fields({("metadata", "studyPhase"): "Phase 2"},
                      [_label("metadata", "studyPhase", "Phase 2")])
    s2 = score_fields({("metadata", "studyPhase"): "Phase 3"},
                      [_label("metadata", "studyPhase", "Phase 4")])   # wrong
    sb = build_scoreboard([("A", f1, s1), ("B", f2, s2)])
    assert sb.studies == ["A", "B"] and sb.overall.n_labelled_auto_accept == 2
    assert sb.overall.n_labelled_auto_accept_correct == 1 and sb.overall.realized_error == 0.5


def test_build_scoreboard_records_errors():
    sb = build_scoreboard([], errors=["BrokenStudy: ValueError: boom"])
    assert sb.errors == ["BrokenStudy: ValueError: boom"]
    assert sb.overall.n_fields == 0


# --- rendering -------------------------------------------------------------------- #
def test_markdown_mentions_studies_caveat_and_errors():
    fields = [_field("metadata", "studyPhase", "Phase 2", Decision.AUTO_ACCEPT)]
    scores = score_fields({("metadata", "studyPhase"): "Phase 2"},
                          [_label("metadata", "studyPhase", "Phase 2")])
    sb = build_scoreboard([("S1", fields, scores)], errors=["X: failed"])
    md = render_markdown(sb)
    assert "S1" in md and "small-sample" in md.lower() and "X: failed" in md
    assert "overall" in md and "metadata" in md


def test_markdown_handles_zero_studies_without_crashing():
    sb = build_scoreboard([])
    md = render_markdown(sb)
    assert "0 field labels" in md or "(none)" in md
