# Odoo De-identification, Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every user-visible trace of Odoo (strings, translations, links, `/odoo` URL prefix, logo images) from the 19.0 tree with a re-runnable, idempotent script, and prove it with tests.

**Architecture:** A stdlib-only Python tool `afenda/tools/rebrand.py` walks `addons/` and `odoo/`, applies an ordered list of regex rules line by line while skipping protected contexts (license headers, imports, machine endpoints), and reports per-rule counts. A companion `brand_images.py` renders AFENDA replacements for Odoo's image files under their original names. A scanner and HTTP crawl tests prove nothing Odoo-branded remains visible. Pristine upstream lives on `upstream-19.0`; `19.0` carries one `[REBRAND]` commit on top.

**Tech Stack:** Python 3.11 stdlib (`re`, `pathlib`, `argparse`, `unittest`), Pillow (already in `.venv`) for images, Odoo 19 `HttpCase` tests.

**Spec:** `docs/superpowers/specs/2026-09-22-odoo-deidentification-design.md`

## Global Constraints

- Never edit files under `afenda/` with the rebrand script; it only touches `addons/` and `odoo/`.
- Never change: the Python package `odoo`, `odoo-bin`, module technical names, database schema, source license headers ("Part of Odoo", "Odoo S.A." in headers), `LICENSE`, `COPYRIGHT`.
- Replacement values come from `afenda/addons/afenda_brand/brand.py`: product "AFENDA xForge", short "AFENDA", bot "AFENDA Bot", domain `afenda.app` (placeholder), documentation path `/docs/`.
- URL prefix `/odoo` becomes `/app`.
- Machine endpoints stay: lines containing `iap.odoo.com`, `iap-services.odoo.com`, `services.odoo.com`.
- The script must be idempotent: running it twice changes nothing the second time.
- All commands run from the repository root with the venv Python: `.venv/Scripts/python`.
- Odoo tests run from Git Bash with `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"` so `/module` tags are not turned into Windows paths, and with `--http-port 8179`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## File structure

| File | Responsibility |
|---|---|
| `afenda/addons/afenda_brand/brand.py` | Modify: add `domain` and `docs_path` keys. Single source of names. |
| `afenda/tools/__init__.py` | Empty, makes `afenda.tools` importable for tests. |
| `afenda/tools/rebrand.py` | Engine: file walk, `Rule`, protected contexts, `.po` awareness, dry-run/apply, CLI. |
| `afenda/tools/rules.py` | The ordered phase-1 rule list built from `brand.py`. |
| `afenda/tools/brand_images.py` | Renders AFENDA PNG/SVG/ICO files over Odoo's image paths. |
| `afenda/tools/scan_identity.py` | Reports remaining matches; exit code 1 if any. |
| `afenda/tools/tests/__init__.py` | Empty. |
| `afenda/tools/tests/test_rebrand.py` | Unit tests for engine and rules with fixture snippets. |
| `afenda/addons/afenda_brand/tests/test_identity.py` | HttpCase crawl asserting no Odoo identity on served surfaces. |
| `afenda/README.md` | Modify: upstream update procedure and tool usage. |

Tool tests run with: `.venv/Scripts/python -m unittest afenda.tools.tests.test_rebrand -v`

---

### Task 1: Brand values and branch layout

**Files:**
- Modify: `afenda/addons/afenda_brand/brand.py`
- Modify: `afenda/README.md`

**Interfaces:**
- Produces: `BRAND["domain"] == "afenda.app"`, `BRAND["docs_path"] == "/docs/"`, `BRAND["url_prefix"] == "app"`; git branch `upstream-19.0` at the pristine root commit.

- [ ] **Step 1: Add the new brand keys**

In `afenda/addons/afenda_brand/brand.py`, after `"bot": "AFENDA Bot",` add:

```python
    "domain": "afenda.app",  # placeholder until the real domain is known
    "docs_path": "/docs/",  # generated documentation, served same-origin (phase 3)
    "url_prefix": "app",  # browser address prefix, replaces "odoo"
```

- [ ] **Step 2: Create the pristine upstream branch**

The root commit `19ebd007` is the untouched Odoo snapshot.

```bash
git branch upstream-19.0 19ebd007
git push -u origin upstream-19.0
git branch -a | grep upstream
```

Expected: `upstream-19.0` listed locally and as `remotes/origin/upstream-19.0`.

- [ ] **Step 3: Document the update procedure**

Append to `afenda/README.md`:

```markdown
## Branches and upstream updates

- `upstream-19.0`: pristine odoo/odoo. Never edit.
- `19.0`: `upstream-19.0` + the `[REBRAND]` commit + the `afenda/` layer. This deploys.

To take an Odoo update:

```bash
git fetch upstream 19.0
git checkout upstream-19.0 && git merge --ff-only upstream/19.0 && git push
git checkout 19.0 && git merge upstream-19.0        # resolve conflicts if any
.venv/Scripts/python -m afenda.tools.rebrand --apply # re-brands only what is new
.venv/Scripts/python -m afenda.tools.scan_identity   # must print 0 remaining
git commit -am "[REBRAND] re-apply after upstream merge"
```

Note: `upstream/19.0` history is unrelated to our rewritten root, so the
first merge needs `--allow-unrelated-histories`; see the spec for why the
root was rewritten.
```

- [ ] **Step 4: Commit**

