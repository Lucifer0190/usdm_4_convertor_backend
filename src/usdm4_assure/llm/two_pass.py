"""Two-pass sharded LLM extraction (DESIGN.md L4/L5).

Every field an LLM proposes must carry a verbatim quote, and the quote is
resolved to page geometry by :mod:`usdm4_assure.ground.quote` — never trusted
from the model's own coordinates. Two calls per shard:

1. **Reasoning pass** — free text. The model is asked to locate and quote its
   evidence for each field in prose, before committing to a structured answer.
   This pass is not parsed; it exists to let the model "show its work" before
   the constrained pass, which published evidence associates with fewer
   fabricated values than a single-shot JSON extraction.
2. **JSON pass** — given its own reasoning as context, the model returns
   strict JSON: one ``{field, value, quote}`` object per field in the shard.
   ``quote`` is then resolved against the document; a quote that fails to
   resolve produces a :class:`~usdm4_assure.contracts.GroundedCandidate` whose
   ``quote.verify_pass`` is ``FAILED`` — callers must treat that as ungrounded
   (DESIGN.md L5's hard reject), not as a low-confidence value.

Prompt templates live in ``llm/prompts/<shard.id>.pass{1,2}.md`` and are
loaded verbatim, so editing a template changes that shard's ``prompt_hash``
(sha256 of both templates) — exactly what the Part 11 audit trail needs to
reproduce a call.
"""
from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path

from usdm4_assure.contracts import Document, GroundedCandidate, Method
from usdm4_assure.extract.shards import Shard
from usdm4_assure.ground.quote import resolve_quote
from usdm4_assure.llm.base import LLM

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# How much of the document each pass sees. Callers hand a narrow, section-level
# window (extract/slots.py), so this is a safety bound, not the working size.
# It was 12,000 characters, which cut a real eligibility or objectives section
# off after its first page or two.
_MAX_DOC_CHARS = 40000
# Output budgets. Pass 2 emits a JSON list whose size scales with the number of
# records (five estimands need far more than the 1,600 tokens it used to get).
_PASS1_TOKENS = 2000
_PASS2_TOKENS = 6000


@cache
def _load_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _pass_names(shard: Shard | str) -> tuple[str, str]:
    prompt_id = shard if isinstance(shard, str) else shard.id
    return f"{prompt_id}.pass1.md", f"{prompt_id}.pass2.md"


def template_hash(prompt_id: str) -> str:
    """A stable hash of a prompt id's two templates (``<id>.pass{1,2}.md``).

    Depends only on the template *files* on disk, not on any document or
    model — two calls against the same prompt on different protocols get the
    same hash, and editing a template (a new prompt "version") changes it.
    This is the ``prompt_hash`` recorded in every :class:`AuditRecord`.
    """
    p1_name, p2_name = _pass_names(prompt_id)
    payload = prompt_id + "\x00" + _load_template(p1_name) + "\x00" + _load_template(p2_name)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prompt_hash(shard: Shard) -> str:
    """:func:`template_hash` of a flat shard's templates."""
    return template_hash(shard.id)


def run_two_pass(llm: LLM, prompt_id: str, document_text: str, **values: str
                 ) -> list | None:
    """Both passes for any prompt id; returns the parsed JSON array, or ``None``.

    The shared engine behind :func:`extract_shard` (flat ``{field, value,
    quote}`` shards) and structured extractors such as estimands, whose JSON
    items nest. ``values`` fill the templates' other placeholders. ``None``
    means the member failed (unavailable, error, or unparseable output) — a
    bad LLM member must never crash the run.
    """
    if not getattr(llm, "available", False):
        return None
    p1_name, p2_name = _pass_names(prompt_id)
    text = document_text[:_MAX_DOC_CHARS]
    try:
        reasoning = llm.complete(_fill(_load_template(p1_name), document_text=text, **values),
                                 task="extract_prose", max_tokens=_PASS1_TOKENS)
        raw = llm.complete(_fill(_load_template(p2_name), reasoning=reasoning,
                                 document_text=text, **values),
                           task="extract_prose", max_tokens=_PASS2_TOKENS)
        return _parse_json_items(raw)
    except Exception:  # noqa: BLE001 — a bad LLM member must not crash the run
        return None


def _fill(template: str, **values: str) -> str:
    """Substitute ``{name}`` placeholders via plain replace (not ``str.format``,
    so the JSON braces inside a template never need escaping)."""
    out = template
    for key, val in values.items():
        out = out.replace("{" + key + "}", val)
    return out


def _parse_json_items(raw: str) -> list[dict]:
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON array found in model output")
    return json.loads(raw[start:end + 1])


def extract_shard(doc: Document, llm: LLM, shard: Shard) -> list[GroundedCandidate]:
    """Run one shard's two-pass extraction against ``doc`` with ``llm``.

    Returns:
        One :class:`GroundedCandidate` per field the model returned a
        non-null value for. ``[]`` if the LLM is unavailable or either pass
        fails to produce parseable output — a bad LLM member must not crash
        the run (mirrors the existing single-pass ``extract_llm`` behavior).
    """
    items = run_two_pass(llm, shard.id, doc.full_text, description=shard.description,
                         fields=", ".join(shard.fields))
    if items is None:
        return []
    phash = prompt_hash(shard)

    model_id = getattr(llm, "model", None) or getattr(llm, "name", None)
    out: list[GroundedCandidate] = []
    valid_fields = set(shard.fields)
    for item in items:
        if not isinstance(item, dict):
            continue
        field_name = item.get("field")
        value = item.get("value")
        if field_name not in valid_fields or not value:
            continue
        quote_text = item.get("quote") or ""
        quote = resolve_quote(doc, quote_text) if quote_text else None
        out.append(GroundedCandidate(
            field=field_name, value=str(value).strip(), method=Method.LLM_FRONTIER,
            quote=quote, model_id=model_id, prompt_hash=phash, domain=shard.domain,
        ))
    return out


def extract_domain(doc: Document, llm: LLM, shards: list[Shard]) -> list[GroundedCandidate]:
    """Run every shard for a domain and concatenate their candidates."""
    out: list[GroundedCandidate] = []
    for shard in shards:
        out += extract_shard(doc, llm, shard)
    return out
