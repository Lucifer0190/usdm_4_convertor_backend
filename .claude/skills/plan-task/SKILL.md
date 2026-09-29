---
name: plan-task
description: Plan a non-trivial change before coding. Explores the code, lists affected files, risks and acceptance criteria, then records the approved plan in docs/ai.
argument-hint: "[task description]"
---

Plan: $ARGUMENTS

1. Read `docs/ai/PLANS.md`, `CLAUDE.md`, and the relevant rule files. Explore only the code this task touches.
2. Draft a plan using `docs/ai/SPEC-template.md`: goal, context, constraints, scope, acceptance criteria,
   verification (real commands from CLAUDE.md), non-goals. Name affected files, risks, and dependencies.
   Reuse existing utilities; list the ones you found.
3. Split the work into small slices. Tag each checkpoint with the Claude model and thinking level to use
   (cheap mechanical work: Haiku/Sonnet low; subtle design or algorithms: Opus high), group same-tier slices,
   and say where the user should switch models.
4. Present the plan and STOP for approval. Do not write code.
5. After approval: pick the next free `AI-NNN` ID, add one line to `docs/ai/PLANS.md` under Now or Next
   (`ID | title | - | plan file`, no prose), and save the plan as `docs/ai/plans/AI-NNN-<slug>.md`.
   Keep PLANS.md within its caps (Now max 3, Next max 7, Later max 15, file max 60 lines).
