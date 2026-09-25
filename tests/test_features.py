"""Multi-signal feature extraction (task 4.2): vector shape and per-signal stability."""
from __future__ import annotations

import json
from pathlib import Path

from usdm4_assure.assure.features import (
    FeatureRow,
    extract_features,
    extract_features_batch,
    write_features,
)
from usdm4_assure.contracts import (
    AssuredField,
    CharSpan,
    Decision,
    Document,
    FieldCandidate,
    GroundedCandidate,
    Method,
    Quote,
    VerifyPass,
)
from usdm4_assure.extract.windows import EvidenceWindow


def _doc(pages_with_text: set[int] = frozenset({1, 2})) -> Document:
    chars = {p: [CharSpan("x", p, (0, 0, 1, 1))] for p in pages_with_text}
    return Document(source=Path("s.pdf"), blocks=[], full_text="", chars=chars)


def _quote(text: str = "Phase 2", page: int = 1,
          verify_pass: VerifyPass = VerifyPass.EXACT) -> Quote:
    return Quote(text=text, verify_pass=verify_pass, page=page, char_start=0,
                char_end=len(text), bbox=(0, 0, 10, 10))


def _grounded(value: str, quote: Quote | None) -> GroundedCandidate:
    return GroundedCandidate("studyPhase", value, Method.LLM_FRONTIER, quote=quote,
                             domain="metadata")


def _assured(candidates: list, value: str | None = "Phase 2",
            verifier: str = "supported", decision: Decision = Decision.AUTO_ACCEPT,
            quote: Quote | None = None) -> AssuredField:
    return AssuredField(field="studyPhase", value=value, candidates=candidates,
                        methods_agree=len(candidates) >= 2, n_methods=len(candidates),
                        verifier=verifier, confidence=0.9, decision=decision,
                        quote=quote, domain="metadata")


# --- basic shape ------------------------------------------------------------ #
def test_known_field_gets_its_field_type():
    row = extract_features(_assured([_grounded("Phase 2", _quote())]), study_id="S1")
    assert row.field_type == "scalar" and row.domain == "metadata" and row.field == "studyPhase"


def test_unmapped_field_is_unknown_type():
    a = AssuredField(field="footnoteX", value="v", candidates=[], methods_agree=False,
                     n_methods=0, verifier="n/a", confidence=0.1, decision=Decision.BLOCK,
                     domain="soa")
    row = extract_features(a)
    assert row.field_type == "unknown" and row.is_table_cell is True


def test_is_table_cell_flag_follows_domain():
    metadata_field = _assured([_grounded("Phase 2", _quote())])
    assert extract_features(metadata_field).is_table_cell is False


# --- verify_pass / grounding --------------------------------------------------- #
def test_verify_pass_taken_from_winning_candidates_quote():
    quote = _quote(verify_pass=VerifyPass.NORMALIZED)
    row = extract_features(_assured([_grounded("Phase 2", quote)]))
    assert row.verify_pass == "normalized" and row.span_length == len("Phase 2")


def test_no_quote_is_verify_pass_none_and_zero_span():
    row = extract_features(_assured([FieldCandidate("studyPhase", "Phase 2", "labels")]))
    assert row.verify_pass == "none" and row.span_length == 0 and row.page is None


def test_assured_fields_own_quote_wins_over_candidate_quote():
    winner_quote = _quote("candidate quote")
    assured = _assured([_grounded("Phase 2", winner_quote)], quote=_quote("assured quote"))
    assert extract_features(assured).span_length == len("assured quote")


# --- agreement -------------------------------------------------------------- #
def test_single_candidate_has_no_fuzzy_agreement():
    row = extract_features(_assured([_grounded("Phase 2", _quote())]))
    assert row.agreement_fuzzy_mean is None


def test_two_close_candidates_have_high_fuzzy_agreement():
    cands = [_grounded("Phase 2 Randomized Study", _quote()),
            GroundedCandidate("studyPhase", "Phase 2 Randomized Trial", Method.LLM_FRONTIER,
                              domain="metadata")]
    row = extract_features(_assured(cands))
    assert row.agreement_fuzzy_mean is not None and row.agreement_fuzzy_mean > 0.5


def test_two_unrelated_candidates_have_low_fuzzy_agreement():
    cands = [_grounded("Phase 2", _quote()),
            GroundedCandidate("studyPhase", "Completely different text here",
                              Method.LLM_FRONTIER, domain="metadata")]
    row = extract_features(_assured(cands))
    assert row.agreement_fuzzy_mean == 0.0


# --- page position / text layer ----------------------------------------------- #
def test_page_position_and_text_layer_from_document():
    doc = _doc(pages_with_text={1, 2, 3, 4})
    row = extract_features(_assured([_grounded("Phase 2", _quote(page=2))]), document=doc)
    assert row.page == 2 and row.page_position == 0.5 and row.has_text_layer is True


def test_page_with_no_char_geometry_is_no_text_layer():
    doc = _doc(pages_with_text={1})
    row = extract_features(_assured([_grounded("Phase 2", _quote(page=9))]), document=doc)
    assert row.has_text_layer is False


def test_no_document_leaves_text_layer_and_position_unknown():
    row = extract_features(_assured([_grounded("Phase 2", _quote())]))
    assert row.has_text_layer is None and row.page_position is None


# --- retrieval proxy (window) --------------------------------------------------- #
def test_window_supplies_kept_ratio_and_plan_hash():
    win = EvidenceWindow("metadata", "study_header", _doc(), "abc123",
                         blocks_kept=8, blocks_dropped=2)
    row = extract_features(_assured([_grounded("Phase 2", _quote())]), window=win)
    assert row.window_kept_ratio == 0.8 and row.route_plan_hash == "abc123"


def test_no_window_leaves_retrieval_signals_none():
    row = extract_features(_assured([_grounded("Phase 2", _quote())]))
    assert row.window_kept_ratio is None and row.route_plan_hash is None


# --- batch -------------------------------------------------------------------- #
def test_batch_looks_up_each_fields_own_domain_window():
    meta_win = EvidenceWindow("metadata", "study_header", _doc(), "h1", blocks_kept=5)
    design_win = EvidenceWindow("design", "design_structure", _doc(), "h1", blocks_kept=3,
                                blocks_dropped=1)
    fields = [_assured([_grounded("Phase 2", _quote())]),
             AssuredField(field="studyType", value="Interventional", candidates=[],
                          methods_agree=False, n_methods=0, verifier="n/a", confidence=0.5,
                          decision=Decision.REVIEW, domain="design")]
    rows = extract_features_batch(fields, windows={"metadata": meta_win, "design": design_win})
    assert [r.domain for r in rows] == ["metadata", "design"]
    assert rows[0].window_kept_ratio == 1.0 and rows[1].window_kept_ratio == 0.75


# --- writing -------------------------------------------------------------------- #
def test_write_features_parquet_roundtrip(tmp_path):
    rows = [extract_features(_assured([_grounded("Phase 2", _quote())]), study_id="S1")]
    out = write_features(rows, tmp_path / "features.parquet")
    assert out.suffix == ".parquet" and out.exists()
    import pandas as pd
    df = pd.read_parquet(out)
    assert list(df["field"]) == ["studyPhase"] and len(df.columns) == len(FeatureRow.__dataclass_fields__)


def test_feature_row_json_serializable():
    row = extract_features(_assured([_grounded("Phase 2", _quote())]), study_id="S1")
    json.dumps(row.to_dict())    # must not raise (no enums/objects leaking through)
