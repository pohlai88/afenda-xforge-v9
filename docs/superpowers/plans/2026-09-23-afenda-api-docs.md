# AFENDA generated documentation (`afenda_api_docs`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve `/docs` from a new addon that generates an OpenAPI 3.1 reference from the live Odoo registry and renders authored guide pages, with Odoo identity aliased to AFENDA automatically in prose and never in wire values.

**Architecture:** One module, `afenda/addons/afenda_api_docs`, takes the `/docs` route over from `afenda_brand`'s placeholder. An `aliasing` module holds the prose/wire split. An `openapi` module walks the registry, delegating the callable-method rule to Odoo's own `get_public_method` and field schemas to `fields_get()`. Guides are authored in Markdown and converted to QWeb at build time by `afenda/tools/build_docs.py`. Redoc is vendored for rendering.

**Tech Stack:** Odoo 19.0, Python 3.11, OpenAPI 3.1, Redoc (MIT, vendored), QWeb, `markdown` (build-time only).

**Spec:** `docs/superpowers/specs/2026-09-23-afenda-docs-generation-design.md`

## Global Constraints

- Python only from `.venv/Scripts/python`. Never install into the global interpreter.
- Server port 8169, test port 8179, PostgreSQL `127.0.0.1:5444`, database `afenda`.
- Root `odoo/` and `addons/` are pristine upstream: **never hand-edit them.** All work in this plan is under `afenda/`.
- Stage explicit paths. **Never `git add -A`** — the rebrand can leave ~19,000 modified files under `addons/` and `odoo/`.
- Commit subjects use Odoo tags: `[ADD]`, `[FIX]`, `[IMP]`.
- `git status` on the whole tree takes about two minutes. Always scope it: `git status -- afenda docs`.
- The identity scanner must not rise above `BASELINE` (currently **10838**) in `afenda/tools/scan_identity.py`. Run `.venv/Scripts/python -m afenda.tools.scan_identity` after any task that adds user-visible text; it exits 0 while holding.
- **A green exit code is not evidence.** `afenda/odoo.conf` sets
  `log_level = warn`, and the `N failed, M error(s) of K tests` line is emitted
  by `odoo.tests.result` at INFO. A *passing* run is therefore completely
  silent, and exit code 0 cannot distinguish "all tests passed" from "zero tests
  were collected". Always pass `--log-handler=odoo.tests:INFO` and reconcile the
  printed count against the number of `def test_` methods you expect. Two
  separate sessions were misled by this in one day.
- Module test command (the env prefix stops MSYS mangling `/module`):

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda \
  -u afenda_api_docs --test-enable --test-tags "/afenda_api_docs" --stop-after-init --http-port 8189 \n  --log-handler=odoo.tests:INFO
