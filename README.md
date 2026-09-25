# AFENDA xForge

*The truth of your business, kept.*

AFENDA xForge is a business management platform — accounting, inventory, sales, purchasing,
projects, HR — built on Odoo 19.0 Community. This repository is the whole platform: the
upstream framework and addons, the AFENDA identity layer, and the tooling that produces it.

**This is a fork, not an addons overlay.** The identity transform rewrites text and images
across `odoo/` and `addons/`, so the deployable artifact is the entire tree — the official
Odoo container image and distribution packages cannot be used as-is. See
[the platform architecture spec](docs/superpowers/specs/2026-09-23-afenda-platform-architecture.md)
for what that costs and the plan to make it cheap.

## Layout

```
odoo/            upstream framework, carrying the identity transform
addons/          upstream addons, carrying the identity transform
afenda/          everything AFENDA-specific — see afenda/README.md
  addons/        afenda_brand, afenda_api_docs, afenda_brand_digest
  oca/           vendored OCA modules (two git submodules, branch 19.0)
  tools/         the rebrand engine, icon generators, identity scanner
  odoo.conf      local development configuration
docs/            plans and specs
.agents/         version-locked Odoo 19.0 developer documentation (untracked)
```

`afenda/tools/` is the part worth understanding first: brand text and images are *generated*,
never hand-edited into the tree. A rule change is reviewed with
`python -m afenda.tools.corpus diff`, which shows every distinct rewrite before anything is
applied.

## Requirements

| | |
|---|---|
| Python | 3.10 – 3.14 (`odoo/release.py`). Development runs 3.11 |
| PostgreSQL | 13 or above (`odoo/release.py` `MIN_PG_VERSION`) |
| `wkhtmltopdf` | 0.12.6 for PDF reports. Not pip-installable; install it separately |

## Quick start

```bash
git submodule update --init --depth 1
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt          # POSIX: .venv/bin/python
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda \
    -i afenda_brand,afenda_api_docs --stop-after-init --without-demo=all
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda
```

Then open <http://localhost:8169>.

`afenda/odoo.conf` is a **development** configuration and must not be deployed: it binds to
loopback, disables cron, and leaves the database manager listed. It expects PostgreSQL on
`127.0.0.1:5444` with a role named `odoo`; adjust `db_host`, `db_port`, `db_user` and
`db_password` to match your server.

The rebrand tooling has its own pinned dependencies. On Python 3.11 they happen to agree
with the runtime set (both pin `Pillow==9.4.0`); on 3.12 and above they **conflict** — the
runtime wants `Pillow==10.2.0` and the icon generators are pinned to 9.4.0 because a Pillow
bump re-renders every icon in the tree. Install `afenda/tools/requirements.txt` into a
separate virtual environment so the version you build icons with never depends on which
Python you happen to be running.

## Tests

```bash
# rebrand tooling — fast, no database
.venv/Scripts/python -m unittest discover afenda/tools/tests

# the AFENDA modules
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
    -c afenda/odoo.conf -d afenda \
    -u afenda_brand,afenda_api_docs,afenda_brand_digest --test-enable \
    --test-tags "/afenda_brand,/afenda_api_docs,/afenda_brand_digest" \
    --stop-after-init --http-port 8179

# identity regression gate — must hold at its baseline
.venv/Scripts/python -m afenda.tools.scan_identity
```

**Read the printed test count, never the exit code.** `afenda/odoo.conf` sets
`log_level = warn`, which silences the INFO line reporting the result, so a *passing* suite
would print nothing at all and `exit = 0` cannot be told apart from "no tests were
collected". The config sets `log_handler = odoo.tests:INFO` to restore the count — if you
ever see a silent green run, that is the line to check.

The identity scanner holds at a **deliberately non-zero baseline**. That number is the
accepted remainder — protected strings such as translator attribution and registered API
identifiers, plus known outstanding work. A drop is as actionable as a rise: lower the
baseline in the same commit, or the gate goes slack.

## Branches

One branch: **`main`** — the product, what production runs (the identity transform, the
AFENDA modules, the tooling). CI runs on it and `deploy/redeploy.sh` defaults to it.

Upstream Odoo is reached through the `upstream` remote (`odoo/odoo`, branch `19.0`), not a
branch of this repository. Every retired line of work is kept as a tag under `archive/`
(since 2026-09-25): the old `19.0` (which never carried the identity transform),
`upstream-19.0` (the pristine snapshot the fork was anchored on), `afenda/brand-identity`,
a cloud session's unmerged API hardening (`archive/cloud-api-hardening`) and the unfinished
industry preset packs (`archive/industry-packs-wip`). `git fetch origin 'refs/tags/archive/*:refs/tags/archive/*'`
brings them back; a branch is `git switch -c <name> archive/<tag>` away.

Commit subjects use Odoo's tags: `[ADD]`, `[FIX]`, `[IMP]`, `[REBRAND]`. Stage explicit
paths — the rebrand can leave tens of thousands of modified files, so `git add -A` is never
correct here. Several people may share one checkout; commit with
`git commit --only -F msgfile -- <paths>`.

## Documentation

- [`afenda/README.md`](afenda/README.md) — the AFENDA layer: what `afenda_brand` changes, the
  rebrand workflow, the upstream merge procedure
- [`CLAUDE.md`](CLAUDE.md) — development environment, commands, and the traps that have
  already cost this project time
- [`docs/`](docs/) — plans and specs, including the platform architecture
- `/docs` on a running server — the generated API reference, from `afenda_api_docs`

## Security

**No disclosure process is established yet.** Do not report vulnerabilities to Odoo — this
is a modified distribution and Odoo cannot act on issues in it. A contact address and
disclosure policy must be set before any public or customer-facing deployment; until then,
raise issues privately with the repository owner.

## License

Odoo Community is LGPLv3; the AFENDA modules under `afenda/addons/` declare their own
licenses in their manifests. See [`LICENSE`](LICENSE) and [`COPYRIGHT`](COPYRIGHT).
