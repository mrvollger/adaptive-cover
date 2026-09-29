# Architecture decision records

An ADR records one design decision: the problem, the choice, and what follows from it. The full design and the phase plan are in [`docs/refactor_plan.md`](../refactor_plan.md). The ADRs keep the decisions short and stable, so you can cite one in a PR or a code comment.

| ADR | Title | Status | Date | Delivered in |
|---|---|---|---|---|
| [0001](0001-house-entry-and-window-subentries.md) | One house entry with window subentries | Accepted | 2026-09-28 | P7 (v2.0.0), cleanup P8 |
| [0002](0002-one-cover-per-window.md) | One cover per window | Accepted | 2026-09-28 | P3 (v1.16.0) |
| [0003](0003-settings-precedence.md) | Settings precedence and the one-time vs recurring rule | Accepted | 2026-09-28 | P5 (v1.18.x), UI in P6 |
| [0004](0004-refactor-contract-v2.md) | Refactor contract v2, behavior-tier ledger and mutation gate | Accepted | 2026-09-28 | P0 (v1.14.0), then every release |
| [0005](0005-drop-pandas-numpy-pytz.md) | Drop pandas, numpy and pytz | Accepted | 2026-09-28 | P2 (v1.15.x) |

## Writing a new ADR

1. Copy the format of an existing ADR: title, status, date, context, decision, consequences.
2. Use the next free number and a short kebab-case file name, for example `0006-some-decision.md`.
3. Add a row to the table above in the same PR.
4. Do not rewrite an accepted ADR to change the decision. Write a new ADR and set the old one to "Superseded by NNNN".