```

- Fast, database-free tests: `.venv/Scripts/python -m unittest discover afenda/tools/tests`.
- **Coordination:** `afenda/addons/afenda_brand` is owned by another active session. Task 1 removes two files from it. Confirm with that session before starting Task 1.

## File Structure

| File | Responsibility |
| --- | --- |
| `afenda/addons/afenda_api_docs/__manifest__.py` | Module metadata, deps, data, assets |
| `afenda/addons/afenda_api_docs/aliasing.py` | Prose-vs-wire brand aliasing. No Odoo imports; pure text |
| `afenda/addons/afenda_api_docs/openapi.py` | Registry walk → OpenAPI 3.1 dict |
| `afenda/addons/afenda_api_docs/controllers/landing.py` | The `/docs` landing route |
| `afenda/addons/afenda_api_docs/controllers/api.py` | `/docs/openapi.json` and `/docs/api` |
| `afenda/addons/afenda_api_docs/controllers/guides.py` | `/docs[/<version>]/applications/<path>` |
| `afenda/addons/afenda_api_docs/views/landing.xml` | The landing page |
| `afenda/addons/afenda_api_docs/views/api.xml` | The Redoc reference page |
| `afenda/addons/afenda_api_docs/views/guides_chrome.xml` | The "not written yet" page |
| `afenda/addons/afenda_api_docs/docs/**.md` | Authored guide source |
| `afenda/addons/afenda_api_docs/views/guides.xml` | Generated from the Markdown; committed |
| `afenda/tools/build_docs.py` | Markdown → QWeb converter |

The controllers and views are split one file per route group, and the tests one
file per task, so that concurrent agents never write the same file. Three files
are shared wiring — `controllers/__init__.py`, `tests/__init__.py` and
`__manifest__.py`. **No task edits those.** The orchestrator wires them between
waves; each task's file list says what it creates and the orchestrator adds the
corresponding import or `data` entry.

## Parallel execution

Tasks run in waves. Within a wave, agents share no file and no database.

| Wave | Agents | Tasks | Database | HTTP port |
| --- | --- | --- | --- | --- |
| 0 | 1 | Task 1 | `afenda` | 8179 |
| 1 | 2 | Task 2 · Task 7 | `afenda` · none (no DB needed) | 8179 · — |
| 2 | 2 | Tasks 3→4→5 · Task 8 | `afenda` · `afenda_lane2` | 8179 · 8189 |
| 3 | 1 | Task 6 | `afenda` | 8179 |
| 4 | 1 | Task 9 | `afenda` | 8179 |

A lane is a database clone **plus its filestore**. Cloning the database alone
is a trap: in Odoo 19 every image field and every asset bundle is
attachment-backed, so the clone's attachment rows point at files that do not
exist and the suite fails with `FileNotFoundError ... filestore/<db>/cd/cd37f4...`
plus 500s on asset-bundle routes. Those read as code regressions and are not.
This cost another session an hour before it was diagnosed.

Clone both together, deriving the filestore path from Odoo's own config rather
than hardcoding it:

```bash
.venv/Scripts/python - <<'PY'
import shutil, sys
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from odoo.tools import config

SRC, DST = "afenda", "afenda_lane2"
config.parse_config(["-c", "afenda/odoo.conf"])
root = Path(config.filestore(SRC)).parent

conn = psycopg2.connect(host="127.0.0.1", port=5444, user="odoo", dbname="postgres")
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (SRC,))
if cur.fetchone()[0]:
    sys.exit(f"{SRC} has live connections; TEMPLATE clone needs zero")
cur.execute(f'DROP DATABASE IF EXISTS "{DST}"')
cur.execute(f'CREATE DATABASE "{DST}" TEMPLATE "{SRC}"')

shutil.rmtree(root / DST, ignore_errors=True)
shutil.copytree(root / SRC, root / DST)
src_n = sum(1 for _ in (root / SRC).rglob("*") if _.is_file())
dst_n = sum(1 for _ in (root / DST).rglob("*") if _.is_file())
print(f"cloned {SRC} -> {DST}; filestore {src_n} -> {dst_n} files")
assert src_n == dst_n, "filestore copy incomplete"
PY
```

Verify the counts match before using the lane. Re-clone at the start of each
wave so the lane carries the previous wave's schema, and install
`afenda_api_docs` there if the lane needs to run the `afenda_brand` suite — that
suite's `test_docs_route_answers_same_origin` 404s without it.

**Why the ceiling is two, not nine.** Tasks 3, 4 and 5 all edit `openapi.py`
and each depends on the one before, so they are a single agent's sequential
work. Task 1 must be alone because every later file lives inside the module it
creates. Task 6 edits the `controllers/api.py` that Task 5 creates, and Task 9
reads the output of all of them. Two lanes is the real width of this graph;
adding agents past that produces conflicts, not speed.

`aliasing.py` stays free of Odoo imports so its tests run without a database.

**Test base classes are not interchangeable.** Any test collected by Odoo's
module test runner must subclass `odoo.tests.BaseCase` (or a descendant such as
`TransactionCase` / `HttpCase`). A plain `unittest.TestCase` is silently
excluded by the tag selector and the suite still reports success. Task 7 is the
only exception: its tests live outside an addon, under `afenda/tools/tests/`,
and run via `python -m unittest`, which has no tag selector.

---

### Task 1: Module skeleton and the `/docs` route takeover

**Files:**
- Create: `afenda/addons/afenda_api_docs/__init__.py`
- Create: `afenda/addons/afenda_api_docs/__manifest__.py`
- Create: `afenda/addons/afenda_api_docs/controllers/__init__.py`
- Create: `afenda/addons/afenda_api_docs/controllers/landing.py`
- Create: `afenda/addons/afenda_api_docs/views/landing.xml`
- Create: `afenda/addons/afenda_api_docs/tests/__init__.py`
- Create: `afenda/addons/afenda_api_docs/tests/test_routes.py`
- Modify: `afenda/addons/afenda_brand/__manifest__.py` (drop `views/docs_placeholder.xml` from `data`)
- Modify: `afenda/addons/afenda_brand/controllers/__init__.py:1` (drop `from . import main`)
- Modify: `afenda/addons/afenda_brand/tests/test_identity.py:84-89` (`test_docs_placeholder_route_works`)
- Delete: `afenda/addons/afenda_brand/controllers/main.py`
- Delete: `afenda/addons/afenda_brand/views/docs_placeholder.xml`

**Interfaces:**
- Consumes: nothing.
- Produces: module `afenda_api_docs`; template ids `afenda_api_docs.landing`; controller class `AfendaDocsController`.

- [ ] **Step 1: Confirm the coordination precondition**

Two controllers claiming `/docs` collide. Message the session that owns `afenda_brand` and confirm it is not mid-edit in `controllers/` or `__manifest__.py`. Do not proceed until confirmed.

- [ ] **Step 2: Write the failing test**

Create `afenda/addons/afenda_api_docs/tests/__init__.py`:

```python
from . import test_routes
```

Create `afenda/addons/afenda_api_docs/tests/test_routes.py`:

```python
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestDocsRoutes(HttpCase):
    def test_landing_is_public_and_branded(self):
        res = self.url_open("/docs")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AFENDA", res.text)

    def test_landing_carries_no_odoo_identity(self):
        res = self.url_open("/docs")
        for tell in ("Odoo", "odoo.com"):
            self.assertNotIn(tell, res.text)

    def test_settings_help_paths_do_not_404_before_the_guides_land(self):
        # What the documentation_link widget emits. Until Task 8 these fall
        # through to the landing page; they must never 404.
        res = self.url_open("/docs/19.0/applications/finance/accounting.html")
        self.assertEqual(res.status_code, 200)
```

- [ ] **Step 3: Run it to make sure it fails**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda \
  -i afenda_api_docs --test-enable --test-tags "/afenda_api_docs" --stop-after-init --http-port 8179
```

Expected: the module does not exist, so the install fails before tests run. That is the correct failure for this step.

- [ ] **Step 4: Create the module**

`afenda/addons/afenda_api_docs/__init__.py`:

```python
from . import controllers
```

`afenda/addons/afenda_api_docs/__manifest__.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA Documentation",
    "summary": "Generated API reference and guides served at /docs",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://afenda.app",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    # `rpc` owns the /json/2 route this documents; `afenda_brand` owns BRAND.
    "depends": ["web", "rpc", "afenda_brand"],
    "data": ["views/landing.xml"],
}
```

`afenda/addons/afenda_api_docs/controllers/__init__.py`:

```python
from . import main
```

`afenda/addons/afenda_api_docs/controllers/landing.py`:

```python
from odoo import http
from odoo.http import request


class AfendaDocsController(http.Controller):
    # The catch-all is not decoration. The placeholder this replaces answered
    # `/docs/<path:subpath>` as well as `/docs`, and 117 Settings help icons
    # point at `/docs/19.0/applications/...`. Without it those 404 from this
    # task until Task 8 lands. Task 8 adds more specific `/docs/applications`
    # rules, which werkzeug prefers over this one.
    @http.route(
        ["/docs", "/docs/<path:subpath>"],
        type="http", auth="public", website=False, sitemap=False,
    )
    def docs_landing(self, subpath=None, **kwargs):
        return request.render("afenda_api_docs.landing", {})
```

`afenda/addons/afenda_api_docs/views/landing.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="landing" name="AFENDA Documentation">
        <t t-call="web.frontend_layout">
            <div class="container py-5">
                <h1>AFENDA xForge documentation</h1>
                <div class="row mt-4">
                    <div class="col-md-6">
                        <h2>Guides</h2>
                        <p class="text-muted">How the apps work, written for people using them.</p>
                        <a href="/docs/applications">Browse the guides</a>
                    </div>
                    <div class="col-md-6">
                        <h2>API reference</h2>
                        <p class="text-muted">Every model and method reachable over the JSON API.</p>
                        <a href="/docs/api">Open the API reference</a>
                    </div>
                </div>
            </div>
        </t>
    </template>
</odoo>
```

- [ ] **Step 5: Remove the placeholder from `afenda_brand`**

Delete `afenda/addons/afenda_brand/controllers/main.py` and `afenda/addons/afenda_brand/views/docs_placeholder.xml`.

In `afenda/addons/afenda_brand/controllers/__init__.py`, delete the line `from . import main` so the file reads:

```python
from . import webmanifest
from . import home
```

In `afenda/addons/afenda_brand/__manifest__.py`, delete the `"views/docs_placeholder.xml",` entry from `data`.

Then fix the test that pins the placeholder. `afenda/addons/afenda_brand/tests/test_identity.py:84` currently asserts the page says "coming soon", which stops being true here. Its real intent is that the rewritten documentation links resolve same-origin, and that intent survives. Replace the method with:

```python
    def test_docs_route_answers_same_origin(self):
        # afenda_api_docs owns the content; this module only cares that the
        # rewritten documentation links resolve on this origin at all.
        self.assertEqual(self.url_open("/docs").status_code, 200)
        self.assertEqual(self.url_open("/docs/applications/sales.html").status_code, 200)
```

- [ ] **Step 6: Run the tests and make sure they pass**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda \
  -i afenda_api_docs -u afenda_brand --test-enable --test-tags "/afenda_api_docs" --stop-after-init --http-port 8179
```

Expected: both tests PASS. `afenda_brand` must be updated in the same run so the placeholder view record is removed from the database.

- [ ] **Step 7: Commit**

```bash
git add afenda/addons/afenda_api_docs afenda/addons/afenda_brand/__manifest__.py afenda/addons/afenda_brand/controllers/__init__.py
git add -u afenda/addons/afenda_brand/controllers/main.py afenda/addons/afenda_brand/views/docs_placeholder.xml
git commit -m "[ADD] afenda_api_docs: take /docs over from the placeholder

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Prose-versus-wire brand aliasing

This is the plan's one stated requirement. Get it right before anything consumes it.

**Files:**
- Create: `afenda/addons/afenda_api_docs/aliasing.py`
- Create: `afenda/addons/afenda_api_docs/tests/test_aliasing.py`
- Modify: `afenda/addons/afenda_api_docs/tests/__init__.py`

**Interfaces:**
- Consumes: `BRAND` from `odoo.addons.afenda_brand.brand`.
- Produces: `alias_prose(text: str | None) -> str | None`. Every later task calls this and **only** this for prose.

- [ ] **Step 1: Write the failing tests**

Create `afenda/addons/afenda_api_docs/tests/test_aliasing.py`:

```python
from odoo.tests import BaseCase

from odoo.addons.afenda_api_docs.aliasing import alias_prose


# BaseCase, NOT unittest.TestCase. Odoo's tag selector drops any test class
# without a `test_tags` attribute (odoo/tests/tag_selector.py:88-90), and only
# BaseCase subclasses get one, via __init_subclass__ (common.py:309-318). The
# skip is logged at DEBUG and afenda/odoo.conf runs at `warn`, so a plain
# unittest.TestCase here does not fail - it silently never runs, and the suite
# reports green. BaseCase is the right base for a DB-free pure-logic test.
class TestAliasProse(BaseCase):
    def test_capitalised_product_name(self):
        self.assertEqual(alias_prose("Powered by Odoo"), "Powered by AFENDA xForge")

    def test_lowercase_is_aliased_too(self):
        # The file-level rules skip lowercase because a file has imports and
        # license headers to protect. A prose field has neither.
        self.assertEqual(alias_prose("sent from odoo"), "sent from AFENDA xForge")

    def test_legal_name_beats_product_name(self):
        self.assertEqual(alias_prose("Copyright Odoo S.A."), "Copyright AFENDA")

    def test_bot_name(self):
        self.assertEqual(alias_prose("Ask OdooBot"), "Ask AFENDA Bot")

    def test_domain(self):
        self.assertEqual(alias_prose("see odoo.com for more"), "see afenda.app for more")

    def test_documentation_link_goes_same_origin(self):
        self.assertEqual(
            alias_prose("read https://www.odoo.com/documentation/19.0/x.html"),
            "read /docs/x.html",
        )

    def test_identifiers_embedded_in_prose_survive(self):
        # Word boundaries: these are field names a reader may need verbatim.
        for identifier in ("odoobot_state", "odoobot_failed", "delete_odoo"):
            self.assertIn(identifier, alias_prose(f"Set {identifier} to done"))

    def test_none_and_empty_pass_through(self):
        self.assertIsNone(alias_prose(None))
        self.assertEqual(alias_prose(""), "")

    def test_is_idempotent(self):
        once = alias_prose("Odoo and odoo and odoo.com")
        self.assertEqual(alias_prose(once), once)
```

Add to `afenda/addons/afenda_api_docs/tests/__init__.py`:

```python
from . import test_aliasing
from . import test_routes
```

- [ ] **Step 2: Run them to make sure they fail**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda \
  -u afenda_api_docs --test-enable --test-tags "/afenda_api_docs" --stop-after-init --http-port 8179
```

Expected: `ModuleNotFoundError: No module named 'odoo.addons.afenda_api_docs.aliasing'`.

- [ ] **Step 3: Write the implementation**

Create `afenda/addons/afenda_api_docs/aliasing.py`:

```python
"""Brand aliasing for generated documentation.

Two classes of string appear in a generated document and they must never be
treated alike:

* **Prose** - summaries, descriptions, field labels and help, selection
  labels, docstrings. Always aliased.
* **Wire values** - model, field, method and parameter names, selection keys,
  spreadsheet function names such as ODOO.BALANCE. Never aliased: a caller
  must send them back verbatim, so renaming one documents an API that
  rejects its own documentation.

The split is enforced structurally, by calling `alias_prose` only at prose
insertion points, never by scanning an assembled document.

Unlike the build-time rules in `afenda/tools/rules.py`, matching here is
case-insensitive on the standalone word: those rules must spare lowercase
`odoo` because a source file contains imports, license headers and module
paths. A prose field contains none of those. Word boundaries keep this safe
- `\\bodoo\\b` does not match inside `odoobot_state`.
"""
import re

from odoo.addons.afenda_brand.brand import BRAND

# Ordered. Earlier rules win: the legal name and the bot name must be
# consumed before the bare product name would split them.
_RULES = (
    (re.compile(r"Odoo\s+S\.A\.", re.IGNORECASE), BRAND["short"]),
    #  on BOTH sides, and it is load-bearing. With re.IGNORECASE and no
    # boundaries this pattern matches inside `odoobot_state` and
    # `odoobot_failed`, rewriting them to `AFENDA Bot_state` and
    # `AFENDA Bot_failed` - corrupting the exact wire values this whole module
    # exists to protect. `test_identifiers_embedded_in_prose_survive` pins it.
    (re.compile(r"OdooBot", re.IGNORECASE), BRAND["bot"]),
    (
        re.compile(
            r"https?://(?:www\.)?odoo\.com"
            r"/documentation(?:/(?:\d+\.\d+|latest|master|saas-[\d.]+))?/?",
            re.IGNORECASE,
        ),
        BRAND["docs_path"],
    ),
    (re.compile(r"\bodoo\.com\b", re.IGNORECASE), BRAND["domain"]),
    (re.compile(r"\bodoo\b", re.IGNORECASE), BRAND["product"]),
)


def alias_prose(text):
    """Rewrite Odoo identity in a prose string. Never call this on a wire value."""
    if not text:
        return text
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
```

- [ ] **Step 4: Run the tests and make sure they pass**

Same command as Step 2. Expected: all 9 aliasing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add afenda/addons/afenda_api_docs/aliasing.py afenda/addons/afenda_api_docs/tests/
git commit -m "[ADD] afenda_api_docs: prose-versus-wire brand aliasing

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Field schemas from `fields_get()`

**Files:**
- Create: `afenda/addons/afenda_api_docs/openapi.py`
- Create: `afenda/addons/afenda_api_docs/tests/test_openapi.py`
- Modify: `afenda/addons/afenda_api_docs/tests/__init__.py`

**Interfaces:**
- Consumes: `alias_prose` from Task 2.
- Produces: `model_schema(model) -> dict` — a JSON Schema object for one model. Task 4 and Task 5 both call it.

- [ ] **Step 1: Write the failing tests**

Create `afenda/addons/afenda_api_docs/tests/test_openapi.py`:

```python
from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_api_docs.openapi import model_schema


@tagged("post_install", "-at_install")
class TestModelSchema(TransactionCase):
    def test_scalar_field_types_map_to_json_schema(self):
        schema = model_schema(self.env["res.partner"])
        self.assertEqual(schema["properties"]["name"]["type"], "string")
        self.assertEqual(schema["properties"]["active"]["type"], "boolean")

    def test_many2one_is_an_integer_id(self):
        schema = model_schema(self.env["res.partner"])
        self.assertEqual(schema["properties"]["country_id"]["type"], "integer")

    def test_x2many_is_an_array_of_ids(self):
        schema = model_schema(self.env["res.partner"])
        child = schema["properties"]["child_ids"]
        self.assertEqual(child["type"], "array")
        self.assertEqual(child["items"]["type"], "integer")

    def test_selection_keys_are_wire_values_and_are_not_aliased(self):
        schema = model_schema(self.env["res.users"])
        state = schema["properties"]["odoobot_state"]
        # The field name and every enum key must survive verbatim.
        self.assertIn("odoobot_state", schema["properties"])
        for key in state["enum"]:
            self.assertNotIn("AFENDA", key)

    def test_selection_labels_are_prose_and_are_aliased(self):
        schema = model_schema(self.env["res.users"])
        labels = " ".join(schema["properties"]["odoobot_state"]["x-enum-labels"])
        self.assertNotIn("Odoo", labels)

    def test_every_odoo_field_type_is_mapped(self):
        # The fallback silently documents an unknown type as a string, which is
        # a wrong contract rather than a missing one. If Odoo gains a field type,
        # fail here rather than mis-document it.
        from odoo.addons.afenda_api_docs.openapi import _TYPE_MAP
        declared = {f.type for f in self.env["res.partner"]._fields.values()}
        self.assertTrue(declared)
        self.assertEqual(declared - set(_TYPE_MAP), set())

    def test_help_text_is_aliased(self):
        schema = model_schema(self.env["res.partner"])
        for prop in schema["properties"].values():
            self.assertNotIn("Odoo", prop.get("description", ""))
```

Add `from . import test_openapi` to `afenda/addons/afenda_api_docs/tests/__init__.py`.

- [ ] **Step 2: Run them to make sure they fail**

Same command as Task 2 Step 2. Expected: `ModuleNotFoundError: No module named 'odoo.addons.afenda_api_docs.openapi'`.

- [ ] **Step 3: Write the implementation**

Create `afenda/addons/afenda_api_docs/openapi.py`:

```python
"""Generate an OpenAPI 3.1 document by walking the live registry."""
from .aliasing import alias_prose

# Odoo field type -> JSON Schema fragment. Relational fields are documented as
# the ids the /json/2 route actually accepts and returns, not as nested
# objects, because that is what the dispatcher passes to the ORM.
_TYPE_MAP = {
    "char": {"type": "string"},
    "text": {"type": "string"},
    "html": {"type": "string"},
    "selection": {"type": "string"},
    "integer": {"type": "integer"},
    "float": {"type": "number"},
    "monetary": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
    "datetime": {"type": "string", "format": "date-time"},
    "binary": {"type": "string", "format": "byte"},
    "json": {"type": "object"},
    "properties": {"type": "object"},
    "many2one": {"type": "integer"},
    "one2many": {"type": "array", "items": {"type": "integer"}},
    "many2many": {"type": "array", "items": {"type": "integer"}},
    # The three below are easy to miss and two of them are NOT strings.
    # many2one_reference stores an integer id, with the model name in a
    # companion Char named by its `model_field` (odoo/orm/fields_reference.py:62).
    # Falling through to the string fallback would tell an integrator to send
    # "5" where the ORM wants 5.
    "many2one_reference": {"type": "integer"},
    # Reference really is a string, but a structured one: "res_model,res_id"
    # (odoo/orm/fields_reference.py:17-18). Document the shape.
    "reference": {"type": "string", "pattern": r"^[a-z_.]+,\d+$"},
    # A jsonb list of property definitions (odoo/orm/fields_properties.py:850).
    "properties_definition": {"type": "array", "items": {"type": "object"}},
}
# Only reached by a field type added to Odoo after this map was written. A new
# type documented as a string is a wrong contract, not a missing one, so the
# test below fails loudly instead of letting it through quietly.
_FALLBACK = {"type": "string"}


def model_schema(model):
    """JSON Schema for one model, from what the calling user may read."""
    properties = {}
    required = []
    for name, meta in model.fields_get().items():
        prop = dict(_TYPE_MAP.get(meta["type"], _FALLBACK))
        # Prose.
        prop["title"] = alias_prose(meta.get("string") or name)
        if meta.get("help"):
            prop["description"] = alias_prose(meta["help"])
        # Wire values: enum keys are sent back verbatim, labels are read.
        if meta.get("selection"):
            prop["enum"] = [key for key, _label in meta["selection"]]
            prop["x-enum-labels"] = [alias_prose(label) for _key, label in meta["selection"]]
        if meta.get("relation"):
            prop["x-relation"] = meta["relation"]
        if meta.get("readonly"):
            prop["readOnly"] = True
        if meta.get("required"):
            required.append(name)
        properties[name] = prop

    schema = {
        "type": "object",
        "title": alias_prose(model._description or model._name),
        "properties": properties,
    }
    if required:
        schema["required"] = sorted(required)
    return schema
```

- [ ] **Step 4: Run the tests and make sure they pass**

Same command. Expected: all 6 schema tests PASS.

If `test_selection_keys_...` errors because `odoobot_state` is absent, the `mail_bot` module is not installed in this database. Install it once with `-i mail_bot` and re-run; do not weaken the test, it is the wire-value guard.

- [ ] **Step 5: Commit**

```bash
git add afenda/addons/afenda_api_docs/openapi.py afenda/addons/afenda_api_docs/tests/
git commit -m "[ADD] afenda_api_docs: field schemas from fields_get

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Operations from `get_public_method`

**Files:**
- Modify: `afenda/addons/afenda_api_docs/openapi.py`
- Modify: `afenda/addons/afenda_api_docs/tests/test_openapi.py`

**Interfaces:**
- Consumes: `model_schema` from Task 3.
- Produces: `model_operations(model) -> dict[str, callable]` and `path_item(model_name, method_name, func) -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `afenda/addons/afenda_api_docs/tests/test_openapi.py`:

```python
import inspect

from odoo.service.model import get_public_method

from odoo.addons.afenda_api_docs.openapi import model_operations, path_item


@tagged("post_install", "-at_install")
class TestOperations(TransactionCase):
    def test_public_orm_methods_are_documented(self):
        ops = model_operations(self.env["res.partner"])
        for expected in ("search", "read", "create", "write", "unlink"):
            self.assertIn(expected, ops)

    def test_private_methods_are_not_documented(self):
        ops = model_operations(self.env["res.partner"])
        for hidden in ("_read", "_write", "browse"):
            self.assertNotIn(hidden, ops)

    def test_every_documented_method_is_actually_callable(self):
        # The one invariant that matters: the docs must not describe an
        # operation the dispatcher would 404.
        model = self.env["res.partner"]
        for name in model_operations(model):
            get_public_method(model, name)

    def test_path_item_shape(self):
        model = self.env["res.partner"]
        func = model_operations(model)["read"]
        item = path_item("res.partner", "read", func)
        body = item["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(body["properties"]["ids"]["type"], "array")
        self.assertIn("context", body["properties"])
        self.assertIn("404", item["post"]["responses"])
        self.assertIn("422", item["post"]["responses"])

    def test_method_docstring_is_aliased(self):
        model = self.env["res.partner"]
        for name, func in model_operations(model).items():
            item = path_item("res.partner", name, func)
            self.assertNotIn("Odoo", item["post"].get("description", ""))
```

- [ ] **Step 2: Run them to make sure they fail**

Same command. Expected: `ImportError: cannot import name 'model_operations'`.

- [ ] **Step 3: Write the implementation**

Append to `afenda/addons/afenda_api_docs/openapi.py`:

```python
import inspect

from odoo.exceptions import AccessError
from odoo.service.model import get_public_method

# Annotation -> JSON Schema. Most ORM methods carry no annotations; an
# unannotated parameter is documented as untyped rather than guessed at.
_ANNOTATION_MAP = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array"},
    dict: {"type": "object"},
}


def model_operations(model):
    """Every method on `model` the /json/2 dispatcher would accept.

    Delegates the rule to `get_public_method`, the same function the
    dispatcher calls, so this cannot drift into documenting a 404.
    """
    operations = {}
    for name in sorted(dir(type(model))):
        try:
            operations[name] = get_public_method(model, name)
        except (AttributeError, AccessError):
            continue
    return operations


def _annotation_schema(annotation):
    if annotation is inspect.Parameter.empty:
        return {}
    return dict(_ANNOTATION_MAP.get(annotation, {}))


def path_item(model_name, method_name, func):
    """The OpenAPI path item for POST /json/2/<model>/<method>."""
    properties = {
        "ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Record ids the method is called on.",
        },
        "context": {"type": "object", "description": "Odoo context for the call."},
    }
    parameters = list(inspect.signature(func).parameters.values())
    for param in parameters[1:]:  # [0] is the recordset the dispatcher binds
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        properties[param.name] = _annotation_schema(param.annotation)

    return {
        "post": {
            "operationId": f"{model_name}.{method_name}",
            "summary": alias_prose(f"{method_name} on {model_name}"),
            "description": alias_prose(inspect.getdoc(func) or ""),
            "tags": [model_name],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"type": "object", "properties": properties}
                    }
                },
            },
            "responses": {
                "200": {"description": "Success."},
                "404": {"description": "The model or method does not exist."},
                "422": {"description": "The arguments do not match the method signature."},
            },
            "security": [{"bearerAuth": []}],
        }
    }
```

Note the `context` description deliberately says "Odoo context": it is aliased by `alias_prose`? No — it is a literal in this file, so **write it as** `"AFENDA xForge context for the call."` to avoid reintroducing identity that the scanner would then count. Use that wording.

- [ ] **Step 4: Run the tests and make sure they pass**

Same command. Expected: 5 operation tests PASS, plus the 6 from Task 3.

- [ ] **Step 5: Commit**

```bash
git add afenda/addons/afenda_api_docs/openapi.py afenda/addons/afenda_api_docs/tests/test_openapi.py
git commit -m "[ADD] afenda_api_docs: operations from get_public_method

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: App scoping and the `/docs/openapi.json` route

**Files:**
- Modify: `afenda/addons/afenda_api_docs/openapi.py`
- Create: `afenda/addons/afenda_api_docs/controllers/api.py`
- Modify: `afenda/addons/afenda_api_docs/tests/test_openapi.py`
- Create: `afenda/addons/afenda_api_docs/tests/test_api_routes.py`

**Interfaces:**
- Consumes: `model_schema`, `model_operations`, `path_item`.
- Produces: `build_document(env, app=None) -> dict`; route `/docs/openapi.json`.

- [ ] **Step 1: Write the failing tests**

Append to `afenda/addons/afenda_api_docs/tests/test_openapi.py`:

```python
from odoo.addons.afenda_api_docs.openapi import build_document, models_for_app

CORE = ("res.partner", "res.users", "product.template",
        "sale.order", "account.move", "stock.picking")


@tagged("post_install", "-at_install")
class TestDocument(TransactionCase):
    def test_default_document_is_the_core_set_intersected_with_the_registry(self):
        doc = build_document(self.env)
        tags = {t["name"] for t in doc["tags"]}
        self.assertTrue(tags)
        for name in tags:
            self.assertIn(name, CORE)
            self.assertIn(name, self.env)

    def test_app_scoping_uses_ir_model_data(self):
        # ir.model.modules is computed and non-stored, so it cannot be searched.
        names = models_for_app(self.env, "base")
        self.assertIn("res.partner", names)
        self.assertNotIn("sale.order", names)

    def test_document_is_openapi_31_and_structurally_complete(self):
        doc = build_document(self.env)
        self.assertEqual(doc["openapi"], "3.1.0")
        self.assertIn("info", doc)
        self.assertTrue(doc["paths"])
        for path, item in doc["paths"].items():
            self.assertTrue(path.startswith("/json/2/"))
            self.assertIn("post", item)

    def test_every_ref_resolves(self):
        doc = build_document(self.env)
        schemas = doc["components"]["schemas"]

        def walk(node):
            if isinstance(node, dict):
                ref = node.get("$ref")
                if ref:
                    self.assertTrue(ref.startswith("#/components/schemas/"))
                    self.assertIn(ref.rsplit("/", 1)[1], schemas)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(doc)

    def test_no_odoo_identity_in_prose_but_wire_values_survive(self):
        doc = build_document(self.env)
        for tag in doc["tags"]:
            self.assertNotIn("Odoo", tag.get("description", ""))
        self.assertIn("res.partner", doc["components"]["schemas"])
```

Create `afenda/addons/afenda_api_docs/tests/test_api_routes.py` (same `HttpCase` header as `test_routes.py`):

```python
    def test_openapi_json_requires_a_session(self):
        res = self.url_open("/docs/openapi.json")
        self.assertNotEqual(res.status_code, 200)

    def test_openapi_json_serves_a_document_to_a_logged_in_user(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/openapi.json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["openapi"], "3.1.0")
```

- [ ] **Step 2: Run them to make sure they fail**

Same command. Expected: `ImportError: cannot import name 'build_document'`.

- [ ] **Step 3: Write the implementation**

Append to `afenda/addons/afenda_api_docs/openapi.py`:

```python
# Emitted when no ?app= is given, so the default URL is useful rather than
# empty. Intersected with the registry: a model whose module is not installed
# does not exist.
_CORE_MODELS = (
    "res.partner",
    "res.users",
    "product.template",
    "sale.order",
    "account.move",
    "stock.picking",
)


def models_for_app(env, app):
    """Model names defined by one module.

    Resolved through ir.model.data rather than ir.model.modules: the latter
    reads as the obvious choice and is a non-stored computed field
    (`ir_model.py:241`), so it cannot appear in a search domain.
    """
    data = env["ir.model.data"].sudo().search(
        [("module", "=", app), ("model", "=", "ir.model")]
    )
    models = env["ir.model"].sudo().browse(data.mapped("res_id"))
    return sorted(m.model for m in models if m.model in env)


def build_document(env, app=None):
    """An OpenAPI 3.1 document for one app, or for the core set."""
    names = models_for_app(env, app) if app else [m for m in _CORE_MODELS if m in env]

    paths = {}
    schemas = {}
    tags = []
    for name in names:
        model = env[name]
        if not model.has_access("read"):
            continue
        schemas[name] = model_schema(model)
        tags.append({"name": name, "description": alias_prose(model._description or name)})
        for method_name, func in model_operations(model).items():
            paths[f"/json/2/{name}/{method_name}"] = path_item(name, method_name, func)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": alias_prose("AFENDA xForge JSON API"),
            "version": "2",
            "description": alias_prose(
                "Every model and method reachable over POST /json/2/<model>/<method>. "
                "Generated from the running system for the signed-in user, so it "
                "shows only what that user may read."
            ),
        },
        "servers": [{"url": "/"}],
        "tags": tags,
        "paths": paths,
        "components": {
            "schemas": schemas,
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            },
        },
    }
```

Create `afenda/addons/afenda_api_docs/controllers/api.py`:

```python
import json

from ..openapi import build_document


class AfendaDocsController(http.Controller):  # extend the existing class
    @http.route("/docs/openapi.json", type="http", auth="user", website=False, sitemap=False)
    def docs_openapi(self, app=None, **kwargs):
        document = build_document(request.env, app=app)
        return request.make_response(
            json.dumps(document),
            headers=[("Content-Type", "application/json")],
        )
```

Declare this as its own controller class `AfendaApiController` in `controllers/api.py`. A module may register several controllers; keeping the route groups in separate files is what lets Task 6 and Task 8 run beside each other. The orchestrator adds `from . import api` to `controllers/__init__.py`.

- [ ] **Step 4: Run the tests and make sure they pass**

Same command. Expected: 5 document tests and 2 route tests PASS.

- [ ] **Step 5: Check the document is small enough to render**

```bash
.venv/Scripts/python odoo-bin shell -c afenda/odoo.conf -d afenda --no-http <<'PY'
import json
from odoo.addons.afenda_api_docs.openapi import build_document
for app in (None, 'sale', 'account'):
    size = len(json.dumps(build_document(env, app=app)))
    print(app, f"{size/1024:.0f} KiB")
PY
```

Expected: each well under 1 MiB. If any app exceeds it, that is the signal to narrow the method set, not to widen the budget.

- [ ] **Step 6: Commit**

```bash
git add afenda/addons/afenda_api_docs/openapi.py afenda/addons/afenda_api_docs/controllers/main.py afenda/addons/afenda_api_docs/tests/
git commit -m "[ADD] afenda_api_docs: per-app OpenAPI document at /docs/openapi.json

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Vendored Redoc and the `/docs/api` page

**Files:**
- Create: `afenda/addons/afenda_api_docs/static/lib/redoc/redoc.standalone.js`
- Create: `afenda/addons/afenda_api_docs/static/lib/redoc/LICENSE`
- Create: `afenda/addons/afenda_api_docs/views/api.xml`
- Modify: `afenda/addons/afenda_api_docs/controllers/api.py`
- Modify: `afenda/addons/afenda_api_docs/tests/test_api_routes.py`

**Interfaces:**
- Consumes: `/docs/openapi.json` from Task 5.
- Produces: route `/docs/api`; template `afenda_api_docs.api_reference`.

Redoc, not Scalar or Swagger UI: `/json/2` is `auth='bearer'`, so an in-page "try it" console cannot borrow the browser session and would need an API key pasted into the page. A read-only reference avoids that.

- [ ] **Step 1: Vendor the bundle**

Download `redoc.standalone.js` from the Redoc releases and its MIT `LICENSE` into `static/lib/redoc/`. No CDN reference may appear in any template: the page must work offline and same-origin.

Verify it is the whole bundle and not an HTML error page:

```bash
head -c 200 afenda/addons/afenda_api_docs/static/lib/redoc/redoc.standalone.js
ls -la afenda/addons/afenda_api_docs/static/lib/redoc/
```

Expected: JavaScript, roughly 1 MB.

- [ ] **Step 2: Write the failing test**

Append to `afenda/addons/afenda_api_docs/tests/test_api_routes.py`:

```python
    def test_api_reference_requires_a_session(self):
        res = self.url_open("/docs/api")
        self.assertNotEqual(res.status_code, 200)

    def test_api_reference_renders_and_loads_redoc_from_this_origin(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/api")
        self.assertEqual(res.status_code, 200)
        self.assertIn("/afenda_api_docs/static/lib/redoc/redoc.standalone.js", res.text)
        self.assertNotIn("cdn.", res.text)
        self.assertNotIn("Odoo", res.text)
```

- [ ] **Step 3: Run it to make sure it fails**

Same command. Expected: the `/docs/api` assertions fail with a 404.

- [ ] **Step 4: Add the route and the template**

Add to `AfendaApiController` in `controllers/api.py`:

```python
    @http.route("/docs/api", type="http", auth="user", website=False, sitemap=False)
    def docs_api(self, app=None, **kwargs):
        return request.render(
            "afenda_api_docs.api_reference",
            {"spec_url": f"/docs/openapi.json?app={app}" if app else "/docs/openapi.json"},
        )
```

Create `views/api.xml` with the usual `<?xml?>`/`<odoo>` wrapper containing:

```xml
    <template id="api_reference" name="AFENDA API reference">
        <t t-call="web.frontend_layout">
            <redoc t-att-spec-url="spec_url"/>
            <script type="text/javascript"
                    src="/afenda_api_docs/static/lib/redoc/redoc.standalone.js"/>
        </t>
    </template>
```

- [ ] **Step 5: Run the tests and make sure they pass**

Same command. Expected: both `/docs/api` tests PASS.

- [ ] **Step 6: Commit**

```bash
git add afenda/addons/afenda_api_docs/static afenda/addons/afenda_api_docs/views/templates.xml afenda/addons/afenda_api_docs/controllers/main.py afenda/addons/afenda_api_docs/tests/test_routes.py
git commit -m "[ADD] afenda_api_docs: vendored Redoc reference at /docs/api

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: The Markdown-to-QWeb build tool

**Files:**
- Create: `afenda/tools/build_docs.py`
- Create: `afenda/tools/tests/test_build_docs.py`
- Create: `afenda/addons/afenda_api_docs/docs/applications/general/users.md`
- Create: `afenda/addons/afenda_api_docs/views/guides.xml` (generated, committed)
- Modify: `afenda/tools/requirements.txt`
- Modify: `afenda/addons/afenda_api_docs/__manifest__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `build(src_dir, out_file) -> int` returning the page count; template ids `afenda_api_docs.guide_<slug>` where `<slug>` is the path with `/` and `.` replaced by `_`.

Build time rather than request time: no Markdown library is installed, and this keeps the runtime free of a new Python dependency. Both the Markdown and the generated XML are committed, and a test asserts they agree — the same golden-file discipline the corpus already uses.

- [ ] **Step 1: Add the build-time dependency**

Append to `afenda/tools/requirements.txt`:

```
# Build-time only: converts afenda_api_docs/docs/**.md into committed QWeb
# templates. Pinned because the generated XML is committed and reviewed.
markdown==3.5.2
```

Install it:

```bash
.venv/Scripts/python -m pip install markdown==3.5.2
```

- [ ] **Step 2: Write the failing test**

Create `afenda/tools/tests/test_build_docs.py`:

```python
import tempfile
import unittest
from pathlib import Path

from afenda.tools.build_docs import build, slug_for


class SlugTests(unittest.TestCase):
    def test_path_becomes_a_template_slug(self):
        self.assertEqual(slug_for("applications/general/users.md"), "applications_general_users")


class BuildTests(unittest.TestCase):
    def test_a_markdown_page_becomes_a_qweb_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            (src / "applications").mkdir(parents=True)
            (src / "applications" / "users.md").write_text(
                "# Users\n\nHow to add a user.\n", encoding="utf-8"
            )
            out = Path(tmp) / "guides.xml"
            count = build(src, out)
            self.assertEqual(count, 1)
            xml = out.read_text(encoding="utf-8")
            self.assertIn('id="guide_applications_users"', xml)
            self.assertIn("<h1>Users</h1>", xml)

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "a.md").write_text("# A\n", encoding="utf-8")
            (src / "b.md").write_text("# B\n", encoding="utf-8")
            out1, out2 = Path(tmp) / "1.xml", Path(tmp) / "2.xml"
            build(src, out1)
            build(src, out2)
            self.assertEqual(out1.read_text(encoding="utf-8"), out2.read_text(encoding="utf-8"))
```

- [ ] **Step 3: Run it to make sure it fails**

```bash
.venv/Scripts/python -m unittest afenda.tools.tests.test_build_docs
```

Expected: `ModuleNotFoundError: No module named 'afenda.tools.build_docs'`.

- [ ] **Step 4: Write the tool**

Create `afenda/tools/build_docs.py`:

```python
"""Convert authored Markdown guides into committed QWeb templates.

    python -m afenda.tools.build_docs

Both the Markdown and the generated XML are committed; `test_guides_in_sync`
in afenda_api_docs asserts they agree, so a hand-edit of the XML is caught.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

import markdown

HERE = Path(__file__).resolve().parents[1]
SRC = HERE / "addons" / "afenda_api_docs" / "docs"
OUT = HERE / "addons" / "afenda_api_docs" / "views" / "guides.xml"


def slug_for(rel_path: str) -> str:
    return rel_path.removesuffix(".md").replace("/", "_").replace(".", "_")


def title_for(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def build(src_dir: Path, out_file: Path) -> int:
    pages = sorted(Path(src_dir).rglob("*.md"), key=lambda p: p.as_posix())
    parts = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>"]
    for page in pages:
        rel = page.relative_to(src_dir).as_posix()
        text = page.read_text(encoding="utf-8")
        body = markdown.markdown(text, extensions=["tables", "fenced_code"])
        parts.append(f'    <template id="guide_{slug_for(rel)}" name={quoteattr(title_for(text, rel))}>')
        parts.append('        <t t-call="web.frontend_layout">')
        parts.append('            <div class="container py-5 o_afenda_guide">')
        parts.append(body)
        parts.append("            </div>")
        parts.append("        </t>")
        parts.append("    </template>")
    parts.append("</odoo>")
    out_file.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    return len(pages)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=SRC)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    count = build(args.src, args.out)
    print(f"{count} guide(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and make sure they pass**

```bash
.venv/Scripts/python -m unittest afenda.tools.tests.test_build_docs
```

Expected: 3 tests PASS.

- [ ] **Step 6: Author one seed page and generate**

This plan delivers the mechanism plus one page. Writing the remaining guides is a separate, ongoing authoring effort and is explicitly not in scope here.

Create `afenda/addons/afenda_api_docs/docs/applications/general/users.md`:

```markdown
# Users and access rights

Every person who signs in to AFENDA xForge is a user record. A user belongs
to one or more groups, and groups are what grant access to an app.

## Adding a user

Open Settings, then Users, then New. Enter a name and an email address; the
email address is the login. Save, then use Send Password Reset Instructions
so the person sets their own password.

## Granting access to an app

On the user form, each installed app offers a level of access. Leave an app
blank to hide it from that user entirely.
```

Then generate and check the output:

```bash
.venv/Scripts/python -m afenda.tools.build_docs
cat afenda/addons/afenda_api_docs/views/guides.xml
```

Add `"views/guides.xml"` to `data` in `afenda/addons/afenda_api_docs/__manifest__.py`, after `"views/templates.xml"`.

- [ ] **Step 7: Commit**

```bash
git add afenda/tools/build_docs.py afenda/tools/tests/test_build_docs.py afenda/tools/requirements.txt
git add afenda/addons/afenda_api_docs/docs afenda/addons/afenda_api_docs/views/guides.xml afenda/addons/afenda_api_docs/__manifest__.py
git commit -m "[ADD] afenda/tools: build guide QWeb templates from Markdown

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Guide routes, the version segment, and the unwritten-page fallback

**Files:**
- Create: `afenda/addons/afenda_api_docs/controllers/guides.py`
- Create: `afenda/addons/afenda_api_docs/views/guides_chrome.xml`
- Create: `afenda/addons/afenda_api_docs/tests/test_guides.py`
- Modify: `afenda/addons/afenda_api_docs/tests/__init__.py`

**Interfaces:**
- Consumes: templates `afenda_api_docs.guide_<slug>` from Task 7.
- Produces: routes `/docs/applications/<path>` and `/docs/<version>/applications/<path>`.

The version segment exists only because the web client's `documentation_link` widget concatenates one — the live shape is `/docs/19.0/applications/...`. It is accepted and ignored; the generated documentation is not versioned.

- [ ] **Step 1: Write the failing tests**

Create `afenda/addons/afenda_api_docs/tests/test_guides.py`:

```python
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestGuideRoutes(HttpCase):
    def test_authored_page_renders(self):
        res = self.url_open("/docs/applications/general/users.html")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Users and access rights", res.text)

    def test_version_segment_is_accepted_and_ignored(self):
        # What the settings help icon actually emits.
        plain = self.url_open("/docs/applications/general/users.html")
        versioned = self.url_open("/docs/19.0/applications/general/users.html")
        self.assertEqual(versioned.status_code, 200)
        self.assertIn("Users and access rights", versioned.text)
        self.assertEqual(plain.status_code, versioned.status_code)

    def test_unwritten_page_is_a_page_not_a_404(self):
        res = self.url_open("/docs/19.0/applications/finance/nothing_here.html")
        self.assertEqual(res.status_code, 200)
        self.assertIn("not written", res.text.lower())

    def test_unwritten_page_does_not_leave_the_origin(self):
        res = self.url_open("/docs/19.0/applications/finance/nothing_here.html")
        self.assertNotIn("odoo.com", res.text)
        self.assertNotIn("Odoo", res.text)
```

Add `from . import test_guides` to `afenda/addons/afenda_api_docs/tests/__init__.py`.

- [ ] **Step 2: Run them to make sure they fail**

Same module test command. Expected: all four fail with 404.

- [ ] **Step 3: Add the routes**

Create `controllers/guides.py` with a class `AfendaGuidesController(http.Controller)` containing:

```python
    # The version segment is what the web client's documentation_link widget
    # concatenates ("/docs/" + serverVersion + path). Accept it and ignore it:
    # the generated documentation is not versioned.
    _VERSION = re.compile(r"^(?:\d+\.\d+|latest|master|saas-[\d.]+)$")

    @http.route(
        ["/docs/applications", "/docs/applications/<path:subpath>",
         "/docs/<string:version>/applications",
         "/docs/<string:version>/applications/<path:subpath>"],
        type="http", auth="public", website=False, sitemap=False,
    )
    def docs_guide(self, version=None, subpath=None, **kwargs):
        if version is not None and not self._VERSION.match(version):
            raise request.not_found()
        slug = (subpath or "index").removesuffix(".html").replace("/", "_").replace(".", "_")
        template = f"afenda_api_docs.guide_{slug}"
        if not request.env.ref(template, raise_if_not_found=False):
            return request.render("afenda_api_docs.guide_missing", {"subpath": subpath or ""})
        return request.render(template, {})
```

The file needs `import re` and the same `from odoo import http` / `from odoo.http import request` header as `landing.py`.

Create `views/guides_chrome.xml` with the usual wrapper containing:

```xml
    <template id="guide_missing" name="AFENDA guide not written yet">
        <t t-call="web.frontend_layout">
            <div class="container py-5">
                <h1>This guide is not written yet</h1>
                <p class="text-muted">
                    There is no page for <code t-esc="subpath"/> yet.
                </p>
                <p><a href="/docs">Back to the documentation index</a></p>
            </div>
        </t>
    </template>
```

- [ ] **Step 4: Run the tests and make sure they pass**

Same command. Expected: all four guide tests PASS.

- [ ] **Step 5: Commit**

```bash
git add afenda/addons/afenda_api_docs/controllers/main.py afenda/addons/afenda_api_docs/views/templates.xml afenda/addons/afenda_api_docs/tests/
git commit -m "[ADD] afenda_api_docs: guide routes with an ignored version segment

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Guide sync test, crawl, and the identity gate

**Files:**
- Create: `afenda/addons/afenda_api_docs/tests/test_identity.py`
- Modify: `afenda/addons/afenda_api_docs/tests/__init__.py`
- Modify: `afenda/README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing; this task closes the verification loop.

- [ ] **Step 1: Write the failing tests**

Create `afenda/addons/afenda_api_docs/tests/test_identity.py`:

```python
import pathlib
import tempfile

from odoo.tests import HttpCase, tagged

from afenda.tools.build_docs import build
from afenda.tools import rules as file_rules
from odoo.addons.afenda_api_docs.aliasing import alias_prose

ODOO_TELLS = ("Odoo", "odoo.com", "OdooBot", "Odoo S.A.")


@tagged("post_install", "-at_install")
class TestGuidesInSync(HttpCase):
    def test_generated_xml_matches_the_markdown(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        committed = (root / "views" / "guides.xml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "guides.xml"
            build(root / "docs", out)
            self.assertEqual(
                out.read_text(encoding="utf-8"),
                committed,
                "views/guides.xml is stale: run python -m afenda.tools.build_docs",
            )


@tagged("post_install", "-at_install")
class TestAliasingParity(HttpCase):
    def test_runtime_aliaser_agrees_with_the_file_rules_on_capitalised_text(self):
        # The runtime aliaser is deliberately broader (case-insensitive), but it
        # must never disagree with the build-time rules where both apply.
        for sample in ("Powered by Odoo", "Copyright Odoo S.A.", "Ask OdooBot"):
            expected = sample
            for rule in file_rules.RULES:
                if rule.suffixes is None and not rule.path_contains:
                    expected = rule.pattern.sub(rule.replacement, expected)
            self.assertEqual(alias_prose(sample), expected)


@tagged("post_install", "-at_install")
class TestDocsCrawl(HttpCase):
    def test_public_pages_carry_no_odoo_identity(self):
        for url in ("/docs", "/docs/applications/general/users.html",
                    "/docs/19.0/applications/finance/nothing_here.html"):
            res = self.url_open(url)
            self.assertEqual(res.status_code, 200, url)
            for tell in ODOO_TELLS:
                self.assertNotIn(tell, res.text, f"{tell} on {url}")

    def test_signed_in_pages_carry_no_odoo_identity_in_prose(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/api")
        self.assertEqual(res.status_code, 200)
        for tell in ODOO_TELLS:
            self.assertNotIn(tell, res.text)

    def test_wire_values_survive_in_the_document(self):
        self.authenticate("admin", "admin")
        doc = self.url_open("/docs/openapi.json").json()
        self.assertIn("res.partner", doc["components"]["schemas"])
        self.assertTrue(any(p.startswith("/json/2/res.partner/") for p in doc["paths"]))
```

Add `from . import test_identity` to `afenda/addons/afenda_api_docs/tests/__init__.py`.

- [ ] **Step 2: Run them and fix what they catch**

Same module test command. Every failure here is a real defect in an earlier task — fix the source, never the assertion. The likely catches: a literal "Odoo" written into a template or a docstring in `openapi.py`, and a stale `guides.xml`.

- [ ] **Step 3: Run the identity scanner**

```bash
.venv/Scripts/python -m afenda.tools.scan_identity
```

Expected: `delta +0`, exit 0. This module adds user-visible text, so any rise is text this plan introduced. If it rose, find the line and alias or reword it; do **not** raise `BASELINE`.

- [ ] **Step 4: Run the whole module suite plus the tooling suite**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda \
  -u afenda_api_docs,afenda_brand --test-enable --test-tags "/afenda_api_docs,/afenda_brand" \
  --stop-after-init --http-port 8179
.venv/Scripts/python -m unittest discover afenda/tools/tests
```

Expected: all green. `afenda_brand` is included because Task 1 removed a controller and a view from it.

- [ ] **Step 5: Document the tools**

In `afenda/README.md`, under "De-identification tools", add:

```bash
.venv/Scripts/python -m afenda.tools.build_docs       # regenerate guide QWeb from Markdown
```

And add a short section stating that `/docs` is served by `afenda_api_docs`; that guides are authored in `afenda/addons/afenda_api_docs/docs/` and the committed `views/guides.xml` is generated, never hand-edited; and that `/docs/openapi.json` is generated per request for the signed-in user.

- [ ] **Step 6: Commit**

```bash
git add afenda/addons/afenda_api_docs/tests afenda/README.md
git commit -m "[ADD] afenda_api_docs: guide sync, aliasing parity and crawl tests

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage.** Routes table → Tasks 1, 5, 6, 8. `get_public_method` delegation → Task 4 (`test_every_documented_method_is_actually_callable`). `fields_get` schemas → Task 3. App scoping via `ir.model.data`, not `ir.model.modules` → Task 5. Curated core set intersected with the registry → Task 5. Per-request generation, no cache in v1 → Task 5, with the 500 ms threshold measured in Step 5. Prose/wire aliasing → Task 2, enforced in Tasks 3, 4, 9. Case-insensitive prose rule → Task 2. Parity test against `afenda/tools/rules.py` → Task 9. Markdown → QWeb at build time with a sync test → Tasks 7, 9. Redoc vendored, no CDN → Task 6. `auth='user'` on `/docs/openapi.json` and `/docs/api` → Tasks 5, 6, asserted both ways. Meta-schema validation → **narrowed**: `jsonschema` is not installed and the OpenAPI 3.1 meta-schema would have to be vendored over the network, so Task 5 asserts structure and `$ref` resolution instead. That is a deliberate reduction from the spec, recorded here rather than silently dropped. Scanner gate → Task 9. Sequencing note about `afenda_brand` → Task 1, Step 1.

**Placeholders.** None. Task 7 Step 6 delivers one seed guide and says plainly that authoring the rest is out of scope, rather than leaving a "write the guides" stub.

**Type consistency.** `alias_prose` (Task 2) is the only aliasing entry point in Tasks 3, 4, 5, 9. `model_schema` (Task 3) is consumed by `build_document` (Task 5). `model_operations` and `path_item` (Task 4) are consumed by `build_document` (Task 5). `slug_for` (Task 7) and the slug expression in `docs_guide` (Task 8) must produce the same string — both are `removesuffix(".md"/".html")` then `replace("/", "_").replace(".", "_")`. `build` (Task 7) is reused by the sync test (Task 9).

## Known risk

Task 6 needs the Redoc bundle downloaded. If the environment has no network, that task stalls; everything before it still delivers a working `/docs` and a valid `/docs/openapi.json`, and `/docs/api` can be deferred without blocking Tasks 7 to 9.