```bash
git add afenda/addons/afenda_brand/brand.py afenda/README.md
git commit -m "[IMP] afenda: brand domain, docs path, url prefix; document upstream flow

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Rebrand engine core

**Files:**
- Create: `afenda/tools/__init__.py` (empty)
- Create: `afenda/tools/tests/__init__.py` (empty)
- Create: `afenda/tools/rebrand.py`
- Test: `afenda/tools/tests/test_rebrand.py`

**Interfaces:**
- Produces:
  - `class Rule(name: str, pattern: re.Pattern, replacement: str, suffixes: frozenset[str] | None = None, path_contains: tuple[str, ...] = (), path_excludes: tuple[str, ...] = ())` with `applies_to(path: Path) -> bool`
  - `rewrite_text(text: str, rules: list[Rule], path: Path) -> tuple[str, dict[str, int]]`
  - `iter_files(root: Path) -> Iterator[Path]`
  - `run(root: Path, rules: list[Rule], apply: bool) -> dict[str, int]`
  - CLI: `python -m afenda.tools.rebrand [--apply] [--root PATH]`

- [ ] **Step 1: Write the failing tests**

`afenda/tools/tests/test_rebrand.py`:

```python
import re
import tempfile
import unittest
from pathlib import Path

from afenda.tools.rebrand import Rule, iter_files, rewrite_text, run

PRODUCT = Rule("product", re.compile(r"(?<![\w\-@/.])Odoo(?![\w\-])"), "AFENDA xForge")


