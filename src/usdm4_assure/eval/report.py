"""`usdm4 eval` scoreboard (task 4.4, PLAN.md §8.5, DESIGN.md §5).

Runs the full pipeline on every labelled corpus study, scores its output
against the frozen labels (:mod:`usdm4_assure.eval.score`), and reports the
two numbers DESIGN.md L6 asks every run to report — **auto-accept coverage**
and **review burden** — plus **realized error**: the fraction of *labelled*
auto-accepted fields that were actually wrong. Realized error is only ever
computed over labelled fields (the only ones with a known right answer); it
is not the same as, and is not presented as, the conformal bound's certified
guarantee (:mod:`usdm4_assure.assure.conformal`) — it is what actually
happened on this small held-out set, nothing more.

**Discipline (DESIGN.md §5):** this module reports numbers. It never asserts
an accuracy floor — that is `tests/`'s job for behaviour, not this module's.

Currently 4 studies carry frozen labels (task 4.1) — far short of the ~1,200
field-level labels DESIGN.md §5 anticipates. The scoreboard says so plainly
rather than dressing up a 4-study result as a general accuracy claim.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from usdm4_assure.contracts import AssuredField, Decision
from usdm4_assure.eval.corpus import studies as corpus_studies
from usdm4_assure.eval.labels import FieldLabel, read_labels
from usdm4_assure.eval.score import FieldScore, score_fields
from usdm4_assure.pipeline import run_full

REPO_ROOT = Path(__file__).resolve().parents[3]
LABELS_DIR = REPO_ROOT / "data" / "labels" / "fields"
DEFAULT_OUT = REPO_ROOT / "spikes" / "reports" / "eval_scoreboard"


@dataclass
class DomainScoreboard:
    """Coverage/burden/error for one domain, or ``"overall"`` across all of them."""
    domain: str
    n_fields: int = 0                      # every AssuredField the pipeline produced
    n_auto_accept: int = 0
    n_review: int = 0
    n_block: int = 0
    n_labelled: int = 0                    # of those, how many have a frozen label
    n_labelled_auto_accept: int = 0
    n_labelled_auto_accept_correct: int = 0
    verdicts: dict[str, int] = field(default_factory=dict)

    @property
    def auto_accept_coverage(self) -> float | None:
        return self.n_auto_accept / self.n_fields if self.n_fields else None

    @property
    def review_burden(self) -> float | None:
        return self.n_review / self.n_fields if self.n_fields else None

    @property
    def realized_error(self) -> float | None:
        """Error rate among labelled, auto-accepted fields. ``None`` with no such fields."""
        if not self.n_labelled_auto_accept:
            return None
        return 1 - self.n_labelled_auto_accept_correct / self.n_labelled_auto_accept

    @property
    def accuracy_of_found(self) -> float | None:
        """Of labelled fields the pipeline attempted, the fraction scored correct."""
        found = sum(v for k, v in self.verdicts.items() if k != "predicted_absent")
        if not found:
            return None
        correct = sum(self.verdicts.get(k, 0) for k in ("exact", "normalized", "fuzzy"))
        return correct / found

    def to_dict(self) -> dict:
        d = asdict(self)
        d["auto_accept_coverage"] = self.auto_accept_coverage
        d["review_burden"] = self.review_burden
        d["realized_error"] = self.realized_error
        d["accuracy_of_found"] = self.accuracy_of_found
        return d


@dataclass
class Scoreboard:
    generated_at: str
    studies: list[str]
    n_labels_total: int
    overall: DomainScoreboard
    by_domain: dict[str, DomainScoreboard]
    errors: list[str] = field(default_factory=list)   # studies that failed to run

    def to_dict(self) -> dict:
        return {"generated_at": self.generated_at, "studies": self.studies,
               "n_labels_total": self.n_labels_total, "errors": self.errors,
               "overall": self.overall.to_dict(),
               "by_domain": {d: s.to_dict() for d, s in self.by_domain.items()}}


def score_study(pdf_path: str | Path, labels: list[FieldLabel]
                ) -> tuple[list[AssuredField], list[FieldScore]]:
    """Run the full pipeline on one PDF and score its output against ``labels``."""
    result = run_full(pdf_path)
    all_assured = (result.assured_meta + result.assured_design
                  + result.assured_eligibility + result.assured_objectives)
    predicted = {(a.domain, a.field): a.value for a in all_assured}
    return all_assured, score_fields(predicted, labels)


def _accumulate(sb: DomainScoreboard, fields: list[AssuredField],
                scores_by_key: dict[tuple[str, str], FieldScore]) -> None:
    for a in fields:
        sb.n_fields += 1
        if a.decision is Decision.AUTO_ACCEPT:
            sb.n_auto_accept += 1
        elif a.decision is Decision.REVIEW:
            sb.n_review += 1
        else:
            sb.n_block += 1
        s = scores_by_key.get((a.domain, a.field))
        if s is None:
            continue
        sb.n_labelled += 1
        sb.verdicts[s.verdict] = sb.verdicts.get(s.verdict, 0) + 1
        if a.decision is Decision.AUTO_ACCEPT:
            sb.n_labelled_auto_accept += 1
            if s.verdict in ("exact", "normalized", "fuzzy"):
                sb.n_labelled_auto_accept_correct += 1


def build_scoreboard(runs: list[tuple[str, list[AssuredField], list[FieldScore]]],
                     errors: list[str] | None = None) -> Scoreboard:
    """Aggregate per-study (fields, scores) into overall + per-domain boards."""
    overall = DomainScoreboard("overall")
    by_domain: dict[str, DomainScoreboard] = {}
    n_labels = 0
    study_ids = []
    for study_id, fields, scores in runs:
        study_ids.append(study_id)
        n_labels += len(scores)
        scores_by_key = {(s.domain, s.field): s for s in scores}
        _accumulate(overall, fields, scores_by_key)
        by_field_domain: dict[str, list[AssuredField]] = {}
        for a in fields:
            by_field_domain.setdefault(a.domain, []).append(a)
        for domain, domain_fields in by_field_domain.items():
            dsb = by_domain.setdefault(domain, DomainScoreboard(domain))
            _accumulate(dsb, domain_fields, scores_by_key)
    return Scoreboard(generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
                      studies=study_ids, n_labels_total=n_labels, overall=overall,
                      by_domain=by_domain, errors=errors or [])


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def render_markdown(sb: Scoreboard) -> str:
    header = (f"Generated {sb.generated_at}. {len(sb.studies)} labelled stud"
             f"{'y' if len(sb.studies) == 1 else 'ies'} ({sb.n_labels_total} field labels): "
             f"{', '.join(sb.studies) or '(none)'}.\n")
    lines = ["# Evaluation scoreboard\n", header]
    if sb.n_labels_total < 1200:
        lines.append(
            f"> **Small-sample caveat.** DESIGN.md §5 anticipates ~1,200 field-level labels "
            f"from ~20 protocols; only {sb.n_labels_total} exist today (task 4.1's 4 held-out "
            f"studies). Numbers below describe this small set, not a general accuracy claim.\n")
    if sb.errors:
        lines.append(f"**{len(sb.errors)} stud{'y' if len(sb.errors) == 1 else 'ies'} "
                     f"failed to run:** {', '.join(sb.errors)}\n")

    header_row = ("| Domain | Fields | Auto-accept coverage | Review burden | Realized error "
                 "(labelled auto-accept) | Accuracy of found |")
    lines += [header_row, "|---|---|---|---|---|---|"]
    lines.append(f"| **overall** | {sb.overall.n_fields} | "
                 f"{_pct(sb.overall.auto_accept_coverage)} | {_pct(sb.overall.review_burden)} | "
                 f"{_pct(sb.overall.realized_error)} | {_pct(sb.overall.accuracy_of_found)} |")
    for domain in sorted(sb.by_domain):
        d = sb.by_domain[domain]
        lines.append(f"| {domain} | {d.n_fields} | {_pct(d.auto_accept_coverage)} | "
                     f"{_pct(d.review_burden)} | {_pct(d.realized_error)} | "
                     f"{_pct(d.accuracy_of_found)} |")
    return "\n".join(lines) + "\n"


def run_eval(study_ids: list[str] | None = None, out_dir: Path = DEFAULT_OUT) -> Scoreboard:
    """Run + score every labelled study (or just ``study_ids``); writes the scoreboard."""
    by_id = {s.study_id: s for s in corpus_studies()}
    label_files = {p.stem: p for p in LABELS_DIR.glob("*.jsonl")} if LABELS_DIR.is_dir() else {}
    targets = study_ids if study_ids is not None else sorted(label_files)

    runs, errors = [], []
    for sid in targets:
        labels = read_labels(label_files[sid]) if sid in label_files else []
        if not labels:
            errors.append(f"{sid}: no labels found")
            continue
        study = by_id.get(sid)
        if study is None:
            errors.append(f"{sid}: not found in corpus (spikes/_work/usdm_data absent?)")
            continue
        try:
            fields, scores = score_study(study.pdf_path, labels)
        except Exception as exc:  # noqa: BLE001 — one broken study must not sink the scoreboard
            errors.append(f"{sid}: {type(exc).__name__}: {exc}")
            continue
        runs.append((sid, fields, scores))

    sb = build_scoreboard(runs, errors)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{out_dir}.json").write_text(json.dumps(sb.to_dict(), indent=2), encoding="utf-8")
    Path(f"{out_dir}.md").write_text(render_markdown(sb), encoding="utf-8")
    return sb
