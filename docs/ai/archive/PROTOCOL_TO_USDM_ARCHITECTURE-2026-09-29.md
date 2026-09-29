# Protocol → USDM 4.0: Target Architecture (buildable from the current boilerplate)

**Date:** 2026-09-29 · **Status:** design proposal, no code changed · **Companion:** `DDF_ALIGNMENT_AND_INGESTION_RESEARCH.md` (the evidence for why this is needed)

**Revision 2 (same day):** rewritten after one real LLM run on C5091017 v2 with the refreshed models (Section 0). The run changed three things in the design: the LLM is a **first-class reader for semantic fields**, not an optional add-on; agreement between members must be **independence-aware**; and LLM output contracts need **budgeting and empty-response handling**.

**Ground rules for this design**
- Budget: LLM runs are rationed (one protocol so far), so **the deterministic layers must be buildable, testable and measurable without any LLM**, and LLM calls must be few, narrow and cached.
- Accuracy over cost, right-sized: each role keeps its tier and moves to the newest release of that tier (Sonnet 5.5, Opus 5.5, GPT-6 Sol, Gemini 3.1 Pro), not to the top flagship.
- Reuse what already works in the repo: grounding, audit, review UI, validation gates, the assembler wrapper, the section graph, the SoA stitcher and mark re-derivation.

---

## 0. What the first real LLM run showed (C5091017 v2, refreshed models)

**Setup.** `usdm4 convert-full --require-llm` on the 146-page C5091017 protocol, unrouted defaults otherwise. Models were the refreshed roles: Sonnet 5.5 (metadata, sites), Opus 5.5 (hard reasoning), GPT-6 Sol (second extractor). 7 LLM calls in total. Compared against the hand-corrected `C5091017-v2.0_IDEAL.json`. The existing test suite (445 tests) still passes after the model refresh. Raw outputs: scratchpad `run1/`.

**Headline: the models found the right answers and the architecture threw them away.**

| Item | What the LLM said (from the response cache) | What ended up in the USDM | Why |
|---|---|---|---|
| Phase | Sonnet 5.5: `"studyPhase": "3"` ✓ | **"Phase 1"**, `auto_accept` at confidence 1.00 ✗ | Two deterministic members (`labels`, `titlepage`) both read the template footer "Phase 1 2 3 4" and **outvoted the correct LLM**. They share one wrong source, so their "agreement" is not independent evidence |
| Sponsor | Sonnet 5.5: `"Pfizer Inc."` ✓ | "Pfizer Inc. 66 Hudson Boulevard East New York…Brief Title:" ✗ | Same: the longer deterministic string won |
| Title, protocol ID, version | Sonnet 5.5 all correct ✓ | Correct | No conflict, so they survived (title only reached `review`, 0.65) |
| Estimands | Opus 5.5 and GPT-6 Sol both found **5 estimands**, matching the reference ✓ (deterministic parser also found 5) | **0 estimands assembled** ✗ | Each estimand's endpoint is matched by text to the extracted endpoints; the extracted endpoints were garbage (`.`), so all 5 were dropped as "matches no extracted endpoint" |
| Arms, eligibility, objectives | **No LLM call was ever made** | `['600-MG','‒1']`; 8 inclusion / **172** exclusion (amendment-history and TOC lines); objective `"."` ✗ | `run_full` only calls the grounded LLM shards for these domains as an *escalation inside the repair loop*. The loop ran **0 rounds**, because the only failing d4k rules were "known gaps" with no repair path. So these three domains were 100% regex |
| SoA | **No vision call was made** | 2 encounters, 40 "activities" that are abbreviation-list terms (`Mpro, MQI, mTOR…`), 0 marks ✗ | Wrong table selected (no SoA locator), so the vision reader never had a valid grid to read |
| Empty answers | 2 of 7 calls returned an **empty string** (Opus 5.5 estimand JSON pass; Sonnet 5.5 sites JSON pass) | Silently treated as "no result" | Pass 2 has `max_tokens=1600`; a reasoning-capable model can spend the budget on thinking and return nothing. **The empty result was written to the persistent cache**, so a re-run would replay the failure |
| Placeholders | – | Synopsis text, version date `2026-01-01`, rationale strings, `healthyVolunteers=False` invented | `assemble/sanitize.py` (reported as findings but still in the file) |
| Conformance | – | Structural PASS; d4k 213 rules, 45 findings, 6 failing rules | Known assembler gaps; unrelated to accuracy |

**Scorecard vs the reference (this one study):** phase ✗, identifiers 1 of 6, arms ✗, epochs 1 of 3, encounters 2 of 15, activities 40 (wrong content) vs 53, objectives 0 of 6 usable, estimands 0 of 5, organisations ✗ (no vendors), narrative 0. The model refresh itself did no harm (all calls succeeded, valid JSON, right answers where asked); the pipeline around it is the limiting factor.

**Measured accuracy of this run (single study, vs `C5091017-v2.0_IDEAL.json`):**

| Measure | Result |
|---|---|
| 14 headline scalar fields, repo scorer (`eval/score.py`), strict | **5 / 14 = 36%** (exact 3, normalized 1, fuzzy 1; 7 miss, 2 absent) |
| Same, counting two semantic equivalents as correct ("Interventional" = "Interventional Study"; "Final Protocol Amendment 2" = v2.0) | 7 / 14 = 50% |
| Structured records (identifiers, arms, interventions, epochs, encounters, activities, criteria, objectives, estimands, vendor orgs) | **2 / 116 = ~2%** (identifiers 1/6, activities 1/53 by loose token match, everything else 0) |
| Blended, all 130 reference items | **~5–7%** |
| Wrong items delivered | 180 eligibility criteria against 19 in the reference; 40 "activities" that are abbreviations; 2 fake arms |
| What the LLM answered correctly *when asked* (raw cached responses) | Metadata 5 of 5 asked fields (title, sponsor, phase, protocol ID, version) and estimand count 5 of 5, i.e. the model outputs were far better than the delivered USDM |

Caveats: one study; the reference is hand-corrected but not perfect (e.g. max age `999`, version `2.0`); matching is exact/normalized/token-overlap, not a human review.

**Run 2 (same study, after the first four fixes were built):**

