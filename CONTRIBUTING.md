Contributing to AFENDA xForge
============================

This is not the Odoo repository. Pull requests against upstream Odoo belong at
[odoo/odoo](https://github.com/odoo/odoo); this repo is a modified distribution, and changes
here follow its own rules.

Read [`CLAUDE.md`](CLAUDE.md) before your first change — it holds the environment, the
commands, and the traps that have already cost this project time.

TL;DR
-----

* **Never hand-edit `odoo/` or `addons/`.** Brand text and images there are *generated*.
  Change `afenda/tools/rules.py` instead, review it with
  `python -m afenda.tools.corpus diff`, regenerate the golden file, then apply once.
  Reviewing a rule change by applying it to the tree and reading the result is how this
  branch lost days.
* **Everything else goes in `afenda/addons/<module>/`** as an inheriting module.
* **Stage explicit paths.** Never `git add -A` or `git commit -am` — after a rebrand run the
  tree holds tens of thousands of modified files, and several people may share one checkout.
  Use `git commit --only -F msgfile -- <paths>`.
* **Commit subjects use Odoo's tags**: `[ADD]`, `[FIX]`, `[IMP]`, `[REBRAND]`. Keep
  generated output under `[REBRAND]` so an auditor can separate it from hand-written code by
  subject line.
* **New behaviour needs a test**, in `afenda/addons/<module>/tests/`, subclassing Odoo's
  `TransactionCase` or `HttpCase`. A class that does not descend from `BaseCase` is
  discovered and then silently dropped — there is a guard test for exactly this.
* **Read the printed test count, never the exit code.** `afenda/odoo.conf` sets
  `log_level = warn`, so a *passing* suite would print nothing and `exit = 0` cannot be told
  apart from "no tests were collected".

Before you open a pull request
------------------------------

```bash
# rebrand tooling — fast, no database
.venv/Scripts/python -m unittest discover afenda/tools/tests

# the AFENDA modules
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
    -c afenda/odoo.conf -d afenda \
    -u afenda_brand,afenda_api_docs,afenda_brand_digest --test-enable \
    --test-tags "/afenda_brand,/afenda_api_docs,/afenda_brand_digest" \
    --stop-after-init --http-port 8179

# identity regression gate
.venv/Scripts/python -m afenda.tools.scan_identity
```

The identity scanner holds at a deliberately non-zero baseline. A **rise** needs triage; a
**drop** needs the baseline lowered in the same commit, or the gate quietly goes slack.

Changing `hooks.py`
-------------------

`post_init_hook` runs at **install only**. If you change what it does, existing databases
will never see it. Bump `version` in the module's `__manifest__.py` and add a
`migrations/<new version>/post-migrate.py` that re-invokes the affected helper, in the same
commit. The existing migrations under `afenda_brand/` document why, including one case where
skipping the migration leaves a company's logo permanently unrepairable.

Security issues
---------------

Do not open a public issue or a pull request for a vulnerability. See
[`SECURITY.md`](SECURITY.md).
