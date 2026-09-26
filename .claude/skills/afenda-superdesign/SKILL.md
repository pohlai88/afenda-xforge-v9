---
name: afenda-superdesign
description: "Use when a UI request in afenda-xforge-v9 asks to design, redesign, restyle, 'make nicer', 'make premium', 'make it work on mobile', or visually review a view, a form, a list, the web client shell, an icon set or the palette — before any UI code is edited or any artwork is generated. Reach for it especially when the request is small enough to tempt a full redesign, large enough to tempt editing one view and calling it global, names a design tool that may not be installed, or invites inventing a drawer, panel or view type that Odoo's vocabulary does not have."
metadata:
  upstream: "adapted 2026-09-24 from .claude/skills/afenda-superdesign in afenda-xForge-v8. That repo is a greenfield Next.js/Base UI frontend; this one is an Odoo 19.0 fork with no package.json. Every authority the original cited (docs/architecture/frontend-pdr.md, platform-laws.md, ADR-0012, PDR-D6a..D34) and all seven agents it dispatched (frontend-architect, ui-foundation-engineer, view-engine-engineer, screen-engineer, ui-reviewer, browser-verifier, ui-polish-engineer) are absent here, as are /cui, /rui, /iui and .HITL. The route table, context ladder, five-part prompt, QA gate and red flags are kept because they are repo-independent discipline; every citation is rebound to CLAUDE.md, .claude/odoo-agent-rules.md, the Odoo 19 doc kit and the six odoo-* agents that actually exist."
---

# Afenda Superdesign

**Spend design effort only where a real design decision exists.**

Most UI requests here are already answered by Odoo 19's own view vocabulary and
by `CLAUDE.md`'s layering rules. The expensive part is noticing that before
editing anything; the dangerous part is producing something that quietly
contradicts it — or worse, editing a tree that must stay pristine.

"Superdesign" in this repository is **this workflow, not a vendor product.**
There is no Superdesign CLI, no `.superdesign/` state, no Shadcn Studio, and no
`/cui`, `/rui` or `/iui` commands — this repo has no `package.json` at all. The
canvas is the running Odoo web client on port 8169. If a request names
"Superdesign", say in one line that it resolves to this workflow and continue.
Never claim a canvas, draft or URL that no tool returned.

The design surface that **is** installed and generative is the brand and icon
pipeline under `afenda/tools/` — `rules.py`, `rebrand.py`, `brand_images.py`,
`app_icons.py`, `xforge_icons*/`. Artwork changes go through it, never by
editing a rendered PNG or SVG.

## Authority — read these, carry none of them

| Question | Authority |
|---|---|
| Which tree a change belongs in; what must never be hand-edited | `CLAUDE.md` — root `odoo/` and `addons/` are upstream plus the generated rebrand transform |
| Binding rules every `odoo-*` sub-agent also reads | `.claude/odoo-agent-rules.md` |
| Any Odoo 19 API, view attribute, widget, registry or hook | `.agents/Odoo_19_Developer_LLM_Kit/` — start at its `AGENTS.md` and `llms.txt` |
| What the kit omits (autodoc docstrings) | the source itself: `odoo/orm/`, `odoo/http.py`, `odoo/addons/base/models/`, `addons/web/static/src/` |
| Module layout, manifest keys, the access-CSV rule | `.claude/odoo-agent-rules.md` |
| Whether a test run proved anything | `superpowers:verification-before-completion` — read the printed count, never `exit 0` |
| Brand text, wordmark, logo, module icons | `afenda/tools/` rules plus the corpus golden test; never the rendered output |
| Run steps, ports, the layout | `afenda/README.md` |

Cite the file you relied on in every design note. Do not paste its content into
this skill or into a new guidance document — a second copy of a rule is the
thing that drifts.

**Corrections worth keeping**, because a session primed by generic web-app
design advice will reach for the left column:

| Tempting reading | This repo |
|---|---|
| Restyle by editing `addons/web/static/src/scss/...` | `addons/` and `odoo/` are pristine upstream plus a generated transform. Style through a module in `afenda/addons/` that inherits, or through primary variables |
| A "drawer" / "side panel" surface | Odoo's vocabulary is closed: view types, `ControlPanel`, `Dialog`, notification service, `ActionMenus`, Chatter, systray. A drawer is a *presentation* of one of these on a narrow screen, never a surface of its own. Naming a job "drawer" means naming which one it actually is |
| One table component for everything | `list`, `kanban`, `pivot`, `graph` and `tree`/hierarchy are separate view types with separate jobs. Editable rows are a list view's `editable` attribute, not a bespoke grid |
| `patch()` the component and move on | Walk the documented extension points first — registries, services, hooks, `t-inherit` templates, view `xpath`. `patch()` is the last resort and is reviewed as such |
| `groups=` on a field is security | It is visibility. Security is ir.model.access CSV plus record rules. A design that *implies* wider authority than `viewScope` allows is refused in the design |
| A new view type for a new screen | Almost never. The existing types plus `xpath` inheritance cover it; a new type is a SYSTEM change |
| Change the brand blue by editing a rendered asset | Brand identity moves through `afenda/tools/` rules, reviewed with `python -m afenda.tools.corpus diff`, applied once |
| Bigger body text in comfortable density | Density moves geometry, not reading size |

