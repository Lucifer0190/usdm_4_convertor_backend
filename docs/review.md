# Review UI

An HTMX interface over the Part 11 audit store (`usdm4_assure.audit`) — the tool a human
reviewer certifies a run through. It is the only place in the system that writes reviewer
edits and certifications; the extraction pipeline itself never mutates a field once decided.

## Running it

```bash
pip install -e .[review]
uvicorn usdm4_assure.review.app:app --reload
```

or, via Docker Compose:

```bash
docker compose --profile review up
```

Then open `http://localhost:8000`. There is no login and no TLS — see
[Security posture](#security-posture) below for why that is a deliberate, scoped decision,
not an oversight.

## What it shows

- **Home page** — every source PDF with audit history (found under `data/audit/*.sqlite`),
  with field/decision counts and certification status.
- **Source page** — every field's *current* value (the latest record for that field, across
  any run or edit), sorted worst-first: `block`, then `review`, then `auto_accept`, ties
  broken by confidence ascending. That ordering is the point — a reviewer's limited time goes
  to the fields most likely to need it first.
- **Click-to-source** — expanding a field's page number renders a cropped PNG of exactly the
  bounding box its quote resolved to (DESIGN.md L5's grounding, made visible). The crop is
  rendered fresh from the source PDF on every request; nothing is pre-rendered or cached.
- **History** — every record ever written for a field, oldest first: the original extraction,
  any edits, in full.
- **Edit** — changes a field's value. This never overwrites anything: it appends a new
  `REVIEW_EDIT` audit record carrying the prior value and a required reason, and that new
  record becomes the field's current value because it is now the latest one.
- **Certify** — one button, one record: a `CERTIFY` event with a reviewer id and a signature
  meaning (default: "Reviewed and approved for submission"), the Part 11 sign-off. Certifying
  also triggers post-edit telemetry (below).

## How a field's "current" value works

The audit store is append-only — there is no `UPDATE` anywhere, enforced by a SQLite trigger,
not just application code (`usdm4_assure.audit.store`). So a field's current value is not a
column; it is simply the *last* record written for that `(domain, field)` key, whatever event
wrote it. An edit is a new record with the same key, so it becomes current the instant it is
appended, without anything else changing.

## Post-edit-distance telemetry

On certification, `usdm4_assure.review.telemetry` computes the normalized character edit
distance between each field's original extracted value and its value *as of certification*
(an edit made after certifying does not count against that certified state). `0.0` means the
pipeline's value needed no change; `1.0` means it was effectively rewritten. This is the
"how much did review actually cost" number reported in the certification confirmation and,
in aggregate, is one of DESIGN.md §5's operational metrics.

Every field a reviewer actually edited also gets exported to `data/labels/edits/<study>.jsonl`
as a new label — the reviewer's corrected value is real signal, closer to ground truth than
the pipeline's own guess. It never touches `data/labels/fields/` (task 4.1's frozen
ground-truth set): that directory is explicitly not to be silently blended with review
corrections, so edit-derived labels get their own directory, their own `review_edit:<source>`
labeler tag, and — unlike the frozen set — are freely regenerable on every certification.

## Security posture

**Localhost only, no auth**, by design (DESIGN.md L9, PLAN.md CP5-A): this is a
human-in-the-loop tool for one operator on their own machine, not a multi-tenant service.
Every write is still fully accountable — reviewer id and reason are required on every edit,
and nothing is ever silently overwritten — but access control is out of scope until there is
an actual multi-user deployment to design it for. Do not expose port 8000 beyond `localhost`
without adding one.