| Measure (same rubric, 130 reference items) | Run 1 (before) | Deterministic only, after fixes | **Run 2 (LLM + fixes)** |
|---|---|---|---|
| 14 headline scalar fields, strict scorer | 5 / 14 = 36% | 7 / 14 = 50% | **8 / 14 = 57%** |
| Structured records (incl. 5 vendor orgs, still 0) | 2 / 116 = 2% | 40 / 116 = 34% | **44 / 116 = 38%** |
| **All 130 items** | **7 = 5.4%** | 47 = 36% | **52 = 40%** |
| Estimands assembled | 0 / 5 | 5 / 5 | **5 / 5** |
| Eligibility criteria correct / delivered | 0 / 180 | 18 / 19 | **18 / 19** |
| Objective rows | 0 / 6 | 5 / 6 | **5 / 6** |
| Arms, interventions | 0 / 2, 0 / 2 | 0 / 2, 0 / 2 | **2 / 2, 2 / 2** ("Treatment arm", "Placebo arm") |
| Phase | wrong (Phase 1 @ 1.00) | correct | **correct** (validator-confirmed) |
| d4k findings | 45 | 21 | **21** |
| LLM calls / empty responses | 7 / 2 | 0 | **14 / 0** (Sonnet 5.5 ×7, GPT-6 Sol ×6, Opus 5.5 ×1; the rest served from cache) |
| Auto-accepted fields | 2, one of them wrong | – | **6, all six correct** (small n) |

Scorer notes: three of the six strict "misses" are equivalent wording (phase `3` vs `Phase 3`; `Interventional` vs `Interventional Study`; `Amendment 2` vs `2.0`), two are the reference's condensed objective wording against our verbatim text, and maximum age `None` (no upper limit) equals the reference's `999`. Counting those, the 14 scalars are about 13 of 14; the strict number is kept as the headline because the rubric is fixed across runs.

**What is still wrong, in order of weight:** the Schedule of Activities (epochs 0/3, visits 0/15, activities 11/53 = 71 of 130 items, 55% of the rubric) because the header parser still assumes a three-row header; identifiers other than the protocol number (NCT, EU CT, IND, PIP, compound: 1/6); vendors and organisations (0/5); narrative sections (not in the rubric, still absent). The SoA reader (Section 3.4) is now the single biggest lever.

**Design consequences (these are now built into the sections below):**
1. **LLM = default reader for semantic fields, from the first pass**, on narrow slot windows with verbatim quotes. Deterministic code parses *structure* (tables, lists, page ranges), verifies quotes and enforces sanity rules. "LLM proposes, code disposes."
2. **Independence-aware agreement.** Members that share a code path or source count once. A deterministic member can never outvote a grounded LLM candidate by numbers alone; disagreement goes to a **sanity validator** (e.g. the Phase must equal the synopsis `Phase:` label; template-footer text is stripped before any member sees it).
3. **Row-level linking** for objectives ↔ endpoints ↔ estimands (they sit in one table row), never text matching against a possibly-wrong list. Prevents the cascade that dropped all 5 estimands.
4. **LLM call contract:** per-shard token budgets sized to record lists, `finish_reason` / empty / truncated detection, one automatic retry with a larger budget, and **never cache empty, error or truncated responses**.
5. **The repair loop must not be the only route to the LLM.** Escalation stays, but the first pass already uses it.
6. **No fabricated fill-ins** (already in Section 3.6), plus an explicit run policy for incomplete studies.

---

## 1. First, your question: will other protocols look like Pfizer's?

**Short answer: partly. Same family, same idea, different details. And the world is converging.**

### 1.1 What I found online

