# Visual QA gate

Every draft or implemented view is answered against these rows before it is
shown as approved. Each row is PASS, FAIL or N/A **with evidence** — a
`file:line`, a rendered observation at a named viewport, or a printed test
count. A row answered from memory of how the view "should" look is not
answered.

A draft that is attractive and fails one row is not approved.

Rows cite `CLAUDE.md`, `.claude/odoo-agent-rules.md` or the Odoo 19 doc kit at
`.agents/Odoo_19_Developer_LLM_Kit/`. Read the authority, not a paraphrase.

## 1. Layering — CLAUDE.md

| # | Check |
|---|---|
| L1 | Nothing under `addons/` or `odoo/` is hand-edited. Both are upstream plus a generated transform; a change that seems to need one belongs in `afenda/addons/<module>/` as an inheriting module |
| L2 | Brand text, wordmark, logo and module icons changed through `afenda/tools/` rules, never by editing rendered output. A rule change was reviewed with `corpus diff` before it was applied |
| L3 | View changes are `xpath` inheritance against a named `xml_id`, not a copied-and-edited view |
| L4 | New files live in a module that declares them — assets in the manifest's bundles, not loaded by a side channel |
| L5 | `patch()` is absent, or its use is justified against the documented extension points that were tried first |

## 2. Surface truth — Odoo's own vocabulary

| # | Check |
|---|---|
| S1 | Every overlay or region names what it actually is: a view type, `ControlPanel`, `Dialog`, the notification service, `ActionMenus`, Chatter or systray. No invented surface, and nothing named after a domain object |
| S2 | The view type matches the job — `list` for records, `kanban` for cards with a pipeline, `pivot`/`graph` for aggregates, `form` for one record. Editable rows use the list view's `editable`, not a bespoke grid |
| S3 | At most one modal task at a time; a `Dialog` does not open another `Dialog` except where Odoo itself does |
| S4 | Heavy secondary work is its own action and breadcrumb, not a deeper overlay |
| S5 | A command appears once in its natural place — toolbar, cog menu, row, context menu — and reads the same wherever it repeats |

## 3. Hierarchy and density

| # | Check |
|---|---|
| H1 | Record identity, state and the active company are each obvious; state visible but not dominant |
| H2 | The work surface is primary; Chatter and auxiliary panels do not compete with it |
| H3 | No card soup: no card inside a card, no row of decorative stat tiles standing in for a register |
| H4 | Borders and spacing carry structure; shadow, radius, gradient and glass do not |
| H5 | Density moves geometry, not reading size |
| H6 | Accent spent on primary action, link, active nav, selection and focus — not sprayed |

## 4. Lists, numbers and money

| # | Check |
|---|---|
| T1 | Relational and financial rows stay a table at every viewport; narrow widths scroll inside their own region rather than becoming cards |
| T2 | Paired amounts (debit/credit, ordered/received) stay in their columns and their relationship stays visible |
| T3 | Amounts right-aligned in tabular numerals, with the aggregates the register actually has (`sum`, `avg` on the field) |
| T4 | Money uses the monetary widget with its currency field; no precision invented that `decimal_precision` would not give |
| T5 | Hierarchy uses a real hierarchical view, not a flat list with indentation faked in a label |

## 5. Scope and domain truth

| # | Check |
|---|---|
| D1 | The active company is stated where it matters; restricted scope is stated, not inferred |
| D2 | No control implies it can widen scope or authority. `groups=` on a field is visibility, never security — the record rule and the access CSV are |
| D3 | No invented state, permission, model or workflow step |
| D4 | Business dates read as dates, not timestamps, where the field is a Date |
| D5 | A mock fakes no session, company, route or ORM call |

## 6. Responsiveness

| # | Check |
|---|---|
| R1 | Same meaning at every breakpoint: a surface may change presentation, never its job |
| R2 | No horizontal page scroll at 360px; tables scroll inside their own region |
| R3 | The shell and navigation are Odoo's, not an invented parallel mechanism beside it |

## 7. Accessibility

| # | Check |
|---|---|
| A1 | Landmarks uniquely labelled; no duplicate hidden responsive landmarks |
| A2 | Heading order correct; tables have an accessible name |
| A3 | Every control has an accessible name and a visible focus state |
| A4 | Keyboard reaches every command; the active nav item is marked as current |
| A5 | State never colour-only — a shape, an icon or a label carries it too |

## 8. Proof

| # | Check |
|---|---|
| V1 | Seen rendered in a real browser at a wide and a narrow viewport, on port 8169 — not inferred from the diff |
| V2 | The narrowest test that exercises the edit was run and its **printed count** quoted. `exit 0` is not evidence: a suite that collected nothing also exits 0 |
| V3 | A test class that does not subclass Odoo's `BaseCase` is silently dropped — if a new test was added, it was confirmed collected |
| V4 | `odoo-reviewer` has seen the diff, if anything under `afenda/addons/` changed |

## Verdict

```
Visual QA: <target> — <route taken> — <viewports seen>
FAIL: <row ids, one line each with evidence>
PASS: <row ids>
N/A:  <row ids, with why>
Verdict: APPROVABLE | NOT APPROVABLE
```
