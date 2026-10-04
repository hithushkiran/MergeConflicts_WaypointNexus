# T10 — first UI slice (in progress)

Branch: `feat/T10/Hithush`. T01–T09 were treated as completed. No architecture, backend contracts, database schema, or business rules were redesigned.

## Implemented

- Shared role-aware shell, navigation, account context, responsive mobile menu, skip link and workspace focus; reusable headings, cards, buttons, facts, alerts and status labels.
- Store S01–S03 order list, shipment creation, server-confirmed submission and status/detail views. Existing receipt workflow is reachable from Deliveries; account context is read-only.
- Existing order eligibility/list/create and store issue APIs supply displayed values. A submission retry retains its request key while its payload is unchanged.
- Exact Figma SVG assets are served locally, preserving their intrinsic geometry. Unsupported ETA, vehicle assignment, notification, product catalog, profile editing and live operational data are not fabricated.

The Figma design-to-code workflow supplied the store frames `61:1020`, `61:1409`, `61:1736`, `61:1950`, and `67:2307`. Available API fields constrain S03: status and recorded shipment details are shown, while pre-delivery ETA, assigned vehicle and deferral timing are explicitly unavailable. Counters describe the returned order list rather than claiming complete history.

## Verification — 2026-10-04

- Existing isolated Compose project `waypoint-t09` started successfully before edits: database/API healthy, API readiness successful, web available at `http://localhost:5174/`. Its web image was updated and started with `up -d --no-deps web`. A redundant dependency rebuild was cancelled before replacing the unchanged API; final checks confirmed API/database healthy and `/ready` returning `ready`/`ok`. No database volume was reset or removed.
- Frontend typecheck, lint, 21 tests across 5 files, and production build passed. A sandbox-only Vite configuration read denial was resolved by rerunning the checks with approved filesystem access. Tests cover role navigation boundaries, accessible shell labels, store loading presentation and readable status meanings, alongside the existing offline/receiving regressions.
- API golden-path runner passed against the isolated Compose stack for planning date `2026-10-08`: initial 500 kg, revised 480 kg manifest V2, hold/stale-version rejection, ordered driver delivery, idempotent sync, store receipt and dispatcher issue closure. Local evidence: `.t09-verification/t10-regression.json` (not committed).
- Browser store flow created a real synthetic order `WN-20261004-9EAAEC90` with 3 units, 30 kg and 0.3 m³. Its confirmation displayed the server-issued reference, timestamp and quantities; a subsequent reload listed the persisted order. Its detail view retained those values, and Deliveries displayed the existing V2 receipt/issue record.
- At desktop 1440×1136 and narrow 390×900 viewports there was no horizontal page overflow. The narrow orders table has its own scroll region, and mobile navigation opens independently. Visible Figma SVGs loaded successfully at their intrinsic proportions.

Browser checks are a store-slice smoke test, not full T10 acceptance. Automated tests do not establish pixel-perfect parity or exercise every role's browser workflow.

## Remaining work / blocker

T10 is **not complete**. Continue in the documented order: dispatcher D01–D04/G02, loader L01–L04, driver R01–R04, then receipt S04/S04B/S05. The existing operational workspaces remain functional but retain temporary content styling inside the new shell. Full role-specific responsive, keyboard, empty/error, offline and visual comparison gates remain open.

The connected Figma account returned its MCP tool-call quota limit during reference retrieval. Store and dispatcher contexts were obtained, but loader/driver references are incomplete. Restore connected Figma tool access before completing the affected design work; do not invent missing visual requirements or bypass the quota. Dispatcher is the next independent slice with retrieved references. Optional operational panels remain T11, not prerequisites for this slice.

No commit or push was performed.
