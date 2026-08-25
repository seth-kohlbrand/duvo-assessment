---
name: module-deep-audit
description: Audit every data-rendering and action surface in an application module, including secondary views, summaries, exports, attribution, empty states, and hidden workflow paths.
---

# Module Deep Audit

Inventory all user-visible surfaces before judging the module: routes, tabs, tables, cards, charts, dialogs, detail views, searches, exports, notifications, and background refreshes.

For each surface, trace the component, data source, tenant source, cache key, transformation, write action, authorization control, error state, empty state, and output destination. Confirm derived values come from deterministic server-side logic when they represent business rules.

Exercise primary and secondary paths with real inputs. Compare totals and detail rows, exported and on-screen values, fresh and cached sessions, allowed and denied roles, two distinct tenants, empty datasets, and failure responses. Flag mock data, hardcoded identifiers, client-only calculations, silent failures, stale caches, and general navigation that loses the target record.

Report findings by severity with exact evidence, affected surfaces, reproduction steps, and missing coverage. Do not infer module-wide correctness from the primary tab alone.
