"""Assurance ★ (the moat) — turn raw candidates into scored, triaged fields.

4.1 ensemble    — group candidates per field; measure agreement across methods.
4.2 grounding   — a value backed only by a failed quote is a hard BLOCK
                  (DESIGN.md L5); this runs before the verifier even sees it.
4.3 verifier    — check the chosen value is supported by its cited source span
                  (deterministic token overlap, escalating to an LLM
                  ``verify``-role call on the uncertain subset only).
4.4 confidence  — combine agreement + verifier + coverage into a calibrated
                  score and an auto_accept / review / block decision.

One path for every domain: candidates may be legacy ``FieldCandidate``s
(deterministic extractors) or grounded ``GroundedCandidate``s (LLM shards,
DESIGN.md L4/L5) in any mix — the ensemble, grounding and verifier logic below
treats them uniformly, which is what lets C1-C4 all go through the same
:func:`assure` instead of each domain hand-rolling its own confidence formula.

Runs fully WITHOUT an LLM: the deterministic extractors are independent
members, so agreement is real. An LLM, when present, is just an extra member,
a stronger verifier on the uncertain subset, and (via ``GroundedCandidate``)
a quote to ground against.
"""
from __future__ import annotations

import re
from collections import defaultdict

from usdm4_assure.assure.sanity import Check, check as sanity_check
from usdm4_assure.assure.verify import verify_deterministic, verify_llm
from usdm4_assure.contracts import (
    AssuredField,
    Decision,
    Document,
    FieldCandidate,
    GroundedCandidate,
    Quote,
)
from usdm4_assure.llm.base import LLM

_Candidate = FieldCandidate | GroundedCandidate


def _norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower())


def _method_name(c: _Candidate) -> str:
    return c.method.value if isinstance(c, GroundedCandidate) else c.method


# --- 4.1 ensemble ------------------------------------------------------------ #
# Method names that are an LLM member on the legacy (ungrounded) path.
_LLM_METHODS = frozenset({"claude", "slm", "llm", "openrouter"})


def _group(c: _Candidate) -> str:
    """The independence group a candidate votes in.

    Members that share a code path or a source are one vote: every regex/label/
    table parser is ``"deterministic"`` (two of them agreeing on a wrong value
    read the same footer), while each LLM is its own group, keyed by model.
    """
    if isinstance(c, GroundedCandidate):
        if c.method.value.startswith("llm") or c.method.value == "vision":
            return f"llm:{c.model_id or c.method.value}"
        return "deterministic"
    name = c.method
    return f"llm:{name}" if name in _LLM_METHODS or name.startswith("llm") else "deterministic"


def _is_llm(group: str) -> bool:
    return group.startswith("llm:")


def _choose(cands: list[_Candidate], domain: str, field: str, doc_text: str
            ) -> tuple[str | None, bool, list[_Candidate], Check, int]:
    """Choose the value to deliver for one field.

    Buckets candidates by normalised value, drops any bucket whose value fails a
    sanity check when a valid one exists, then ranks by *independent* groups
    (not headcount), preferring an LLM-backed bucket on a tie.

    Returns:
        ``(value, agree, winner_group, check, n_groups)``. ``value`` is ``None``
        when every candidate value fails its sanity check: an implausible value
        is never delivered.
    """
    buckets: dict[str, list[_Candidate]] = defaultdict(list)
    for c in cands:
        if c.value:
            buckets[_norm(c.value)].append(c)
    if not buckets:
        return None, False, [], Check("neutral"), 0

    ranked = []
    for key, bucket in buckets.items():
        chk = sanity_check(domain, field, bucket[0].value, doc_text)
        groups = {_group(c) for c in bucket}
        ranked.append(((chk.status != "failed", chk.status == "confirmed", len(groups),
                        any(_is_llm(g) for g in groups), len(bucket)), key, chk, groups))
    ranked.sort(key=lambda r: r[0], reverse=True)
    _, key, chk, groups = ranked[0]
    if chk.status == "failed":
        return None, False, buckets[key], chk, len(groups)
    group = buckets[key]
    return group[0].value, len(groups) >= 2, group, chk, len(groups)