Product character: quiet, dense, precise enterprise software. Borders, spacing
and type over shadow; restrained radius; semantic colour; tabular numerals;
status never colour-only. No card soup, glass, marketing gradients, icon
rainbows or decorative motion. The auth-page crystal bear is the tenant's signature
(`docs/superpowers/specs/2026-09-26-tenant-signature.md`): never recolour, regenerate,
replace or decorate it (pinned by `afenda/tools/tests/test_tenant_signature.py`).

## Route the request first

Ask one question before anything else: **could a competent implementer produce
the result without making a visual-composition judgement?** If yes, DIRECT.

| Route | Observable predicate | What happens |
|---|---|---|
| **DIRECT** | A token, spacing, label, alignment, a widget Odoo already picks, or a responsive bug whose intended behaviour is known | Edit real code; verify in the browser at 8169. **No design round** |
| **WARM** | An approved direction already exists for this exact target — a prior artifact this repo's owner reviewed | Refine that artifact. Exact edits are edits; judgement goes through a fresh pass against it. Do not re-derive what the review settled |
| **DESIGN** | Meaningful redesign of a view that renders today, no approved direction | First reproduce the current view faithfully, then refine it. Two steps, not one |
| **NEW TARGET** | The view does not exist, but Odoo's vocabulary and a sibling module cover its grammar | No fake baseline. Nearest sibling + the view types it needs + the domain constraints → one draft |
| **SYSTEM** | Changes a cross-product pattern: the shell, the palette, density, icon vocabulary, a view type, or several modules at once | Deliberate comparison of directions, and it almost always means changing `afenda/tools/` rules or a base theme — never one view edited and assumed global |

"Premium", "exciting", "modern" name no composition problem. Ask which view and
which friction, or treat it as SYSTEM. Never answer it by editing a stylesheet
directly.

A request that asks a control to do something authority forbids — a selector
that "opens any record", a view that reveals restricted rows — is refused in
the design itself: the control offers only what the record rules already
permit. Say so; do not draw the widening.

## Context ladder — load the lowest rung that answers

- **L0** the view as rendered — label, colour, spacing, a visible element
- **L1** the target's own source — the view XML, its SCSS, its component
- **L2** target + the Odoo component or view type it builds on
  (`addons/web/static/src/...`) + the kit page governing it
- **L3** cross-module architecture — only for SYSTEM

Climbing to L3 because it feels thorough is the cost this skill exists to cut.

## The design brief — five parts, this order

Every design pass, and every brief to a sub-agent, is exactly:

```
TARGET        module, view type and xml_id, the viewport(s)
PRESERVE      business semantics and contracts: record rules, company scope,
              monetary precision, the view types already in place, the
              pristine trees
IMPROVE       the one unresolved composition problem
DO NOT INVENT a new view type, a second shell or palette, a theme, widened
              scope, fake statuses or permissions, or an edit to addons/ or odoo/
ACCEPTANCE    observable criteria a reviewer can check, including the
              narrow-viewport behaviour and the test command with its
              expected printed count
```

## Tool failure budget

When a tool a request names is not installed — a design generator, an MCP
server, a preview service — try it once, retry once only on a transient error,
then stop and say so plainly. Never claim a draft, canvas or URL that was not
returned. Keep the analysis and the five-part brief in the report; an outage
must not erase them. If the job can be finished from Odoo's own vocabulary,
route it DIRECT and say so.

## Approval and handoff

A DESIGN, NEW TARGET or SYSTEM draft is shown before implementation, unless the
owner said to skip design. Every draft passes the gate in
`references/visual-qa-gate.md` first — a draft that looks good and fails a row
is not shown as approved.

Dispatch the agents that exist here rather than a general-purpose stand-in:

| Lands in | Owning agent |
|---|---|
| View XML, xpath inheritance, SCSS, theming, menus, icons, the afenda_brand look | `odoo-ui-dev` |
| Owl components, registries, services, hooks, JS fields and views, HOOT tests | `odoo-frontend-dev` |
| Models, ORM, security files, actions, controllers, reports, manifests | `odoo-backend-dev` |
| An Odoo 19 API fact or a citation, before writing code | `odoo-docs-librarian` (read-only) |
| Reviewing a UI diff against the kit's rules and this skill's gate | `odoo-reviewer` (read-only) |
| Running a suite and reporting the printed count | `odoo-test-runner` |

`odoo-reviewer` runs before committing anything under `afenda/addons/`. It is
read-only and catches the layering and security mistakes least visible in a
diff.

One owner per file: several sessions share this worktree and therefore one
`.git/index`. Agents that share no files may run in the same turn; two that
touch the same file never do.

## Done means

- seen rendered, at a wide and a narrow viewport, in a real browser — not
  inferred from the diff;
- the QA gate's rows answered with evidence;
- the narrowest test that exercises the edit run, and its **printed count**
  quoted, never `exit 0`;
- deliberate deviations from the approved draft named;
- the route taken named in the report, so a DIRECT that should have been
  DESIGN (or the reverse) is visible.

## Red flags — stop and re-route

- Changing the crystal bear (`crystal_bear.svg`, `auth_bear.xml`) for a design request: it is
  the tenant signature; design around it.

- Editing anything under `addons/` or `odoo/` to change how something looks.
- Editing a rendered brand asset instead of the rule that generates it.
- Designing anything for a padding, token or label change.
- A panel named after a domain object (`EmployeeDetailsDrawer`).
- Relational rows turned into cards on a phone.
- A single view redesigned to settle a cross-module question.
- A mock showing an action the user's record rules would refuse.
- A draft, canvas or URL reported that no tool returned.
- `patch()` reached for before the documented extension points.
- "Tests pass" without the printed count.
