"""Organizations and study roles beyond the sponsor (task 6.4).

usdm4's own ``identification.roles`` assembler input can represent exactly
three organization roles (``co_sponsor``, ``local_sponsor``,
``device_manufacturer``) — anything else is silently dropped with a warning
("no template in ROLE_ORGS"). A Contract Research Organization or a central
laboratory — the two kinds this project actually extracts
(:mod:`usdm4_assure.extract.sites`) — has no template there, so both are
built directly with the assembler's own ``Builder`` *after* assembly
succeeds: the same builder-fallback pattern task 6.3 established for the
sponsor role and for rebuilt objectives.

``ORG_TYPE_CODES`` / ``ROLE_CODES`` below are not invented codes: they are
copied from ``usdm4.assembler.identification_assembler.IdentificationAssembler``'s
own ``ORG_CODES`` / ``ROLE_CODES`` tables, which are private class attributes
and so not otherwise reusable. There is no distinct CDISC study-role code for
a CRO in that table — a CRO is recorded as an ``Organization`` with no
``StudyRole``, and that gap is reported rather than papered over with an
unverified code.
"""
from __future__ import annotations

from usdm4_assure.contracts import Finding, FindingKind, Severity

DOMAIN = "sites"

# Mirrors IdentificationAssembler.ORG_CODES / ROLE_CODES (private there).
ORG_TYPE_CODES = {
    "cro": ("C54148", "Contract Research Organization"),
    "lab": ("C37984", "Laboratory"),
}
ROLE_CODES = {
    "lab": ("C37984", "Laboratory"),   # no distinct CRO role code exists upstream
}

# Which org "kind" each extracted field represents.
_FIELD_ORG_TYPE = {"croName": "cro", "centralLaboratoryName": "lab"}


def _finding(severity: Severity, field: str, message: str) -> Finding:
    return Finding(FindingKind.SANITIZER, severity, DOMAIN, message, field=field)


def _study_version(asm):
    versions = getattr(asm.study, "versions", None) or []
    return versions[0] if versions else None


def attach_organizations(asm, values: dict[str, str | None]) -> list[Finding]:
    """Append an ``Organization`` (+ ``StudyRole`` where a role code exists)
    for each extracted org name onto the assembled study version.

    Args:
        asm: The usdm4 ``Assembler`` after a successful ``execute()``.
        values: ``{field: value}`` from the ``sites`` domain's assured
            fields; a missing or ``None`` value is skipped, not defaulted.

    Returns:
        Findings: an ``INFO`` when an org was recorded with no role code to
        attach, an ``ERROR`` if the builder could not create it.
    """
    from usdm4.api.organization import Organization
    from usdm4.api.study_role import StudyRole

    findings: list[Finding] = []
    version = _study_version(asm)
    builder = getattr(asm, "_builder", None)
    if version is None or builder is None:
        return findings

    for field, org_type in _FIELD_ORG_TYPE.items():
        name = values.get(field)
        if not name:
            continue
        code, decode = ORG_TYPE_CODES[org_type]
        org = builder.create(Organization, {
            "name": name, "label": name, "type": builder.cdisc_code(code, decode),
            "identifier": "Not known", "identifierScheme": "Not known",
        })
        if org is None:
            findings.append(_finding(Severity.ERROR, field,
                                     f"Could not create an Organization for '{name}'."))
            continue
        version.organizations.append(org)

        role_codes = ROLE_CODES.get(org_type)
        if role_codes is None:
            findings.append(_finding(Severity.INFO, field,
                                     f"'{name}' recorded as an Organization; no CDISC study-role "
                                     "code exists for this organization type, so no StudyRole "
                                     "was attached."))
            continue
        rcode, rdecode = role_codes
        role = builder.create(StudyRole, {
            "name": f"ROLE_{field}", "code": builder.cdisc_code(rcode, rdecode),
            "organizationIds": [org.id],
        })
        if role is not None:
            version.roles.append(role)
        else:
            findings.append(_finding(Severity.ERROR, field,
                                     f"Organization '{name}' created but its StudyRole failed."))
    return findings
