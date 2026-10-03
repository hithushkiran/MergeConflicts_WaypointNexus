# Waypoint Nexus work queue

This folder is the source of truth for unfinished project work. The old single-file checklist is preserved as [roadmap.md](roadmap.md); this index makes it usable as an ordered queue for people and coding agents.

## Start here

1. Read the repository [README](../README.md), [foundation handoff](../FOUNDATION_HANDOFF.md), and relevant ADRs.
2. Check the **Current focus** section below and inspect the code before choosing a task. The roadmap describes the intended product; it is not evidence that a feature is missing or present.
3. Claim one task in the status board, state its acceptance criteria and files/modules likely to change, then implement only that task and its dependencies.
4. Update the board and task checklist with evidence (commands run, outcome, and any blocker) when done. Do not mark work complete based only on code existing.

## Current focus

The repository documents FND-01/FND-03 foundation work, and the API currently exposes health/readiness endpoints. Authentication, planning, and the business workflows are explicitly described in the root README as not implemented. The roadmap has many unchecked foundation tasks that may already be complete. Reconcile each candidate against the current code and tests before changing it; keep the README, handoff, and this board consistent when evidence changes.

T01 is complete. Start T02 (authentication, authorization, and API contracts), following the roadmap requirements and acceptance gates. Do not assume every unchecked roadmap item is still open.

## Order and gates

Follow roadmap dependencies, prioritizing the end-to-end path:

`store order → plan → dispatcher publish → load/shortfall resolution → driver delivery → offline sync → store receipt`

P0 work and its acceptance gate must be complete before starting dependent P0 work. P1 work follows a working P0 path; P2 is optional polish. A failed relevant check blocks dependent tasks until fixed. The roadmap's phases and gates are the detailed requirements; this index does not override project architecture or ADRs.

## Agent coordination

- One owner per task at a time. Parallel work is allowed only for tasks with non-overlapping files and explicit interface agreements.
- Before editing, inspect current implementation, tests, migrations, and git status. Preserve unrelated user changes.
- Do not fabricate behavior, use hard-coded demo results as implementation, bypass validation, or use the client as the authoritative store.
- For stateful workflows, define and enforce valid transitions server-side. PostgreSQL is authoritative; realtime is advisory. Offline commands must persist and be idempotent.
- Keep changes scoped. Add or update relevant tests as part of implementation; report checks run and results. Do not claim a check passed if it was not run.
- Never reset/delete databases, volumes, or user data without explicit authorization. Document any destructive command as a human-operated step.
- If blocked, record the precise blocker, evidence, and smallest decision/input needed. Then work on an independent task only if its dependencies and files are clear.

## Status board

| ID | Workstream | Status | Owner | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| T01 | Reconcile foundation and development setup | done | Codex | — | Repaired the broken Buildx symlink to `/usr/libexec/docker/cli-plugins/docker-buildx`. Added `httpx2` as the backend dev TestClient dependency and select uvloop for TestClient when available. `docker compose up --build -d` starts db/api/web; API `/health` and `/ready` both return success, with database readiness confirmed. Backend pytest: 8 passed, 1 skipped (optional PostgreSQL integration URL unset). Frontend test (1), typecheck, ESLint, and production build pass. |
| T02 | Authentication, authorization, and API contracts | open | — | T01 | |
| T03 | Store order workflow | open | — | T02 | |
| T04 | Planning and eligibility/allocation | open | — | T03, T02 | |
| T05 | Dispatcher review and plan publication | open | — | T04 | |
| T06 | Loader, shortfall, hold, and revised manifest | open | — | T05 | |
| T07 | Driver delivery and proof of delivery | open | — | T06 | |
| T08 | Offline cache, outbox, and idempotent sync | open | T07 | |
| T09 | Store receipt and complete golden path | open | T08 | |
| T10 | Security, reliability, responsive UX, and P1 operations | open | T09 | |
| T11 | Fresh install, deployment, demo, and submission | open | T10 | |

Statuses: `open`, `in progress`, `blocked`, `done`. Update owner/status/evidence in the same change as task progress. Split a row into smaller IDs if it is too large for one reviewable change; retain dependency order.

## Task handoff template

```text
Task ID / title:
Outcome:
In scope:
Out of scope:
Dependencies:
Acceptance criteria:
Relevant paths / interfaces:
Checks to run:
Owner:
```

Completion note:

```text
Status: done | blocked
Changes:
Acceptance evidence:
Checks run and results:
Follow-up / blocker:
```

## Detailed checklist

See [roadmap.md](roadmap.md) for phase-level requirements, specific workflow gates, and the demo/submission checklist. Check off an item only after implementation and verification; update this status board with the corresponding evidence.
