# AFENDA xForge layer

Everything AFENDA-specific lives in this folder. The `addons/` and `odoo/`
folders at the repository root are unmodified upstream Odoo 19.0, so upstream
updates merge cleanly.

```
afenda/
  addons/afenda_brand/   the AFENDA identity: logo, colors, fonts, titles, login, settings
  oca/server-brand/      OCA debranding modules (git submodule, branch 19.0)
  oca/web/               OCA web modules: favicon, PWA, no bubbles (git submodule, branch 19.0)
  odoo.conf              local development configuration
```

## First run

```bash
git submodule update --init --depth 1
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -i afenda_brand --stop-after-init --without-demo=all
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda
```

Then open http://localhost:8169. `odoo.conf` expects PostgreSQL on
127.0.0.1:5444 with a superuser named `odoo` and no password; change
`db_port`, `db_user` and `db_password` to match your server.

## What `afenda_brand` changes

Installing `afenda_brand` pulls in the OCA modules and applies the identity:

| Where a user sees it | What changes |
|---|---|
| Browser tab | "AFENDA xForge" instead of "Odoo", favicon replaced |
| Login page | AFENDA logo, no "Powered by Odoo" link |
| Web client | Ledger Blue primary color, Source Sans 3 and Source Code Pro, paper background, tabular figures on money |
| Settings | "AFENDA xForge 19.0" edition block, Enterprise upsells removed (`remove_odoo_enterprise`), odoo.com links removed (`disable_odoo_online`) |
| Emails | "Powered by Odoo" footer removed (`mail_debranding`), AFENDA email colors |
| Portal | Odoo branding removed (`portal_debranding`) |
| PWA / mobile | App name "AFENDA", theme color Ledger Blue (`web_pwa_customize`) |
| Companies | Default logo is the AFENDA lockup; a company still named "My Company" is renamed "AFENDA" at install |

If you also install the `website` app, add `website_debranding` from
`oca/server-brand` to remove the website footer branding.

Brand values (colors, names) are defined once in `addons/afenda_brand/brand.py`
and mirrored in `static/src/scss/primary_variables.scss`.

## Branches and upstream updates

- `upstream-19.0`: pristine odoo/odoo. Never edit.
- `19.0`: `upstream-19.0` + the `[REBRAND]` commit + the `afenda/` layer. This deploys.

To take an Odoo update:

````bash
git fetch upstream 19.0
git checkout upstream-19.0 && git merge --ff-only upstream/19.0 && git push
git checkout 19.0 && git merge upstream-19.0        # resolve conflicts if any
.venv/Scripts/python -m afenda.tools.rebrand --apply # re-brands only what is new
.venv/Scripts/python -m afenda.tools.scan_identity   # must print 0 remaining
git commit -am "[REBRAND] re-apply after upstream merge"
````

Note: `upstream/19.0` history is unrelated to our rewritten root, so the
first merge needs `--allow-unrelated-histories`; see the spec for why the
root was rewritten.

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

Rule changes are reviewed on the corpus, never on the tree:
`python -m afenda.tools.corpus diff` shows exactly what a rule change alters;
after review, `python -m afenda.tools.corpus golden` and commit both files.