# --- 4.2 grounding ------------------------------------------------------------ #
def _resolve_grounding(winner_group: list[_Candidate]) -> tuple[Quote | None, bool]:
    """Find the winning value's best quote, and whether it must hard-BLOCK.

    DESIGN.md L5: a failed quote is a hard, non-probabilistic reject — but
    only when *no* candidate in the winning group has a defensible source.
    If one grounded member's quote failed to resolve while another grounded
    member (or a deterministic one) supports the same value, that is not a
    block; it is simply not this candidate's evidence that gets used.

    Returns:
        ``(quote, hard_block)``. ``quote`` is the first successfully
        resolved quote in the winning group, or ``None`` if the group has no
        grounded members at all (a purely deterministic value — grounding
        does not apply, so ``hard_block`` is always ``False`` in that case).
    """
    grounded = [c for c in winner_group
                if isinstance(c, GroundedCandidate) and c.quote is not None]
    if not grounded:
        return None, False
    ok = next((c.quote for c in grounded if c.quote.ok), None)
    if ok is not None:
        return ok, False
    return grounded[0].quote, True  # every grounded member's quote failed


def _source_text(winner_group: list[_Candidate], quote: Quote | None) -> str:
    """The text to run the verifier against: the resolved quote if grounded,
    else the legacy free-text spans of any ``FieldCandidate`` in the group."""
    if quote is not None:
        return quote.text
    return " ".join(c.source_text for c in winner_group if isinstance(c, FieldCandidate))


# --- 4.4 confidence ------------------------------------------------------------ #
def _confidence(agree: bool, n_methods: int, verifier: str) -> float:
    base = 0.45
    if agree:
        base += 0.30
    base += min(n_methods, 3) * 0.05
    base += {"supported": 0.15, "partial": 0.0, "unsupported": -0.35,
             "n/a": 0.0}[verifier]
    return max(0.0, min(1.0, base))


def _decide(value: str | None, agree: bool, verifier: str, conf: float,
            chk: Check, has_llm_backing: bool) -> Decision:
    """Triage. ``auto_accept`` needs independent agreement (or a validator's own
    confirmation) *and* a supported source span; a value that only deterministic
    members produced can never certify itself."""
    if value is None:
        return Decision.BLOCK
    if verifier == "unsupported":
        return Decision.REVIEW
    independent = agree or chk.status == "confirmed"
    if not has_llm_backing and chk.status != "confirmed":
        independent = False           # deterministic-only: needs a validator's confirmation
    if independent and verifier == "supported" and conf >= 0.8:
        return Decision.AUTO_ACCEPT
    return Decision.REVIEW


def assure(candidates: list[_Candidate], document: Document, fields: list[str],
          domain: str = "", verify_member: LLM | None = None) -> list[AssuredField]:
    """Reconcile every method's candidates into one triaged field per name.

    Args:
        candidates: Any mix of ``FieldCandidate`` (deterministic, legacy) and
            ``GroundedCandidate`` (LLM shard, quote-backed) values.
        document: The ingested document (full text used as the verifier's
            fallback corpus).
        fields: The field names to produce a row for, even if no candidate
            proposed one (that field comes back ``BLOCK``ed with no value).
        domain: Tag recorded on each ``AssuredField`` (and its review row),
            e.g. ``"metadata"`` | ``"design"`` | ``"eligibility"`` |
            ``"objectives"``.
        verify_member: Optional ``verify``-role LLM. Only ever called for a
            field whose deterministic verifier result is ``"partial"``
            (DESIGN.md L6: escalation on the uncertain subset only) — most
            fields never reach a model here.

    Returns:
        One ``AssuredField`` per name in ``fields``.
    """
    by_field: dict[str, list[_Candidate]] = defaultdict(list)
    for c in candidates:
        by_field[c.field].append(c)

    results: list[AssuredField] = []
    for f in fields:
        cands = by_field.get(f, [])
        value, agree, winner_group, chk, n_groups = _choose(cands, domain, f, document.full_text)
        n_methods = n_groups
        quote, hard_block = _resolve_grounding(winner_group)
        source_text = _source_text(winner_group, quote)

        v = verify_deterministic(value, source_text, document.full_text) if value else "unsupported"
        if v == "partial" and verify_member is not None and source_text:
            v = verify_llm(value, source_text, verify_member)

        conf = _confidence(agree or chk.status == "confirmed", n_methods, v)
        if hard_block:
            decision, conf = Decision.BLOCK, 0.0
        else:
            decision = _decide(value, agree, v, conf, chk,
                               any(_is_llm(_group(c)) for c in winner_group))
        if chk.status == "failed":
            conf = 0.0

        results.append(AssuredField(
            field=f, value=value, candidates=cands,
            methods_agree=agree, n_methods=n_methods,
            verifier=v, confidence=conf, decision=decision,
            quote=quote, domain=domain, sanity=chk.reason or chk.status,
        ))
    return results