| Fact | Source |
|---|---|
| **ICH M11 (CeSHarP)** — one harmonised protocol template plus a machine-readable technical specification — was finalised on **19 Nov 2025**, published by **EMA in Dec 2025** and by the **FDA on 22 May 2026**. There is a transition period; some regulators still accept legacy templates. | [EMA page](https://www.ema.europa.eu/en/ich-m11-guideline-clinical-study-protocol-template-technical-specifications-scientific-guideline), [Federal Register](https://www.federalregister.gov/documents/2026/05/22/2026-10295/m11-clinical-electronic-structured-harmonised-protocol-cesharp-international-council-for), [ECA summary](https://www.gmp-compliance.org/gmp-news/final-ich-m11-cesharp-guideline) |
| **TransCelerate's Common Protocol Template (CPT)** came first. It is optional; companies adopting it are asked to keep at least **level-1 and level-2 headings** and may change level-3. It has since been aligned to M11 and to CDISC USDM. | [CASRAI guide](https://casrai.org/guides/ich-m11-clinical-trial-protocol-template), [CPT FAQ](https://www.transceleratebiopharmainc.com/wp-content/uploads/2018/11/CPT_ImplTK-CPT-FAQs_V004.pdf) |
| Research on SoA extraction says table formats are **widely varying** across legacy protocols; SoA is 5–15 pages of a 100–400 page document; simple grids are handled, conditional/repeat-cycle/oncology schedules are hard. | [ProtocolMiner (MRA)](https://esmed.org/MRA/mra/article/view/7362), [TimeTox](https://arxiv.org/pdf/2603.21335) |

I could **not** retrieve the M11 template's actual section list from the web pages (only the PDF links). Action item: download the M11 template and technical specification from EMA/FDA and turn them into our section registry (Section 3.2). The technical specification is especially valuable because it lists the *data elements* a protocol must contain, which is exactly what our USDM mapper needs.

### 1.2 What I measured locally (real protocols from other sponsors)

I checked the section titles of the public protocols in our corpus (Lilly, Novo Nordisk, Roche, BMS, Amgen, Sanofi, Alexion, Tesaro, KalVista, AstraZeneca):

| Family | Examples | How the key sections look |
|---|---|---|
| **A. CPT/M11-style numbering (same as Pfizer)** | Pfizer (197 of 204 files), Alexion, Lilly NCT04184622 / 04677179 / 05176314 / 05324124 | `1.3 Schedule of Activities`, `3 Objectives and Endpoints`, `5.1 Inclusion Criteria`, `5.2 Exclusion Criteria` — identical numbers |
| **B. Same sections, shifted numbers** | BMS (`2 Schedule of Activities`, `4 Objectives and Endpoints`, `6.1 Inclusion Criteria`), older Lilly (`2/4/6.1`), Sanofi (`3 Objectives and Endpoints`) | Same content and near-identical titles, different numbers. **Titles work; numbers don't** |
| **C. Different vocabulary** | Novo Nordisk ("Flowchart", "Objectives and endpoints", "Primary, secondary and exploratory endpoint(s)"), Roche ("Efficacy Objectives", "Safety Objectives", "Schedule of Assessments"), Amgen ("Subject Eligibility"), Tesaro ("Study Objectives"), older Lilly ("6. Objectives") | Different names and different ordering; objectives and endpoints split into separate subsections |
| **Structure carrier** | Bookmarks present in Pfizer 204/204, Lilly/Alexion/BMS/Amgen/Sanofi/Tesaro. **No bookmarks** in AstraZeneca, Novo (3 of 3), Roche (3 of 3), KalVista, one Lilly, CDISC Pilot | Need a fallback: printed contents page and heading detection |
| **Scans** | Roche NCT02291289 (45 of 245 pages image-only), Lilly NCT04557384 (27 of 115), Novo NCT03693430 (11 of 97) | Need OCR fallback |

### 1.3 What that means

1. **Pfizer's recent protocols are the easy, high-regularity case.** 197 of 204 share the same 9 top-level sections in the same order; inclusion, exclusion, objectives, statistics and abbreviations exist in **204 of 204**, the SoA in 203.
2. **Other sponsors mostly contain the same *content blocks*, under different titles and numbers.** So the architecture must key on **meaning (title semantics + content cues), not numbering**. The repo's `sections/classify.py` already does title-keyword classification for this reason. Extend it; don't replace it.
3. **The table layouts differ more than the headings do** (Pfizer's 3-column Objectives/Endpoints/Estimands table vs Novo's separate lists vs Roche's per-domain lists). Readers therefore need a *strategy per layout*, chosen by detection, with a "cannot read this → flag, don't guess" exit.
4. **M11 will make future protocols more uniform** (and its machine-readable spec maps almost directly onto USDM), but the archive, amendment chains of running studies, and other sponsors' legacy documents mean we must support family A, B and C for years.
5. Therefore the design is: **one canonical protocol model, a registry of "template families" that tell readers where to look, and readers that are layout-strategy based.** Pfizer CT02-GSOP is family A. Adding another sponsor later means adding a registry entry and, if needed, one reader strategy, not rewriting the pipeline.

---

## 2. Design principles

1. **Structure first, then content.** Find *where* things are (section spans, page ranges) with cheap, exact methods before reading *what* they say.
2. **Read each region with a purpose-built reader**, not one regex over the whole document. (Today's failures all come from running regexes over the full text.)
3. **Records, not scalars.** Real protocols have dozens of criteria, objectives, endpoints, visits and activities. The current shard contract (5 eligibility fields, 4 objective fields) cannot hold them.
4. **Every record carries provenance** (page, bbox, char span, section, reader, tier). Grounding stays deterministic and code-owned.
5. **Two independent methods where the document itself offers them.** Pfizer protocols repeat facts (Synopsis vs body; SoA vs assessment text; TOC vs bookmarks). Those are free cross-checks that need no LLM.
6. **Fail loudly, never fabricate.** No placeholder values. A missing required item is a blocking finding.
7. **Downstream-readiness is a gate.** A machine-readable contract of what D1–D4 need is checked on every run.
8. **Hybrid reading: code for structure, LLM for meaning.** Tables, lists, page ranges, quote resolution and sanity checks are deterministic. Semantic fields (arms and randomisation from prose, blinding, stratification, estimand attributes, rationale, vendors named in prose) are read by a frontier LLM on the slot's own window, with a verbatim quote that code must resolve. Both feed the same records and provenance contracts.
9. **Agreement must be independent.** Members that share a source or code path count once; correlated members may not outvote a grounded candidate. Disagreement is settled by a sanity validator or by review, never by headcount.
10. **LLM calls are budgeted and honest:** sized to the record list, empty/truncated output is an error (retried once with a bigger budget), and failures are never cached.

---

## 3. The architecture

```
                                 ┌─────────────────────────────────────────────────────┐
PDF (+ prior versions,           │ 0  INTAKE & TRIAGE                                   │
 amendment summaries)  ─────────►│    valid? pages? text-layer ratio? bookmarks?        │
                                 │    template-family fingerprint (footer/title text)   │
                                 │    version/date/amendment number; page classes       │
                                 └──────────────┬──────────────────────────────────────┘
                                                ▼
                                 ┌─────────────────────────────────────────────────────┐
                                 │ 1  SUBSTRATE  (PyMuPDF, keep)                        │
                                 │    lines/words/chars + bbox + font flags             │
                                 │    furniture stripper (repeating header/footer bands)│
                                 │    glyph normaliser (U+F0B7 → bullet, ligatures)     │
                                 │    OCR fallback for image-only pages (non-Pfizer)    │
                                 │    ⇒ CleanDocument                                    │
                                 └──────────────┬──────────────────────────────────────┘
                                                ▼
                                 ┌─────────────────────────────────────────────────────┐
                                 │ 2  STRUCTURE MAP                                     │
                                 │    outline: bookmarks → printed contents page →      │
                                 │             heading detection (font/numbering)       │
                                 │    slot resolver: section → canonical slot(s)        │
                                 │             using family profile (titles + aliases)  │
                                 │    ⇒ SectionSpans(page,y → page,y) + missing-slot    │
                                 │       findings; TOC-vs-outline coverage check        │
                                 └──────────────┬──────────────────────────────────────┘
                                                ▼
        ┌───────────────────────────────────────────────────────────────────────────────┐
        │ 3  READERS  (deterministic, one per region, layout-strategy based)              │
        │   TitleMeta · Synopsis · Design/Arms · Interventions · Eligibility ·            │
        │   ObjectivesEndpointsEstimands · SoA · Assessments · Discontinuation ·          │
        │   Statistics/SampleSize · Narrative tree · Abbreviations · AmendmentSummary ·   │
        │   Vendors/Systems                                                               │
        │   each returns typed Records + provenance + tier (1 template, 2 heading, 3 LLM) │
        └──────────────┬────────────────────────────────────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │ 4  LINKERS / DERIVERS  (rule-based)                                           │
        │   SoA activity ↔ assessment section ↔ instrument ↔ category enum ·            │
        │   objective ↔ endpoint ↔ estimand ↔ intervention · criteria ↔ population ·   │
        │   visit typing (ET, unscheduled, telephone/remote, log) · windows (±days)     │
        └──────────────┬────────────────────────────────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │ 5  PROTOCOL MODEL (canonical, typed, versioned)  ← the single internal truth   │
        └──────────────┬────────────────────────────────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │ 6  ASSURANCE (existing, generalised to records)                               │
        │   grounding quotes · reader-vs-reader agreement · invariants · completeness   │
        │   · confidence features · triage (auto_accept / review / block)               │
        └──────────────┬────────────────────────────────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │ 7  USDM MAPPER                                                                │
        │   ProtocolModel → data4knowledge AssemblerInput (existing)                    │
        │   + Builder-level additions for what the assembler cannot express             │
        │     (narrative content, activity descriptions, contact modes, vendors,        │
        │      extension attributes) + post-assembly repairs (existing pattern)         │
        └──────────────┬────────────────────────────────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │ 8  VALIDATION GATES:  pydantic → d4k rules → CORE → DOWNSTREAM-READINESS (new) │
        └──────────────┬────────────────────────────────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │ 9  REVIEW & CERTIFICATION (existing HTMX UI + Part 11 audit)                  │
        └─────────────────────────────────────────────────────────────────────────────┘

   Layer L (LLM readers, first pass, budgeted): semantic fields on slot windows, residue
   routing, quote verification, VLM check of SoA cells and the study-schema figure. They emit
   the same Records as the deterministic readers. Deterministic layers still run without
   them, so a run with no key (or an exhausted budget) degrades to "partial + flagged",
   never to wrong-but-confident.
```

### 3.1 Layer 0 — Intake & triage (new, small)

- **Input gate:** reject empty/corrupt/encrypted files (the packet contains a zero-byte PDF). Record page count, text-layer ratio, bookmark count, image-only page list.
- **Template-family fingerprint:** running-header text is a reliable tell (Pfizer pages carry `CT02-GSOP Clinical Protocol Template Phase 1 2 3 4 (01 May 2024)`, `PFIZER CONFIDENTIAL`, `Final Protocol Amendment 2, 05 Nov 2025`). Combine with outline shape (the 9 level-1 titles) to pick a family profile. Unknown → `generic` profile + low-confidence flag.
- **Document identity:** protocol number, amendment number and date from the running header and title page. These also order a study's version chain.
- **Page classes:** born-digital text / image-only / landscape table page / figure page.

### 3.2 Layer 2 — Structure map and the slot registry (extend `sections/`)

A **slot** is a canonical thing every protocol should contain. The registry is config, not code, e.g. `config/families/ct02_gsop.yaml` plus `config/families/generic.yaml`:

```yaml
slots:
  synopsis:        {titles: ["synopsis", "protocol summary"],            required: true}
  soa:             {titles: ["schedule of activities", "schedule of assessments",
                             "schedule of events", "flowchart", "time and events"],  required: true}
  objectives:      {titles: ["objectives, endpoints, and estimands", "objectives and endpoints",
                             "study objectives", "objectives"],          required: true}
  inclusion:       {titles: ["inclusion criteria", "selection of subjects", "subject eligibility"], required: true}
  exclusion:       {titles: ["exclusion criteria"],                       required: true}
  interventions:   {titles: ["study intervention(s) administered", "study treatment"], required: true}
  discontinuation: {titles: ["discontinuation of study intervention", "withdrawal"],   required: true}
  # … assessments, statistics, sample_size, abbreviations, amendment_summary, appendices
```

- Resolution is by **normalised title match, then hierarchy, then content cue** (e.g. a section containing the words "Participants are eligible to be included in this study only if" is `inclusion`). Numbers are never used as identity.
- Output: `SectionSpan(slot, start=(page,y), end=(page,y))`. The repo's `Section.page/y/page_end` and `SectionGraph.section_for()` already give this; the registry replaces the ported route tables as the source of truth for *where things are*.
- **Missing-slot findings** (e.g. no `soa`) are first-class and block dependent readers.
- **Outline fallbacks:** (1) bookmarks; (2) parse the printed contents page (`Title ......... 23`) and map to pages; (3) heading detection by font size/weight/numbering (exists in `sections/graph.from_headings`).
- **Coverage invariant:** every bookmark should fall inside exactly one span; contents-page entries should match bookmarks. Mismatches are findings.

### 3.3 Layer 3 — Readers (the heart of the change)

Each reader has the same interface:

```python
class Reader(Protocol):
    slot: str                                      # which SectionSpan(s) it consumes
    def read(self, span: SectionSpan, doc: CleanDocument, ctx: ReadContext) -> ReaderResult
# ReaderResult = records + provenance + tier + findings + self_checks
```

| Reader | Input span | Method (deterministic) | Output records | Built-in cross-check |
|---|---|---|---|---|
| **TitleMeta** | title page, running header, synopsis head | Label/value pairs (`Protocol Title:`, `Brief Title:`, `Protocol Number:`, `Phase: 3`, `US IND Number:`, `ClinicalTrials.gov ID:`, `EU CT Number:`); title-case rules; identifier patterns | `StudyIdentity`, `Identifier[]`, `Sponsor` | Phase in synopsis vs title text ("PHASE 3") |
| **Synopsis** | 1.1 | Parse as **label: value blocks** (the synopsis is a key/value layout, with an embedded objectives table) | `SynopsisFacts` (design summary, N, duration, arms as text) | Compared against body readers (Design, Objectives) |
| **Design/Arms** | 4.1 Overall design + arms table if present | Sentence-pattern parse (randomisation ratio, blinding, number of arms, periods), and the **arms table** (`Arm Title / Arm Type / Arm Description`, as seen in C4591048) | `Arm[]`, `Epoch/Period[]`, `Blinding`, `Stratification[]`, `PlannedN`, `Duration` | Arm count vs ratio vs synopsis |
| **Interventions** | 6.1 | Table reader for the **transposed intervention table** (names as columns; Type, Use, IMP/NIMP, Dose formulation, Unit strength, Dosage level, Route, Sourcing, Packaging, SRSD as rows — 12 × 3 in C5091017) | `Intervention[]` with dose/route/frequency/storage | Names vs arm names |
| **Eligibility** | inclusion + exclusion spans | **List grammar**: numbered `1.`, lettered `a.`, bullets (U+F0B7 normalised), group headings (`Age and risk factors:`), continuation lines across pages (furniture removed); parent–child items | `Criterion{id, category, group, text, children[]}` | Numbering must be contiguous per category; counts vs TOC/synopsis mention |
| **ObjectivesEndpointsEstimands** | objectives span (+ synopsis mini-table) | **Column clustering by word x-positions** (3 columns), row segmentation on tier labels (`Primary:`, `Key Secondary (Alpha protected):`, `Secondary:`, `Exploratory:`), header repeat detection across pages; layout strategies for Novo/Roche style (separate lists) | `Objective{tier,text}`, `Endpoint{tier,text}`, `Estimand{text}`, row-links | Each objective row has ≥1 endpoint; tier order; synopsis mirror |
| **SoA** (flagship) | `soa` span (Table 1, Table 2 …) | See 3.4 | `Epoch[]`, `Encounter[]`, `Activity[]`, `Mark[]`, `Footnote[]`, `Window[]`, `VisitType` | Marks vs Section 8 text; column count vs header |
| **Assessments** | section "Study assessments and procedures" (8.x) | Sub-section index (title, page span, verbatim text); instrument/keyword lexicon (PROMIS Fatigue 7a, EQ-5D-5L, C-SSRS…) | `AssessmentSection[]`, `Instrument[]`, `SpecimenType[]` | Every SoA activity should link to ≥1 section or be flagged |
| **Discontinuation** | section 7.x | Same list grammar as Eligibility | `DiscontinuationCriterion[]`, `WithdrawalCriterion[]` | Numbering contiguous |
| **Statistics/SampleSize** | section 9.x | Sentence patterns for N, power, alpha, interim analyses; analysis-set definitions | `SampleSize`, `AnalysisSet[]`, `InterimAnalysis[]` | vs synopsis N |
| **Narrative** | whole outline | Section tree with verbatim text per node, numbering, page anchors, tables as text blocks | `NarrativeNode[]` (feeds USDM NarrativeContent) | Character coverage: sum of node text ≈ document text minus furniture |
| **Abbreviations** | abbreviations appendix | Two-column table reader | `Abbreviation[]` | — |
| **AmendmentSummary** | front-matter "Summary of Changes" (107 of 204 have it) and separate "Summary of Change" PDFs | Row reader (Description / Rationale / Section) | `AmendmentChange[]` | Sections named exist in outline |
| **Vendors/Systems** | whole text, biased to sections 8.x/10.x | Lexicon + sentence cues (`central laboratory`, `interactive response technology`, `electronic diary`, named organisations) | `Organization[]` with role | Named in protocol only (never invented) |

**Reading modes.** Each reader has a deterministic mode (structure: tables, lists, key/value blocks) and, for semantic fields, an LLM mode on the same slot window (Section 3.8). Both emit the same records; the assurance layer (3.9) reconciles them. Structural readers (SoA grid, eligibility list grammar, objectives table columns, intervention table, narrative tree) are deterministic-first because the run showed regex fails on *semantics* but tables and lists have exact geometry; semantic readers (design, estimand attributes, vendors in prose, identity cross-check) are LLM-first with deterministic sanity validators.

**Tier system for graceful degradation** (recorded on each record and used as a confidence feature):
1. Tier 1 — template-anchored: slot resolved from bookmarks/registry, layout strategy matched.
2. Tier 2 — heading/contents-page fallback (no bookmarks) or generic layout strategy.
3. Tier 3 — LLM read on the routed slot window (the default for semantic fields; gap-fill for structural readers that returned `missing`).
4. Tier X — not found: emit `missing` finding; downstream gate decides whether the run may proceed.

### 3.4 The SoA reader in detail (the riskiest piece)

What real Pfizer SoAs look like (C5091017): **8 landscape pages** for Table 1, plus **Table 2** for the follow-up period; **18 grid columns**, a header of several rows (`Visit Identifier`, period spans such as `Treatment Period`/`F/U`, `Day`, `Visit Window (±days)`), row groups, then each activity row followed by **inline note text** that acts as its footnote.

Pipeline:
1. **Locate** by the `soa` span (both tables); classify pages landscape/portrait.
2. **Grid detection:** ruling-line based (PyMuPDF `find_tables`, pdfplumber lines) with a **word-position fallback** (cluster x-positions of words into columns) when lines are missing. Run engines in parallel; the existing `soa/grid_agreement.py` compares them.
3. **Header model with N rows** (replace today's fixed 3-row assumption in `soa/from_stitched.py`): recognise header rows by content (contains "Day", "Visit", "Screening", "±", "Window", period names), merge fragmented spans ("Treatment" + "Period"), forward-fill epochs.
4. **Stitch continuation pages** (exists: `soa/stitch.py`, `soa/continuation.py`): match repeated header signature; reconcile column count; hard-fail on ambiguity.
5. **Row model:** group rows (bold section rows) → category candidates; activity rows; **notes** captured per row or via footnote letters; conditions ("adult participants only", "if symptoms persist") become `Condition` records rather than being dropped.
6. **Mark reading:** existing `soa/rederive.py` (character-geometry mark detection, independent of the table parser). Accept `X`, `●`, `✓`, `X(a)`.
7. **Column semantics:** windows via existing `soa/timing.py`; visit typing from header text (`ET`, `Telemedicine`, `Unscheduled`, `Follow-up`); mode flags from notes ("may be performed as telemedicine visits").
8. **Multi-table merge:** Table 1 + Table 2 become one timeline or two, decided by a rule + finding.
9. **Optional VLM check** (Layer L) on a sample of cells and on the header; disagreement → `review`.
10. **Invariants:** every activity row has ≥1 mark or a note; every visit column has ≥1 mark; marks-per-column vs Section 8 mentions.

### 3.5 Layer 5 — The canonical Protocol Model (new, central)

A single typed model (pydantic/dataclasses) that both readers write to and the mapper reads from. It removes the current pattern where each extractor hands the assembler its own shape.

```
ProtocolModel
 ├─ identity: StudyIdentity, Identifier[], Sponsor, Phase, Title(s), Version(number,date,amendment)
 ├─ design: Arm[], Epoch[], Blinding, Randomisation, Stratification[], PlannedN, Duration, Parts/SubStudies[]
 ├─ population: Criterion[] (inclusion/exclusion), Demographics(age,sex), DiscontinuationCriterion[]
 ├─ interventions: Intervention[] (dose/route/frequency/storage), Comparator, ConcomitantTherapyRules
 ├─ objectives: Objective[] ─ Endpoint[] ─ Estimand[]   (with row links)
 ├─ schedule: Timeline[] {Epoch[], Encounter[], Activity[], Mark[], Footnote[], Window[], Condition[]}
 ├─ assessments: AssessmentSection[], Instrument[], Specimen[]
 ├─ organizations: Organization[] (role, evidence)
 ├─ narrative: NarrativeNode[]
 ├─ amendments: AmendmentChange[]
 └─ every element: Provenance{page,bbox,char_span,section_id,reader,tier,version} + findings
```

**Reuse trick:** to keep `assure/`, `audit/`, `review/` untouched, flatten records to field rows with structured keys (`eligibility.inclusion[3].text`, `schedule.activity[12].category`). Each row still becomes an `AssuredField`, so the review UI, audit store and confidence code keep working. Only the *extractors* change shape.

### 3.6 Layer 7 — USDM mapping

- **Primary path:** keep the data4knowledge `Assembler`/`TimelineAssembler` for everything it does well (identification, arms, epochs, encounters, activities, scheduled instances, timings). Extend `assemble/study.py` to feed it from the ProtocolModel.
- **Builder-level additions** (same pattern as today's `assemble/sites.py` and `soa.repair_timeline`), for items the assembler has no input for:
  - NarrativeContent / NarrativeContentItem (all sections, verbatim) — this was blank in our output.
  - Activity `description`, Encounter `contactModes`/`environmentalSettings`, `population.criterionIds` linkage, StudyIntervention dose/route, additional organizations and roles, stratification, discontinuation/withdrawal criteria.
  - **Non-native items** the downstream team asked for (activity category enum, encounter type such as `EARLY_TERMINATION`, `isUnscheduled`): use USDM **extensionAttributes** with a registered namespace URL, exactly the fallback the gap report itself proposed.
- **No fabricated fill-ins.** `assemble/sanitize.py` changes from "insert a default and log a finding" to "leave null and raise a blocking finding"; a *policy* setting decides whether a run with blocking findings still writes a draft file (clearly marked `incomplete`).
- **Codes:** biomedical concepts are only attached when a real code lookup succeeds (as today); otherwise left empty and reported. This stays a documented decision, not a silent gap.

### 3.7 Layer 8 — Gates, including the new downstream-readiness gate

Add `config/downstream_contract.yaml`, derived from the DDF gap reports:

```yaml
required:
  - {path: "study.versions[0].studyDesigns[0].eligibilityCriteria", min: 1}
  - {path: "…population.criterionIds",  equals_count_of: "…eligibilityCriteria"}
  - {path: "…objectives", min: 1, must_include_tier: primary}
  - {path: "…activities[*].category", coverage_min: 0.9}
  - {path: "…encounters[*]", require_any_of: [contactModes, environmentalSettings]}
  - {path: "…narrativeContents", min: 20}
recommended:
  - {path: "organizations[*]", roles: [central lab, eCOA, payments]}
```

The gate outputs a **"downstream readiness" score** (per D1–D4) alongside conformance. It answers the question Pfizer actually cares about: *can the next stage work from this USDM?*

### 3.8 Layer L — LLM readers (first-class, narrow, budgeted)

Revised after the real run: the LLM reads **semantic** fields in the first pass, on the slot's own window (a few pages, not the document). Interfaces (`llm/*`, `two_pass`, `verify`) are reused, with the call-contract fixes below.

| LLM reader | Slot window | Reads | Model role (right-sized) | Output |
|---|---|---|---|---|
| Identity check | title page + synopsis head | title, sponsor, phase, IDs, version (cross-check for TitleMeta) | `extract` (Sonnet 5.5) | scalars + quotes |
| Design semantics | 4.1 Overall Design + synopsis | arms, randomisation ratio, blinding, stratification, N, duration, parts | `extract` (Sonnet 5.5), alt member `extract_alt` (GPT-6 Sol) on disagreement | records + quotes |
| Estimand attributes | objectives table window | population, variable, intercurrent events + strategies, summary measure, per **table row** | `hard_reasoning` (Opus 5.5), `extract_alt` second | records + quotes |
| Vendors / systems in prose | sections 8.x / 10.x windows | named organisations and their roles | `extract` | records + quotes |
| Residue router | untyped sections only | slot label | `route` (Sonnet 5.5) | label |
| Verifier | `review` records only | quote ↔ value entailment | `verify` (Gemini 3.1 Pro, third family) | verdict |
| VLM check | SoA header and a sample of cells; schema figure | cell content, arm structure | `vision` (Gemini 3.1 Pro) then `vision_alt` (Sonnet 5.5) on disagreement | cells |

**Call contract (new, from the run's empty responses):**
- **Budget per shard**, sized to the expected record count (e.g. estimand JSON for 5 estimands needs far more than the current 1,600-token pass-2 cap).
- Read `finish_reason`; **empty, truncated or non-JSON output is an error**, retried once with a larger budget and, if it still fails, raised as a finding.
- **Never cache** empty, error or truncated responses (today an empty string is cached and replayed).
- Pass-1 reasoning and pass-2 JSON stay separate (existing two-pass design); reasoning models get an explicit output budget so thinking cannot consume the answer.
- Every call is logged with model id, prompt hash, tokens and cost estimate, so a rationed run can be budgeted before it starts.

Tier assignment follows the accuracy-first rule but stays right-sized: the many small window reads run on Sonnet 5.5; only estimands and amendments (hard reasoning) use Opus 5.5; no role uses a flagship-tier model unless a later evaluation shows the need.

### 3.9 Assurance rules learned from the run

1. **Source-independence groups.** Tag each candidate with its *source path* (`regex:full_text`, `regex:synopsis`, `table_reader`, `llm:<model>`). Members in the same group count as one vote. In the run, `labels` and `titlepage` were one wrong source counted twice.
2. **Sanity validators per field** (deterministic, cheap, cannot be outvoted):
   - Phase must equal the synopsis `Phase:` label and the title text "PHASE n"; strip template footer strings first.
   - Protocol ID must match the sponsor pattern and appear on the title page; template codes (e.g. `CT02-GSOP`) are rejected.
   - Sponsor must be an organisation name (no street address, no label bleed such as "Brief Title:").
   - Arms: 1–8 arms, names not in a stop list (dose fragments, `Date`, `IRBs/ECs`), count consistent with randomisation ratio.
   - Eligibility: each category numbered 1..N with no gaps; item count in a plausible range; no item may come from a contents page or amendment-history section.
   - Objectives: each row has an endpoint; estimand count equals the number of non-"Not applicable" cells.
3. **A candidate that fails a sanity validator cannot be `auto_accept`**, whatever its votes.
4. **Deterministic candidates never self-certify** (the current `arms_confidence = 0.8 ⇒ auto_accept` rule goes away).
5. **Row-based linking** for objective/endpoint/estimand; text matching is only a fallback and its failure is a finding, not a silent drop.
6. **Cascade guard:** if a dependent record set is dropped because its parent set failed (estimands because endpoints failed), raise one clear finding naming the root cause instead of eleven downstream warnings.

---

## 4. Mapping to what already exists

| Existing module | Action | Notes |
|---|---|---|
| `ingest/pdf.py`, `ingest/geometry.py` | **Extend** | Add line objects with font flags, furniture stripper, glyph normaliser, page classes. Keep char geometry (grounding depends on it) |
| `contracts.py` | **Extend** | Add `Provenance`, record types; keep `AssuredField` so review/audit stay intact |
| `sections/graph.py`, `sections/classify.py`, `config/section_taxonomy.yaml` | **Extend** | Add contents-page outline source; add slot registry + family profiles; keep title-keyword approach |
| `sections/fingerprint.py`, `config/protocol_families.yaml` | **Extend** | Add running-header fingerprint (CT02-GSOP etc.) |
| `sections/plan.py`, `sections/_ported_*.py`, `extract/windows.py` | **Simplify** | Windows = slot spans. The ported route tables can stay as a compatibility layer, not the primary router |
| `extract/metadata.py` | **Replace core** | Label parser survives inside `TitleMeta`; drop whole-document scan |
| `extract/design.py`, `eligibility.py`, `objectives.py` | **Replace** by readers | Old regex code retired; LLM `extract_llm_grounded` kept as Tier 3 |
| `extract/estimands.py` | **Keep**, feed from Objectives reader's estimand column | Deterministic estimands from the 3-column table first, LLM to fill intercurrent events |
| `extract/sites.py` | **Merge** into Vendors reader | Same idea, wider lexicon |
| `extract/amendments.py` | **Keep**, key by slots and add the summary-of-changes reader | Real chains for testing |
| `layout/*` adapters, `soa/stitch.py`, `soa/continuation.py`, `soa/grid_agreement.py`, `soa/rederive.py`, `soa/timing.py`, `soa/vision_cells.py` | **Keep and generalise** | Stitcher/grid agreement/mark re-derivation are the right ideas; remove 3-row header limit; add word-position grid fallback |
| `extract/soa/methods.py` | **Fix** | Always pass the SoA span pages; never "most activities wins" |
| `assure/*`, `audit/*`, `review/*` | **Keep** | Add invariant features and tier feature; records flattened to field rows |
| `assemble/study.py`, `assemble/soa.py`, `assemble/fallback.py`, `assemble/sites.py`, `assemble/estimands.py`, `assemble/amendments.py` | **Extend** | New builder-level enrichers for narrative, descriptions, modes, extension attributes |
| `assemble/sanitize.py` | **Change policy** | No fabricated defaults |
| `validate/gate.py`, `validate/repair.py` | **Extend** | Add downstream-readiness gate; repair loop can target readers, not only LLM re-extraction |
| `llm/*`, `extract/shards.py`, `llm/two_pass.py` | **Keep and promote** to first-pass Layer L | Add call contract (budgets, empty/truncated handling, no failure caching); shards become record-list aware; models now Sonnet 5.5 / Opus 5.5 / GPT-6 Sol / Gemini 3.1 Pro |
| `llm/cache.py` | **Fix** | Do not store empty, error or truncated responses |
| `assure/__init__.py`, `assure/verify.py` | **Extend** | Source-independence groups, sanity validators, no self-certifying deterministic members |
| `extract/domains.py`, `pipeline.py` | **Change** | Call grounded shards in the first pass; repair loop stays as escalation |
| `eval/*` | **Extend** | Add invariants and golden-set harness (Section 6) |
| `pipeline.py` | **Rewrite orchestration** | Reader graph instead of a fixed extractor sequence |

**New packages** (created only when they contain real code, per the repo's own rule): `intake/`, `readers/`, `link/`, `model/`, `mapping/`, `validate/downstream.py`, `config/families/`, `config/downstream_contract.yaml`, `eval/invariants.py`.

---

## 5. How this covers "any protocol" without pretending to

| Situation | How the design handles it |
|---|---|
| Pfizer CT02-GSOP (family A) | Full Tier 1 |
| Other CPT/M11 sponsors (Lilly, Alexion…) | Same family profile; verify by invariants |
| Shifted numbering (BMS, older Lilly, Sanofi) | Title/alias/cue-based slots; no numbers |
| Different vocabulary/structure (Novo, Roche, Amgen) | Aliases + alternative layout strategies; anything unreadable → `missing`, LLM gap-fill if enabled, else flagged for a human |
| No bookmarks | Contents-page then heading detection (Tier 2) |
| Scanned pages | Page classifier → OCR fallback; provenance marks "OCR" as a confidence feature |
| Multi-part / sub-study protocols | `Parts` in the model; readers run per part span (needs a rule for "Appendix: Sub-study A") |
| Future M11 documents | Add `m11` family profile from the M11 template; the tech spec drives mapper checks |
| Unknown template | `generic` profile with low confidence; nothing fabricated |

This gives **predictable behaviour on unfamiliar documents** (partial result + explicit list of what is missing), which is the honest meaning of "bulletproof". It does not guarantee correct extraction on formats we have never seen.

---

## 6. Testing and measurement that need no LLM

1. **Structural invariants on all 204 Pfizer PDFs (no labels needed).** Examples: every required slot resolves; bookmark coverage 100%; inclusion/exclusion numbering contiguous; objectives rows each have an endpoint; SoA visit count equals header column count; every marked activity has a name; sum of narrative text ≈ document text; no reader returned text from the running header or contents page. Report pass rate per invariant. This is a real, repeatable quality number today.
2. **Golden set:** the 8 hand-corrected "ideal" USDMs in the DDF folder (C5091017, C4601003, C4891001/002/006/023/024/026) as field-level labels, following the existing `eval/labels.py` freeze rules. Keep the verify studies untouched during reader tuning (mirror Pfizer's train/verify split) so we are not fitting to the test.
3. **Reader unit tests on frozen page ranges** (small PDFs extracted from real ones) for parsing behaviour only; accuracy is reported by `usdm4 eval`, not asserted.
4. **Downstream-readiness score** per study from the gate, and later "downstream recall" by running D1–D3 on our USDM versus the team's USDM.
5. **Mass regression:** re-run all invariants and the golden set on every change; a drop blocks the merge.
6. **Public multi-sponsor set** (the 23 usdm_data protocols) as the generalisation check for families B and C, and for no-bookmark files.

---

## 7. Build sequence (vertical slices, each usable and measurable alone)

Tagged per your workflow: switch models only at checkpoint boundaries; I will announce each boundary. Commit each task separately to `dev`. Ported logic is not given its own tests; code we author is.

### Checkpoint 1 — Foundations · **Sonnet, thinking low**
| # | Task |
|---|---|
| 1.1 | Intake gate (validity, page classes, bookmark/text-layer stats) and document identity from running header |
| 1.2 | Furniture stripper + glyph normaliser → `CleanDocument` |
| 1.3 | Slot registry config (`ct02_gsop.yaml`, `generic.yaml`) + resolver producing `SectionSpan`s + missing-slot findings |
| 1.4 | Invariants harness (`eval/invariants.py`) running on all 204 PDFs; publish the first pass-rate table |
| 1.5 | **LLM call contract**: never cache empty/error/truncated responses, read `finish_reason`, per-shard token budgets, one retry with a larger budget, per-call cost log (fixes the empty pass-2 responses seen in the run) |
| 1.6 | **Source-independence groups + sanity validators** in `assure/` (phase, protocol ID, sponsor, arms, eligibility, objectives); deterministic candidates can no longer self-certify (fixes "Phase 1 at 1.00 confidence") |
| 1.7 | Run the C1–C4 grounded shards in the **first pass** on slot windows (today they only run as repair-loop escalation) |

### Checkpoint 2 — Simple readers · **Sonnet, thinking medium**
| # | Task |
|---|---|
| 2.1 | Provenance + record contracts; flatten-to-field-row adapter for assure/review |
| 2.2 | TitleMeta + Synopsis readers (fixes phase/sponsor/identifier failures) |
| 2.3 | Interventions table reader (transposed table) and Arms table reader |
| 2.4 | Narrative tree reader + Abbreviations reader |
| 2.5 | Vendors/Systems lexicon reader; instrument lexicon |

### Checkpoint 3 — The hard readers · **Opus, thinking high**
| # | Task |
|---|---|
| 3.1 | Eligibility list grammar (numbered/lettered/bullet/group heading, page continuation, sub-items) |
| 3.2 | Objectives/Endpoints/Estimands 3-column reader (x-clustering, tier rows, header repeat) + alternative list-style strategy |
| 3.3 | SoA reader: N-row header model, word-position grid fallback, Table 1/Table 2 handling, row groups, notes/footnotes, conditions |
| 3.4 | Linkers: activity ↔ assessment section ↔ instrument ↔ category enum; visit typing and mode flags |

### Checkpoint 4 — Mapping and gates · **Sonnet, thinking medium**
| # | Task |
|---|---|
| 4.1 | ProtocolModel → `AssemblerInput`; builder-level enrichers (narrative, descriptions, modes, criterionIds, dose/route) |
| 4.2 | Extension-attribute namespace and category/encounter-type enums |
| 4.3 | `sanitize.py` policy change (no fabricated defaults) |
| 4.4 | `downstream_contract.yaml` + downstream-readiness gate |
| 4.5 | Version chain + AmendmentSummary reader on real chains (C5091017 v0→v2) |

### Checkpoint 5 — Assurance and generalisation · **Opus, thinking high**
| # | Task |
|---|---|
| 5.1 | Reader-vs-reader agreement (synopsis vs body, SoA vs Section 8) and invariant features into confidence; deterministic members can vote but never self-certify |
| 5.2 | Family profiles for B/C (BMS, Lilly-old, Novo, Roche) and contents-page outline fallback |
| 5.3 | OCR fallback for image-only pages; test on Roche/Lilly/Novo scans |
| 5.4 | Golden-set evaluation on the 8 ideal USDMs; calibration on real Pfizer fields; scoreboard refresh |
| 5.5 | Rationed LLM evaluation: repeat the C5091017 run on the new pipeline (1 study), then the remaining verify studies one at a time, comparing against the ideal USDMs and against the current baseline in Section 0 |

**Order of value:** 1 (especially 1.5–1.7, the cheapest big fixes) → 2.2 → 3.1/3.2 → 2.4 (narrative) → 3.3 (SoA) → 4 → rest. The deterministic parts of checkpoints 1–4 need no LLM; 1.7 and the LLM readers of Section 3.8 use a few narrow calls per study.

**Baseline to beat (C5091017 v2, Section 0):** phase wrong, 1 of 6 identifiers, 0 usable arms, 8/172 criteria (garbage), 0 of 6 objectives, 0 of 5 estimands, 2 of 15 encounters, no vendors, no narrative.

---

## 8. Risks and honest limits

- **Template dependence:** readers are strongest on family A. Mitigation: registry + strategies + invariants + explicit `missing`.
- **SoA remains the hardest:** oncology cycle-based schedules, conditional branching and repeat cycles are hard for every tool. Our aim is a correct core grid plus loud flags for what we could not model.
- **Overfitting to the 8 golden studies:** mitigated by writing readers against the *template*, tuning on train studies only, and keeping verify studies and the public corpus untouched.
- **M11 outline not yet imported:** I could not fetch the M11 template's section list from the web pages; download it from EMA/FDA.
- **Assembler limits:** the upstream data4knowledge assembler cannot express several items; the design already routes those through `Builder` and extension attributes, but each has to be validated against the d4k/CORE gates.
- **GPL-3.0 (`usdm4`) and AGPL (MinerU weights)** decisions stay recorded, as before.

---

## 9. Decisions needed from you

1. Approve **"records, not scalars"** as the new extraction contract (this is the biggest structural change).
2. Approve **no fabricated defaults** (blocking finding instead), and choose the run policy: block, or write a draft marked `incomplete`.
3. Should the **first target be Pfizer-only (family A) with hooks for others**, or do you want family B/C support in the first release?
4. Extension attributes for category/encounter type: OK to use a project namespace, or should it be agreed with the downstream team first?
5. Do you want me to turn this into a phased implementation plan in `DEVPLAN.md` format and start Checkpoint 1?

---

## Evidence used
- Local: bookmark statistics over 204 Pfizer protocols (9 shared top-level sections in 197, inclusion/exclusion/objectives in 204/204, SoA in 203); Pfizer CT02-GSOP protocol template heading outline (184 headings, 48 tables); real page samples of Synopsis, Objectives table, Inclusion list, Intervention table and SoA footnotes from C5091017; section-title survey of 23 public protocols from 10 sponsors; repo code (`sections/graph.py`, `extract/shards.py`, `extract/soa/methods.py`, `assemble/*`, `soa/*`).
- Web: [ICH M11 (EMA)](https://www.ema.europa.eu/en/ich-m11-guideline-clinical-study-protocol-template-technical-specifications-scientific-guideline) · [FDA M11 notice](https://www.federalregister.gov/documents/2026/05/22/2026-10295/m11-clinical-electronic-structured-harmonised-protocol-cesharp-international-council-for) · [ECA on final M11](https://www.gmp-compliance.org/gmp-news/final-ich-m11-cesharp-guideline) · [CASRAI M11 guide](https://casrai.org/guides/ich-m11-clinical-trial-protocol-template) · [TransCelerate CPT FAQ](https://www.transceleratebiopharmainc.com/wp-content/uploads/2018/11/CPT_ImplTK-CPT-FAQs_V004.pdf) · [ProtocolMiner](https://esmed.org/MRA/mra/article/view/7362) · [TimeTox](https://arxiv.org/pdf/2603.21335).
