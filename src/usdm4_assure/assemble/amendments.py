"""Amendment diff -> the usdm4 assembler's ``AmendmentsInput`` (task 6.2).

Maps each :class:`~usdm4_assure.extract.amendments.SectionChange` to a
``StudyChange`` (section reference, description, rationale). Two things the
assembler's schema would otherwise assert silently are reported instead:

* **Impact.** ``AmendmentsInput`` has no "not assessed" state — omitted, every
  impact flag (subject safety, rights, data reliability, robustness) defaults
  to *not substantial*. A diff cannot judge substantiality, so the assembled
  flags are an unverified default, and a WARNING says so.
* **Reason and scope.** Not inferred from a diff. A caller that knows them
  passes them in; otherwise the assembler records reason "Other" and no
  geographic scope, and an INFO finding records that they were not extracted.

Unnumbered sections (appendix titles, unnumbered front matter) carry an empty
section reference — the assembler only parses ``"<number>, <title>"`` — and
keep their title in the change description instead.
"""
from __future__ import annotations

from usdm4_assure.contracts import Finding, FindingKind, Severity
from usdm4_assure.extract.amendments import DOMAIN, AmendmentDiff

_KIND_VERB = {"modified": "Modified", "added": "Added", "removed": "Removed"}


def _finding(severity: Severity, message: str, field_: str | None = None) -> Finding:
    return Finding(FindingKind.COMPLETENESS, severity, DOMAIN, message, field=field_)


def amendment_input(diff: AmendmentDiff, *, identifier: str, summary: str | None = None,
                    primary_reason: str = "", secondary_reason: str = ""
                    ) -> tuple[dict | None, list[Finding]]:
    """An ``AmendmentsInput``-shaped dict, or ``None`` when nothing changed.

    Args:
        diff: The section-level diff between the prior and amended version.
        identifier: The amendment's number/identifier as the protocol states it.
        summary: Overall summary; defaults to a count of changed sections.
        primary_reason / secondary_reason: ``"<code>: <decode>"`` or free text
            (the assembler decodes CDISC amendment reasons, else records "Other").
    """
    if not diff.changes:
        return None, [_finding(Severity.INFO, "No section differs between the two versions; "
                                              "no amendment was assembled.")]
    counts = {k: sum(c.kind == k for c in diff.changes) for k in _KIND_VERB}
    auto = ", ".join(f"{n} section(s) {k}" for k, n in counts.items() if n)
    changes = []
    for c in diff.changes:
        verb = _KIND_VERB[c.kind]
        description = (f"{verb}: {c.description}" if c.number
                       else f"{verb} '{c.title}': {c.description}")
        changes.append({"section": f"{c.number}, {c.title}" if c.number else "",
                        "description": description, "rationale": c.rationale})

    findings = [_finding(Severity.WARNING,
                         "Amendment impact (subject safety, rights, data reliability, "
                         "robustness) was not assessed; the assembled flags are the "
                         "assembler's 'not substantial' default and need reviewer "
                         "confirmation.", "impact")]
    if not primary_reason:
        findings.append(_finding(Severity.INFO, "Amendment reason not extracted; assembled "
                                                "as 'Other'.", "reasons"))
    findings.append(_finding(Severity.INFO, "Amendment geographic scope not extracted.",
                             "scope"))
    return {"identifier": identifier, "summary": summary or f"Amendment {identifier}: {auto}.",
            "reasons": {"primary": primary_reason, "secondary": secondary_reason},
            "changes": changes}, findings