class RewriteTextTests(unittest.TestCase):
    def test_replaces_standalone_word(self):
        out, counts = rewrite_text('title = _("Welcome to Odoo")\n', [PRODUCT], Path("a.py"))
        self.assertEqual(out, 'title = _("Welcome to AFENDA xForge")\n')
        self.assertEqual(counts, {"product": 1})

    def test_leaves_identifiers_alone(self):
        src = "class OdooEditor:\n    pass\nX_ODOO = 'X-Odoo-Database'\n"
        out, counts = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertEqual(out, src)
        self.assertEqual(counts, {})

    def test_skips_license_header_in_code(self):
        src = "# Part of Odoo. See LICENSE file.\n# Copyright Odoo S.A.\nname = 'Odoo'\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertTrue(out.startswith("# Part of Odoo. See LICENSE file.\n# Copyright Odoo S.A.\n"))
        self.assertIn("name = 'AFENDA xForge'", out)

    def test_skips_import_lines(self):
        src = "from odoo import Odoo\nimport Odoo.things\nlabel = 'Odoo'\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertIn("from odoo import Odoo\n", out)
        self.assertIn("import Odoo.things\n", out)
        self.assertIn("label = 'AFENDA xForge'", out)

    def test_copyright_is_not_protected_in_markup(self):
        src = "<small>Copyright 2004 Odoo</small>\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("t.xml"))
        self.assertEqual(out, "<small>Copyright 2004 AFENDA xForge</small>\n")

    def test_noqa_marker_protects_line(self):
        src = "x = 'Odoo'  # noqa: rebrand\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertEqual(out, src)

    def test_machine_endpoints_protected(self):
        src = "URL = 'https://iap.odoo.com/Odoo'\nURL2 = 'https://iap-services.odoo.com'\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertEqual(out, src)

    def test_po_only_touches_msgid_and_msgstr(self):
        src = (
            '#. module: base\n'
            '#: model:ir.module.module,shortdesc:base.module_Odoo\n'
            'msgid "Odoo"\n'
            'msgstr "Odoo"\n'
            'msgid ""\n'
            '"Welcome to Odoo, "\n'
            '"the suite"\n'
            'msgstr ""\n'
        )
        out, counts = rewrite_text(src, [PRODUCT], Path("fr.po"))
        self.assertIn('#: model:ir.module.module,shortdesc:base.module_Odoo\n', out)
        self.assertIn('msgid "AFENDA xForge"\n', out)
        self.assertIn('msgstr "AFENDA xForge"\n', out)
        self.assertIn('"Welcome to AFENDA xForge, "\n', out)
        self.assertEqual(counts, {"product": 3})

    def test_rule_suffix_and_path_filters(self):
        only_xml = Rule("x", re.compile("Odoo"), "A", suffixes=frozenset({".xml"}))
        self.assertTrue(only_xml.applies_to(Path("v.xml")))
        self.assertFalse(only_xml.applies_to(Path("v.py")))
        router = Rule("r", re.compile("Odoo"), "A", path_contains=("core/browser/router.js",))
        self.assertTrue(router.applies_to(Path("addons/web/static/src/core/browser/router.js")))
        self.assertFalse(router.applies_to(Path("addons/web/static/src/other.js")))
        no_iot = Rule("n", re.compile("Odoo"), "A", path_excludes=("iot_box_image",))
        self.assertFalse(no_iot.applies_to(Path("addons/iot_box_image/x.py")))

    def test_idempotent(self):
        src = "a = 'Odoo Odoo'\n"
        once, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        twice, counts = rewrite_text(once, [PRODUCT], Path("a.py"))
        self.assertEqual(once, twice)
        self.assertEqual(counts, {})


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "addons" / "m").mkdir(parents=True)
        (self.root / "odoo").mkdir()
        (self.root / "afenda").mkdir()
        (self.root / ".git").mkdir()
        (self.root / "addons" / "m" / "v.xml").write_text("<t>Odoo</t>\n", encoding="utf-8")
        (self.root / "addons" / "m" / "logo.png").write_bytes(b"\x89PNG Odoo")
        (self.root / "odoo" / "x.py").write_text("s = 'Odoo'\n", encoding="utf-8")
        (self.root / "afenda" / "y.py").write_text("s = 'Odoo'\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_iter_files_scans_only_text_in_addons_and_odoo(self):
        rel = sorted(p.relative_to(self.root).as_posix() for p in iter_files(self.root))
        self.assertEqual(rel, ["addons/m/v.xml", "odoo/x.py"])

    def test_dry_run_changes_nothing_and_counts(self):
        counts = run(self.root, [PRODUCT], apply=False)
        self.assertEqual(counts, {"product": 2})
        self.assertEqual((self.root / "odoo" / "x.py").read_text(encoding="utf-8"), "s = 'Odoo'\n")

    def test_apply_writes_files(self):
        run(self.root, [PRODUCT], apply=True)
        self.assertEqual((self.root / "odoo" / "x.py").read_text(encoding="utf-8"), "s = 'AFENDA xForge'\n")
        self.assertEqual((self.root / "addons" / "m" / "v.xml").read_text(encoding="utf-8"), "<t>AFENDA xForge</t>\n")
        self.assertEqual((self.root / "afenda" / "y.py").read_text(encoding="utf-8"), "s = 'Odoo'\n")
        self.assertEqual(run(self.root, [PRODUCT], apply=False), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_rebrand -v`
Expected: `ModuleNotFoundError: No module named 'afenda.tools.rebrand'`

- [ ] **Step 3: Write the engine**

Create empty `afenda/tools/__init__.py` and `afenda/tools/tests/__init__.py`.

`afenda/tools/rebrand.py`:

```python
"""Rewrite Odoo identity in the upstream tree by rules.

Usage (from the repository root):
    python -m afenda.tools.rebrand            # dry run: per-rule counts
    python -m afenda.tools.rebrand --apply    # write changes

Only ``addons/`` and ``odoo/`` are scanned; ``afenda/`` is never touched.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SCAN_DIRS = ("addons", "odoo")
SKIP_DIRS = {".git", ".venv", "afenda", "node_modules", "__pycache__", "docs"}
TEXT_SUFFIXES = frozenset({
    ".py", ".js", ".ts", ".xml", ".html", ".md", ".rst", ".txt", ".po", ".pot",
    ".scss", ".css", ".json", ".csv", ".template", ".cfg", ".conf", ".ini",
    ".yml", ".yaml", ".sh", ".sql",
})
CODE_SUFFIXES = frozenset({".py", ".js", ".ts", ".scss", ".css"})
PO_SUFFIXES = frozenset({".po", ".pot"})

# Lines never rewritten, in any file.
PROTECTED_ALWAYS = re.compile(
    r"noqa: rebrand|iap\.odoo\.com|iap-services\.odoo\.com|services\.odoo\.com"
)
# Lines never rewritten in code files: license headers, imports, module loader.
PROTECTED_IN_CODE = re.compile(
    r"Part of Odoo|Copyright|^\s*(from|import)\s|odoo\.define\(|require\("
)
# In .po files only these lines carry user-visible text.
PO_TEXT_LINE = re.compile(r'^(msgid |msgstr|msgid_plural |")')


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    replacement: str
    suffixes: frozenset[str] | None = None
    path_contains: tuple[str, ...] = ()
    path_excludes: tuple[str, ...] = ()

    def applies_to(self, path: Path) -> bool:
        posix = path.as_posix()
        if self.suffixes is not None and path.suffix not in self.suffixes:
            return False
        if self.path_contains and not any(s in posix for s in self.path_contains):
            return False
        if any(s in posix for s in self.path_excludes):
            return False
        return True


def _is_protected(line: str, path: Path) -> bool:
    if PROTECTED_ALWAYS.search(line):
        return True
    if path.suffix in CODE_SUFFIXES and PROTECTED_IN_CODE.search(line):
        return True
    if path.suffix in PO_SUFFIXES and not PO_TEXT_LINE.match(line):
        return True
    return False


def rewrite_text(text: str, rules: list[Rule], path: Path) -> tuple[str, dict[str, int]]:
    """Return (new_text, counts). counts maps rule name to replacements made."""
    counts: dict[str, int] = {}
    active = [r for r in rules if r.applies_to(path)]
    if not active:
        return text, counts
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if not _is_protected(line, path):
            for rule in active:
                line, n = rule.pattern.subn(rule.replacement, line)
                if n:
                    counts[rule.name] = counts.get(rule.name, 0) + n
        out.append(line)
    return "".join(out), counts


def iter_files(root: Path) -> Iterator[Path]:
    for top in SCAN_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                yield path


def run(root: Path, rules: list[Rule], apply: bool) -> dict[str, int]:
    totals: dict[str, int] = {}
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text, counts = rewrite_text(text, rules, path.relative_to(root))
        for name, n in counts.items():
            totals[name] = totals.get(name, 0) + n
        if apply and counts:
            path.write_text(new_text, encoding="utf-8", newline="")
    return totals


def main(argv: list[str] | None = None) -> int:
    from afenda.tools.rules import RULES

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    totals = run(args.root, RULES, apply=args.apply)
    mode = "applied" if args.apply else "would apply"
    for name, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"{n:8d}  {name}")
    print(f"{sum(totals.values()):8d}  total ({mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note on line endings: `read_text` normalizes `\r\n` to `\n`, and `write_text(..., newline="")` writes `\n` back unchanged. Odoo's tree is LF throughout and this checkout has `core.autocrlf=input`, so rewritten files keep LF and untouched files are never written.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_rebrand -v`
Expected: all 13 tests PASS. (The `main()` import of `afenda.tools.rules` is lazy, so the missing module does not break tests yet.)

- [ ] **Step 5: Commit**

```bash
git add afenda/tools/__init__.py afenda/tools/rebrand.py afenda/tools/tests/__init__.py afenda/tools/tests/test_rebrand.py
git commit -m "[ADD] afenda/tools: rebrand engine with protected contexts and .po awareness

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Phase-1 rule set

**Files:**
- Create: `afenda/tools/rules.py`
- Test: `afenda/tools/tests/test_rebrand.py` (append `RulesTests`)

**Interfaces:**
- Consumes: `Rule`, `rewrite_text` from Task 2; `BRAND` from Task 1.
- Produces: `RULES: list[Rule]` in application order; `load_brand() -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `afenda/tools/tests/test_rebrand.py`:

```python
from afenda.tools.rules import RULES, load_brand


class RulesTests(unittest.TestCase):
    def rw(self, text, name):
        out, _ = rewrite_text(text, RULES, Path(name))
        return out

    def test_brand_values_loaded(self):
        b = load_brand()
        self.assertEqual(b["product"], "AFENDA xForge")
        self.assertEqual(b["url_prefix"], "app")

    def test_company_name_in_markup_becomes_short_name(self):
        self.assertEqual(self.rw("<a>Odoo S.A.</a>\n", "t.xml"), "<a>AFENDA</a>\n")
        self.assertEqual(self.rw('msgid "Odoo S.A."\n', "fr.po"), 'msgid "AFENDA"\n')

    def test_company_name_in_code_header_untouched(self):
        src = "# Copyright 2004 Odoo S.A.\n"
        self.assertEqual(self.rw(src, "a.py"), src)

    def test_bot(self):
        self.assertEqual(self.rw('name = _("OdooBot")\n', "a.py"), 'name = _("AFENDA Bot")\n')
        self.assertEqual(self.rw("state = user.odoobot_state\n", "a.py"), "state = user.odoobot_state\n")

    def test_documentation_links_go_same_origin(self):
        self.assertEqual(
            self.rw('href="https://www.odoo.com/documentation/19.0/applications/sales.html"\n', "v.xml"),
            'href="/docs/applications/sales.html"\n',
        )
        self.assertEqual(
            self.rw("url = 'https://www.odoo.com/documentation/latest/'\n", "a.py"),
            "url = '/docs/'\n",
        )

    def test_other_odoo_com_links_go_to_domain(self):
        self.assertEqual(self.rw("https://www.odoo.com?utm_source=db\n", "v.xml"), "https://www.afenda.app?utm_source=db\n")
        self.assertEqual(self.rw("https://accounts.odoo.com/account\n", "u.js"), "https://accounts.afenda.app/account\n")
        self.assertEqual(self.rw("info@odoo.com\n", "d.xml"), "info@afenda.app\n")

    def test_iap_endpoints_survive(self):
        src = "DEFAULT_ENDPOINT = 'https://iap.odoo.com'\n"
        self.assertEqual(self.rw(src, "a.py"), src)

    def test_url_prefix(self):
        self.assertEqual(self.rw("return request.redirect_query('/odoo', query=q)\n", "h.py"), "return request.redirect_query('/app', query=q)\n")
        self.assertEqual(self.rw("@http.route(['/web', '/odoo', '/odoo/<path:subpath>'])\n", "h.py"), "@http.route(['/web', '/app', '/app/<path:subpath>'])\n")
        self.assertEqual(self.rw('browser.location.pathname.startsWith("/odoo")\n', "r.js"), 'browser.location.pathname.startsWith("/app")\n')
        self.assertEqual(self.rw("goto('/odoo/action-108?debug=1')\n", "t.js"), "goto('/app/action-108?debug=1')\n")
        self.assertEqual(self.rw("path = '/home/odoo/bin'\n", "a.py"), "path = '/home/odoo/bin'\n")
        self.assertEqual(self.rw("ExecStart=/odoo/odoo-bin\n", "addons/iot_box_image/odoo.service"), "ExecStart=/odoo/odoo-bin\n")

    def test_router_prefix_constants(self):
        router = "addons/web/static/src/core/browser/router.js"
        self.assertEqual(self.rw('return isScopedApp() ? "scoped_app" : "odoo";\n', router), 'return isScopedApp() ? "scoped_app" : "app";\n')
        self.assertEqual(self.rw('if (["odoo", "scoped_app"].includes(prefix)) {\n', router), 'if (["app", "scoped_app"].includes(prefix)) {\n')
        self.assertEqual(self.rw('x = "odoo";\n', "addons/web/static/src/other.js"), 'x = "odoo";\n')

    def test_product_word_last(self):
        self.assertEqual(self.rw("<h1>Odoo Enterprise</h1>\n", "v.xml"), "<h1>AFENDA xForge Enterprise</h1>\n")
        self.assertEqual(self.rw("Sent by Odoo\n", "v.xml"), "Sent by AFENDA xForge\n")

    def test_rules_are_idempotent_on_own_output(self):
        samples = [
            ("<a>Odoo S.A.</a> Odoo OdooBot https://www.odoo.com/documentation/19.0/x https://odoo.com /odoo/x\n", "v.xml"),
            ('msgid "Odoo"\nmsgstr "Odoo S.A."\n', "fr.po"),
        ]
        for text, name in samples:
            once = self.rw(text, name)
            self.assertEqual(self.rw(once, name), once)
            self.assertNotIn("Odoo", once)
            self.assertNotIn("odoo.com", once)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_rebrand -v`
Expected: `ModuleNotFoundError: No module named 'afenda.tools.rules'`

- [ ] **Step 3: Write the rules**

`afenda/tools/rules.py`:

```python
"""Ordered phase-1 rules. Later rules see the output of earlier ones."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from afenda.tools.rebrand import Rule

MARKUP = frozenset({".xml", ".html", ".js", ".ts", ".po", ".pot", ".md", ".rst", ".json", ".csv"})
URLISH = frozenset({".py", ".js", ".ts", ".xml", ".html", ".md", ".rst", ".po", ".pot", ".json", ".csv"})
ROUTER = "addons/web/static/src/core/browser/router.js"


def load_brand() -> dict:
    path = Path(__file__).resolve().parents[1] / "addons" / "afenda_brand" / "brand.py"
    spec = importlib.util.spec_from_file_location("afenda_brand_values", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BRAND


def build_rules(brand: dict) -> list[Rule]:
    product, short, bot = brand["product"], brand["short"], brand["bot"]
    domain, docs, prefix = brand["domain"], brand["docs_path"], brand["url_prefix"]
    return [
        # 1. Legal name in user-facing markup and translations only.
        Rule("company_name", re.compile(r"Odoo S\.A\."), short, suffixes=MARKUP),
        # 2. The system bot.
        Rule("bot", re.compile(r"OdooBot"), bot),
        # 3. Documentation links become same-origin generated docs.
        Rule(
            "docs_link",
            re.compile(r"https?://(?:www\.)?odoo\.com/documentation/(?:\d+\.\d+|latest|master|saas-[\d.]+)/?"),
            docs,
        ),
        # 4. Every other odoo.com host or address.
        Rule("odoo_com", re.compile(r"\bodoo\.com\b"), domain),
        # 5. Browser address prefix. Not filesystem paths (/home/odoo), not the IoT image.
        Rule(
            "url_prefix",
            re.compile(r"(?<![\w.])/odoo(?=[/'\"`?#\s)\]]|$)"),
            f"/{prefix}",
            suffixes=URLISH,
            path_excludes=("iot_box_image",),
        ),
        Rule("router_prefix", re.compile(r'"odoo"'), f'"{prefix}"', path_contains=(ROUTER,)),
        # 6. The product name, standalone word only, last so earlier rules win.
        Rule("product", re.compile(r"(?<![\w\-@/.])Odoo(?![\w\-])"), product),
    ]


RULES: list[Rule] = build_rules(load_brand())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_rebrand -v`
Expected: all tests PASS (13 engine + 11 rules).

If `test_url_prefix` fails on `/home/odoo/bin`: the lookbehind `(?<![\w.])` must reject the `e` before `/odoo`; it does. If it fails on the `.service` line: that file has no suffix in `URLISH`, so the rule must not apply; confirm `Path(...).suffix == ".service"`.

- [ ] **Step 5: Dry-run against the real tree and read the counts**

Run: `.venv/Scripts/python -m afenda.tools.rebrand`
Expected: a table like

```
  10xxxx  product
    5xx   company_name
    1xxx  odoo_com
    xxx   url_prefix
    xx    docs_link
    xx    bot
    2     router_prefix
```

Sanity checks before continuing: `router_prefix` must be exactly 2. `product` must be roughly 100,000 to 110,000 (translations dominate). If `product` is below 90,000 the `.po` line filter is too strict; if above 130,000 a protection failed.

- [ ] **Step 6: Commit**

```bash
git add afenda/tools/rules.py afenda/tools/tests/test_rebrand.py
git commit -m "[ADD] afenda/tools: phase-1 rebrand rules

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Brand images over Odoo's image files

**Files:**
- Create: `afenda/tools/brand_images.py`
- Test: `afenda/tools/tests/test_brand_images.py`

**Interfaces:**
- Consumes: nothing from other tasks (geometry is the v2.1 mark spec in memory/spec).
- Produces: `TARGETS: dict[str, str]` mapping repo-relative image path to a kind in `{"tile_png", "tile_svg", "tile_ico", "lockup_png", "lockup_svg", "lockup_dark_svg", "mark_png"}`; `render_all(root: Path) -> list[Path]`; CLI `python -m afenda.tools.brand_images`.

- [ ] **Step 1: Write the failing test**

`afenda/tools/tests/test_brand_images.py`:

```python
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from afenda.tools.brand_images import TARGETS, render_all


class BrandImagesTests(unittest.TestCase):
    def test_renders_every_target_with_expected_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = render_all(root)
            self.assertEqual(sorted(p.relative_to(root).as_posix() for p in written), sorted(TARGETS))
            for rel, kind in TARGETS.items():
                data = (root / rel).read_bytes()
                if rel.endswith(".svg"):
                    self.assertTrue(data.startswith(b"<svg"), rel)
                    self.assertNotIn(b"Odoo", data)
                elif rel.endswith(".ico"):
                    self.assertTrue(data.startswith(b"\x00\x00\x01\x00"), rel)
                else:
                    im = Image.open(io.BytesIO(data))
                    self.assertEqual(im.format, "PNG", rel)
                    if kind == "tile_png":
                        self.assertEqual(im.width, im.height, rel)

    def test_sizes_match_odoo_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_all(root)
            expect = {
                "addons/web/static/img/odoo-icon-192x192.png": (192, 192),
                "addons/web/static/img/odoo-icon-512x512.png": (512, 512),
                "addons/web/static/img/odoo-icon-ios.png": (512, 512),
                "addons/web/static/img/odoo_logo_tiny.png": (186, 60),
                "addons/web/static/img/logo.png": (180, 79),
                "addons/mail/static/src/img/odoo_o.png": (100, 100),
                "odoo/addons/base/static/img/res_company_logo.png": (450, 120),
            }
            for rel, size in expect.items():
                self.assertEqual(Image.open(root / rel).size, size, rel)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_brand_images -v`
Expected: `ModuleNotFoundError: No module named 'afenda.tools.brand_images'`

- [ ] **Step 3: Write the renderer**

`afenda/tools/brand_images.py`:

```python
"""Render AFENDA images over the paths where Odoo ships its own logos.

Keeping Odoo's file names means the 300 templates that reference them
need no change. Run after the rebrand script:
    python -m afenda.tools.brand_images
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BLUE = (30, 58, 138)
INK = (15, 23, 42)
PAPER = (247, 247, 245)
WHITE = (255, 255, 255)
SS = 8  # supersampling factor

FONTS = Path(__file__).resolve().parents[1] / "addons" / "afenda_brand" / "static" / "fonts"

# repo-relative path -> kind
TARGETS: dict[str, str] = {
    "addons/web/static/img/favicon.ico": "tile_ico",
    "addons/web/static/img/odoo-icon-192x192.png": "tile_png",
    "addons/web/static/img/odoo-icon-512x512.png": "tile_png",
    "addons/web/static/img/odoo-icon-ios.png": "tile_png",
    "addons/web/static/img/odoo-icon.svg": "tile_svg",
    "addons/web/static/img/odoo_logo.svg": "lockup_svg",
    "addons/web/static/img/odoo_logo_dark.svg": "lockup_dark_svg",
    "addons/web/static/img/odoo_logo_tiny.png": "lockup_png",
    "addons/web/static/img/logo.png": "lockup_png",
    "addons/web/static/img/logo2.png": "lockup_png",
    "addons/mail/static/src/img/odoobot.png": "tile_png",
    "addons/mail/static/src/img/odoobot_transparent.png": "mark_png",
    "addons/mail/static/src/img/odoo_o.png": "mark_png",
    "addons/account/static/src/img/Odoo_logo_O.svg": "tile_svg",
    "odoo/addons/base/static/img/res_company_logo.png": "lockup_png",
}

SIZES: dict[str, tuple[int, int]] = {
    "addons/web/static/img/odoo-icon-192x192.png": (192, 192),
    "addons/web/static/img/odoo-icon-512x512.png": (512, 512),
    "addons/web/static/img/odoo-icon-ios.png": (512, 512),
    "addons/web/static/img/odoo_logo_tiny.png": (186, 60),  # Odoo ships 62x20; 3x for retina, templates set height 1em
    "addons/web/static/img/logo.png": (180, 79),
    "addons/web/static/img/logo2.png": (300, 131),
    "addons/mail/static/src/img/odoobot.png": (512, 512),
    "addons/mail/static/src/img/odoobot_transparent.png": (512, 512),
    "addons/mail/static/src/img/odoo_o.png": (100, 100),
    "odoo/addons/base/static/img/res_company_logo.png": (450, 120),
}

MARK_SVG_INNER = (
    '<path d="M32 12 L50 42 H41 L32 27 L23 42 H14 Z" fill="{fg}" stroke="{fg}" stroke-width="2.5" stroke-linejoin="round"/>'
    '<rect x="14" y="46" width="36" height="4" rx="2" fill="{fg}"/>'
    '<rect x="14" y="52" width="36" height="4" rx="2" fill="{fg}"/>'
)


def tile_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#1E3A8A"/>' + MARK_SVG_INNER.format(fg="#FFFFFF") + "</svg>\n"
    )


def lockup_svg(ink: str, sub: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="80" viewBox="0 0 360 80">'
        '<g transform="translate(8 8)"><rect width="64" height="64" rx="12" fill="#1E3A8A"/>'
        + MARK_SVG_INNER.format(fg="#FFFFFF")
        + "</g>"
        f'<text x="90" y="46" font-family="\'Source Serif 4\', Georgia, serif" font-weight="600" font-size="36" letter-spacing="1.8" fill="{ink}">AFENDA</text>'
        f'<text x="90" y="70" font-family="\'Source Sans 3\', Arial, sans-serif" font-weight="500" font-size="20" fill="{sub}">xForge</text>'
        "</svg>\n"
    )


def _rounded(d: ImageDraw.ImageDraw, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def _mark(d: ImageDraw.ImageDraw, s: float, fg, box_mark=True):
    pts = [(32, 12), (50, 42), (41, 42), (32, 27), (23, 42), (14, 42)] if box_mark else [(32, 2), (56, 46), (44, 46), (32, 24), (20, 46), (8, 46)]
    d.polygon([(x * s, y * s) for x, y in pts], fill=fg)
    if box_mark:
        _rounded(d, (14 * s, 46 * s, 50 * s, 50 * s), 2 * s, fg)
        _rounded(d, (14 * s, 52 * s, 50 * s, 56 * s), 2 * s, fg)
    else:
        _rounded(d, (6 * s, 50 * s, 58 * s, 55 * s), 2.5 * s, fg)
        _rounded(d, (6 * s, 58 * s, 58 * s, 63 * s), 2.5 * s, fg)


def tile_png(size: int) -> Image.Image:
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _rounded(d, (0, 0, big - 1, big - 1), big * 12 / 64, BLUE)
    _mark(d, big / 64, WHITE)
    return im.resize((size, size), Image.LANCZOS)


def mark_png(size: int) -> Image.Image:
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    _mark(ImageDraw.Draw(im), big / 64, BLUE, box_mark=False)
    return im.resize((size, size), Image.LANCZOS)


def _font(name: str, size: int, **axes) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    ax = f.get_variation_axes()
    names = [a["name"].decode() if isinstance(a["name"], bytes) else a["name"] for a in ax]
    f.set_variation_by_axes([axes.get(n, a["default"]) for a, n in zip(ax, names)])
    return f


def lockup_png(width: int, height: int, ink=INK, sub=BLUE) -> Image.Image:
    W, H, S = 1200, 300, 4
    im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    im.alpha_composite(tile_png(220 * S), (40 * S, 40 * S))
    serif = _font("SourceSerif4-VF.ttf", 150 * S, **{"Optical Size": 60, "Weight": 600})
    sans = _font("SourceSans3-VF.ttf", 78 * S, **{"Weight": 500})
    x = cx = 300 * S
    for ch in "AFENDA":
        d.text((cx, 62 * S), ch, font=serif, fill=ink)
        cx += d.textlength(ch, font=serif) + 4 * S
    d.text((x + 4 * S, 200 * S), "xForge", font=sans, fill=sub)
    im = im.resize((W, H), Image.LANCZOS)
    # Fit into the requested box, centered, keeping aspect ratio.
    scale = min(width / W, height / H)
    inner = im.resize((max(1, int(W * scale)), max(1, int(H * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(inner, ((width - inner.width) // 2, (height - inner.height) // 2))
    return canvas


def render_all(root: Path) -> list[Path]:
    written: list[Path] = []
    for rel, kind in TARGETS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "tile_svg":
            path.write_text(tile_svg(), encoding="utf-8")
        elif kind == "lockup_svg":
            path.write_text(lockup_svg("#0F172A", "#1E3A8A"), encoding="utf-8")
        elif kind == "lockup_dark_svg":
            path.write_text(lockup_svg("#F7F7F5", "#A5B4FC"), encoding="utf-8")
        elif kind == "tile_ico":
            tile_png(64).save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        elif kind == "tile_png":
            w, h = SIZES[rel]
            tile_png(w).save(path)
        elif kind == "mark_png":
            w, h = SIZES[rel]
            mark_png(w).save(path)
        elif kind == "lockup_png":
            w, h = SIZES[rel]
            lockup_png(w, h).save(path)
        else:
            raise ValueError(kind)
        written.append(path)
    return written


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    for p in render_all(root):
        print(p.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_brand_images -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add afenda/tools/brand_images.py afenda/tools/tests/test_brand_images.py
git commit -m "[ADD] afenda/tools: render AFENDA images over Odoo's logo paths

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Apply the rebrand to the tree

**Files:**
- Modify: thousands of files under `addons/` and `odoo/` (by script only).
- Modify: `afenda/odoo.conf` (no change needed; kept for reference).

**Interfaces:**
- Consumes: `afenda.tools.rebrand`, `afenda.tools.brand_images`.
- Produces: one commit `[REBRAND] apply phase-1 rules`.

- [ ] **Step 1: Confirm a clean tree and dry-run**

```bash
git status --short | wc -l        # must print 0
.venv/Scripts/python -m afenda.tools.rebrand | tail -8
```

- [ ] **Step 2: Apply text rules and images**

```bash
.venv/Scripts/python -m afenda.tools.rebrand --apply | tail -8
.venv/Scripts/python -m afenda.tools.brand_images
.venv/Scripts/python -m afenda.tools.rebrand | tail -1   # must print "0  total (would apply)"
git status --short | wc -l
```

- [ ] **Step 3: Spot-check the highest-risk edits**

```bash
git diff addons/web/controllers/home.py addons/web/static/src/core/browser/router.js addons/web/controllers/webmanifest.py | head -80
git diff --stat | tail -1
git diff odoo/http.py | grep -E "^[-+]" | grep -vi "X-Odoo" | head -20
```

Expected: routes now `['/web', '/app', '/app/<path:subpath>', ...]`; router constants `"app"`; `X-Odoo-Database` header untouched; `odoo/http.py` changes limited to user-facing strings in error pages.

- [ ] **Step 4: Compile check**

```bash
.venv/Scripts/python -m compileall -q odoo addons > /dev/null && echo "python ok"
```

Expected: `python ok`. If a syntax error appears, the rule broke a string; inspect the file, add a `# noqa: rebrand` marker to that line in a follow-up commit and re-apply.

- [ ] **Step 5: Reinstall the dev database and run the branding tests**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda2 -i afenda_brand --stop-after-init --without-demo=all --http-port 8179 --log-level=warn
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda2 -u afenda_brand --test-enable --test-tags "/afenda_brand" --stop-after-init --http-port 8179 --log-level=test
```

Expected: install without ERROR lines; `0 failed, 0 error(s) of 7 tests`. `test_webclient_page_is_branded` fetches `/odoo`; it now redirects to `/app` and still returns the branded page. If it fails with 404, change the URL in that test to `/app` in the same commit as Task 6.

- [ ] **Step 6: Run Odoo's own web and http tests**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda2 -u web,test_http --test-enable --test-tags "/web,/test_http" --stop-after-init --http-port 8179 --log-level=test --logfile=/tmp/odoo-web-tests.log
grep -E "failed, [0-9]+ error" /tmp/odoo-web-tests.log | tail -1
grep -E "FAIL:|ERROR:" /tmp/odoo-web-tests.log | head -20
```

Expected: failures only from browser-based tests (`browser_js`, `hoot`) reporting Chrome is missing, which say "Chrome not found" or are skipped. Any Python-level failure mentioning `/odoo`, `/app`, redirect, or routing must be fixed before committing: the usual cause is a test asserting a literal `/odoo` path that the rule did not rewrite because it sat on a protected line; rewrite that assertion by hand.

- [ ] **Step 7: Commit the rebrand**

```bash
git add -A addons odoo
git commit -m "[REBRAND] apply phase-1 rules: names, links, /app prefix, images

Generated by afenda/tools/rebrand.py and afenda/tools/brand_images.py.
Re-run both after every upstream merge.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Identity scanner and crawl tests

**Files:**
- Create: `afenda/tools/scan_identity.py`
- Create: `afenda/addons/afenda_brand/tests/test_identity.py`
- Modify: `afenda/addons/afenda_brand/tests/__init__.py`
- Modify: `afenda/addons/afenda_brand/tests/test_branding.py` (URL `/odoo` → `/app` if not done in Task 5)

**Interfaces:**
- Consumes: `run`, `RULES` from Tasks 2 and 3.
- Produces: `python -m afenda.tools.scan_identity` exit 0 when clean, 1 otherwise; `TestIdentity` HttpCase.

- [ ] **Step 1: Write the scanner**

`afenda/tools/scan_identity.py`:

```python
"""Report Odoo identity still present in addons/ and odoo/. Exit 1 if any."""
from __future__ import annotations

import sys
from pathlib import Path

from afenda.tools.rebrand import run
from afenda.tools.rules import RULES


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    totals = run(root, RULES, apply=False)
    for name, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"{n:8d}  {name}")
    remaining = sum(totals.values())
    print(f"{remaining:8d}  remaining")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `.venv/Scripts/python -m afenda.tools.scan_identity`
Expected: `0  remaining`, exit code 0.

- [ ] **Step 2: Write the failing crawl tests**

`afenda/addons/afenda_brand/tests/test_identity.py`:

```python
import re

from odoo.tests import HttpCase, tagged

TELLS = re.compile(r"\bOdoo\b|odoo\.com|OdooBot|/odoo/|Odoo S\.A\.")


@tagged("post_install", "-at_install")
class TestIdentity(HttpCase):
    """No Odoo identity on any surface a user or their email client sees."""

    def assertClean(self, text, where):
        found = sorted(set(TELLS.findall(text)))
        self.assertFalse(found, f"{where} still shows {found}")

    def test_public_pages(self):
        for url in ("/web/login", "/web/database/manager", "/web/manifest.webmanifest"):
            self.assertClean(self.url_open(url).text, url)

    def test_app_prefix_serves_webclient_and_old_prefix_is_gone(self):
        self.authenticate("admin", "admin")
        page = self.url_open("/app")
        self.assertEqual(page.status_code, 200)
        self.assertIn("<title>AFENDA xForge</title>", page.text.replace("\n", ""))
        self.assertClean(page.text, "/app")
        self.assertEqual(self.url_open("/odoo", allow_redirects=False).status_code, 404)

    def test_notification_email_body(self):
        partner = self.env["res.partner"].create({"name": "Crawl Recipient", "email": "crawl@example.com"})
        record = self.env["res.partner"].create({"name": "Crawl Record"})
        record.message_post(
            body="identity check",
            partner_ids=partner.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        mail = self.env["mail.mail"].search([("recipient_ids", "in", partner.ids)], order="id desc", limit=1)
        self.assertTrue(mail, "no outgoing mail was queued")
        self.assertClean(mail.body_html, "notification email")

    def test_report_html(self):
        report = self.env.ref("web.action_report_externalpreview")
        html, _ = self.env["ir.actions.report"]._render_qweb_html(report, self.env.company.ids)
        self.assertClean(html.decode(), "external layout preview report")

    def test_translations_for_a_loaded_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"].search([("name", "=", "base")])._update_translations("fr_FR")
        terms = self.env["ir.translation"] if "ir.translation" in self.env else None
        # Odoo 16+ stores translations on the fields themselves; check a known string.
        menu = self.env.ref("base.menu_administration").with_context(lang="fr_FR")
        self.assertClean(menu.name, "fr_FR menu name")
```

Register it in `afenda/addons/afenda_brand/tests/__init__.py`:

```python
from . import test_branding
from . import test_identity
```

- [ ] **Step 3: Run to verify they fail or pass for the right reasons**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda2 -u afenda_brand --test-enable --test-tags "/afenda_brand" --stop-after-init --http-port 8179 --log-level=test --logfile=/tmp/odoo-identity.log
grep -E "FAIL:|ERROR:|failed, [0-9]+ error" /tmp/odoo-identity.log
```

Expected on first run: `test_translations_for_a_loaded_language` may error on the `ir.translation` line (that model no longer exists in 19). Remove those two lines (`terms = ...` and the comment) so the test reads the menu name only, then re-run. Any `assertClean` failure lists the exact leftover strings; those are real leaks. Fix each by one of: a rule tweak in `rules.py` (if it is a pattern the rules should have caught), or a `noqa`-free targeted edit committed separately, then re-run the rebrand and the tests.

- [ ] **Step 4: All green**

Expected: `0 failed, 0 error(s) of 12 tests` (7 branding + 5 identity).

- [ ] **Step 5: Commit**

```bash
git add afenda/tools/scan_identity.py afenda/addons/afenda_brand/tests
git commit -m "[ADD] afenda: identity scanner and crawl tests for served surfaces

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Browser verification and hand-off

**Files:**
- Modify: `afenda/README.md` (tools section)

- [ ] **Step 1: Document the tools**

Append to `afenda/README.md`:

```markdown
## De-identification tools

```bash
.venv/Scripts/python -m afenda.tools.rebrand           # dry run, per-rule counts
.venv/Scripts/python -m afenda.tools.rebrand --apply   # rewrite addons/ and odoo/
.venv/Scripts/python -m afenda.tools.brand_images      # AFENDA images over Odoo's logo paths
.venv/Scripts/python -m afenda.tools.scan_identity     # exit 1 if any Odoo identity remains
.venv/Scripts/python -m unittest discover -s afenda/tools/tests -t . -v
```

Rules live in `afenda/tools/rules.py`; names and domain in
`afenda/addons/afenda_brand/brand.py`. A line ending in `# noqa: rebrand`
is never rewritten.
```

- [ ] **Step 2: Start the server on the rebranded database and look**

Point `afenda/odoo.conf` at nothing new; start with `-d afenda2` via the `odoo-afenda` launch profile (edit the `-d` argument in `.claude/launch.json` to `afenda2` first). In the browser: `/web/login`, `/app`, Settings, Discuss, and the browser tab title. Screenshot each. Every screen must show AFENDA only; the address bar must read `/app/...`.

- [ ] **Step 3: Commit and finish**

```bash
git add afenda/README.md .claude/launch.json
git commit -m "[IMP] afenda: document de-identification tools

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Then use the finishing-a-development-branch skill: tests green means the Task 6 suite plus the tool unit tests.

---

## Self-review

- Spec coverage: screens and error pages (rules `product`, `company_name`; Task 5 spot-check of `odoo/http.py`), translations (`.po` awareness, `test_translations_for_a_loaded_language`), emails and PDFs (`test_notification_email_body`, `test_report_html`), links (`docs_link`, `odoo_com`), URL prefix (`url_prefix`, `router_prefix`, `test_app_prefix_...`), images (Task 4), branches and update flow (Task 1), idempotency (tests in Tasks 2 and 3, scanner in Task 6), protected contexts (Task 2 tests). Phase 2 and phase 3 are deliberately separate plans.
- Placeholders: none; every step has its code or exact command.
- Type consistency: `Rule(name, pattern, replacement, suffixes, path_contains, path_excludes)` is used identically in Tasks 2, 3; `rewrite_text(text, rules, path)` and `run(root, rules, apply)` match between engine, rules tests, and scanner; `TARGETS`/`render_all(root)` match between renderer and its test.
