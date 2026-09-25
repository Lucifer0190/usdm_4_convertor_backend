"""USDM4-Assure command line."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False, help="USDM4-Assure pipeline CLI.")
console = Console()


@app.command()
def version() -> None:
    """Print version."""
    from usdm4_assure import __version__
    console.print(f"usdm4-assure {__version__}")


@app.command()
def roles() -> None:
    """Print active model roles configuration."""
    from pathlib import Path

    import yaml

    config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
    with config_path.open() as f:
        config = yaml.safe_load(f)

    console.rule("[bold]Model roles[/]")
    if "roles" in config:
        t = Table(title="OpenRouter role → model mapping", show_lines=False)
        t.add_column("role", style="cyan")
        t.add_column("model")
        for role, model in config["roles"].items():
            t.add_row(role, model)
        console.print(t)

    if "constraints" in config:
        console.print("\n[bold]Constraints[/]")
        for name, value in config["constraints"].items():
            console.print(f"  {name}: {value}")


@app.command()
def convert(pdf: str, out: str = "data/out", core: bool = False,
            slm: bool = False, require_llm: bool = False) -> None:
    """Convert a protocol PDF to USDM 4.0 JSON via the Assurance spine.

    Pass --slm to add a cheap different-family SLM member to the ensemble.
    Pass --require-llm to fail if no LLM key is configured.
    """
    import os

    from usdm4_assure.pipeline import run

    if require_llm:
        os.environ["USDM4_REQUIRE_LLM"] = "1"

    console.rule("[bold]USDM4-Assure — convert")
    res = run(pdf, out_dir=out, run_core=core, use_slm=slm)
    console.print(f"LLM member: [cyan]{res.llm_name}[/] "
                  f"({'active' if res.llm_name != 'stub' else 'no key — deterministic paths only'})")

    t = Table(title="Assured metadata fields", show_lines=False)
    for col in ("field", "value", "conf", "agree", "methods", "verifier", "decision"):
        t.add_column(col)
    style = {"auto_accept": "green", "review": "yellow", "block": "red"}
    for a in res.assured:
        t.add_row(
            a.field, (a.value or "—")[:46], f"{a.confidence:.2f}",
            "✓" if a.methods_agree else "·", str(a.n_methods), a.verifier,
            f"[{style[a.decision.value]}]{a.decision.value}[/]",
        )
    console.print(t)

    v = res.validation
    console.print(f"\n[bold]Gates[/] — structural: {_g(v.get('structural'))}"
                  f" | d4k: {_d4k(v.get('d4k'))} | core: {_core(v.get('core'))}")
    console.print(f"Review triage: {res.review_stats}")
    console.print(f"Artifacts → [dim]{res.out_dir}/study.usdm.json, review.json[/]")


@app.command("convert-full")
def convert_full(pdf: str, out: str = "data/out_full", core: bool = False,
                 slm: bool = False, require_llm: bool = False) -> None:
    """Full loop: PDF -> metadata + design + SoA -> one conformant USDM 4.0 study.

    Pass --slm to add a cheap different-family SLM member to the metadata ensemble.
    Pass --require-llm to fail if no LLM key is configured.
    """
    import os

    from usdm4_assure.pipeline import run_full

    if require_llm:
        os.environ["USDM4_REQUIRE_LLM"] = "1"

    console.rule("[bold]USDM4-Assure — full study")
    r = run_full(pdf, out_dir=out, run_core=core, use_slm=slm)
    s = r.study
    if not s.get("ok"):
        console.print(f"[red]Assembler failed[/]: {s.get('assembler_errors')[:3]}")
        return
    console.print(f"arms: [cyan]{[a['name'] for a in r.design.arms]}[/] "
                  f"| model {r.design.intervention_model} | phase from metadata")
    console.print(f"assembled study: {s['summary']}")
    v = s["validation"]
    console.print(f"[bold]Gates[/] — structural: {_g(v.get('structural'))} | "
                  f"d4k: {_d4k(v.get('d4k'))} | core: {_core(v.get('core'))}")
    console.print(f"assembler errors: {len(s['assembler_errors'])}")
    console.print(f"Artifact → [dim]{r.out_dir}/study.usdm.json[/]")


@app.command("convert-soa")
def convert_soa(pdf: str) -> None:
    """Extract a Schedule of Activities table into USDM ScheduleTimeline entities."""
    from usdm4_assure.assemble.soa import build_soa
    from usdm4_assure.extract.soa.crossval import cross_validate
    from usdm4_assure.extract.soa.methods import (
        extract_pdfplumber,
        extract_pymupdf,
        extract_pymupdf_stitched,
    )

    console.rule("[bold]USDM4-Assure — SoA")
    pymupdf_grid = extract_pymupdf_stitched(pdf) or extract_pymupdf(pdf)
    ag = cross_validate([extract_pdfplumber(pdf), pymupdf_grid])
    console.print(f"grid: {len(ag.visits)} visits × {len(ag.activities)} activities "
                  f"| methods {ag.methods} | triage {ag.triage()}")
    res = build_soa(ag)
    console.print(f"assembled USDM: {res['summary']}")
    t = Table(title="Scheduled activities per visit (assembled)")
    t.add_column("encounter"); t.add_column("activities")
    for enc, acts in res["sai_activities_by_encounter"].items():
        t.add_row(enc, ", ".join(acts))
    console.print(t)


@app.command()
def eval(study: str = "", out: str = "spikes/reports/eval_scoreboard") -> None:
    """Score the pipeline against frozen field labels; writes the scoreboard.

    Runs run_full() on every labelled usdm_data study (task 4.1's 4 held-out
    protocols), scores the output with eval.score, and reports auto-accept
    coverage, review burden and realized error (DESIGN.md L6) overall and per
    domain. Pass --study "id1,id2" to score only specific studies.
    """
    from pathlib import Path

    from usdm4_assure.eval.report import run_eval

    console.rule("[bold]USDM4-Assure — eval scoreboard")
    study_ids = [s.strip() for s in study.split(",") if s.strip()] or None
    sb = run_eval(study_ids=study_ids, out_dir=Path(out))
    if not sb.studies:
        console.print("[red]No studies scored.[/] " + "; ".join(sb.errors))
        return

    console.print(f"Studies: [cyan]{', '.join(sb.studies)}[/] ({sb.n_labels_total} labels)")
    if sb.errors:
        console.print(f"[yellow]{len(sb.errors)} error(s):[/] {'; '.join(sb.errors)}")

    t = Table(title="Scoreboard")
    for col in ("domain", "fields", "auto-accept coverage", "review burden",
               "realized error", "accuracy of found"):
        t.add_column(col)

    def _pct(x: float | None) -> str:
        return "—" if x is None else f"{x * 100:.1f}%"

    t.add_row("overall", str(sb.overall.n_fields), _pct(sb.overall.auto_accept_coverage),
             _pct(sb.overall.review_burden), _pct(sb.overall.realized_error),
             _pct(sb.overall.accuracy_of_found))
    for domain in sorted(sb.by_domain):
        d = sb.by_domain[domain]
        t.add_row(domain, str(d.n_fields), _pct(d.auto_accept_coverage), _pct(d.review_burden),
                 _pct(d.realized_error), _pct(d.accuracy_of_found))
    console.print(t)
    console.print(f"Wrote [dim]{out}.md[/] and [dim]{out}.json[/]")


def _g(s) -> str:
    if not s:
        return "—"
    return "[green]PASS[/]" if s.get("passed") else "[red]FAIL[/]"


def _d4k(s) -> str:
    if not s or "error" in s:
        return "[red]err[/]"
    return f"{s.get('rules_run')} rules, {s.get('findings')} findings"


def _core(s) -> str:
    if not s:
        return "—"
    if "skipped" in s:
        return f"[dim]skipped ({s['skipped']})[/]"
    if "error" in s:
        return "[red]err[/]"
    return f"{s.get('rules_run')} rules, {s.get('findings')} findings"


if __name__ == "__main__":
    app()
