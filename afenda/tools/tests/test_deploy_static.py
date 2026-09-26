"""Static checks on the deploy files: no vendor host, pinned build inputs,
a build context that carries every module, the nexuscanon.com landing page
(same-origin files only, no absolute URL, the generated lockup), redeploy upgrades, and
the DNS zone (no wildcard, Zoho mail kept, app mail through Resend).

The image is the product, so it must not reach a vendor host at build or run
time (R7 of the G0 deploy plan proves that at runtime; this proves it in the
text), must not pull a moving `nightly.` artifact, and must not lose a module
to a `.dockerignore` pattern. Needs no database and no Docker, so it lives in
`afenda/tools/tests/` and runs in the fast
`python -m unittest discover afenda/tools/tests` suite.
"""
import os
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "deploy"
DOCKERFILE = DEPLOY / "Dockerfile"
DOCKERIGNORE = REPO / ".dockerignore"
SITE = DEPLOY / "site"

# Committed binary files under deploy/: exempt from the LF and URL text checks.
BINARY_SUFFIXES = (".woff2",)
SVG_NAMESPACE = re.compile(r'\sxmlns(?::\w+)?="http://www\.w3\.org/[^"]*"')

VENDOR_HOSTS = ("odoo.com", "odoocdn")


def _dockerignore_patterns():
    """The exclusion patterns, in order, as (negated, regex) pairs.

    Docker anchors every pattern at the context root (a leading `/` changes
    nothing), `**` spans any number of path segments, `*` and `?` stay inside
    one segment, and a path is excluded when it or any parent directory
    matches. Later `!` lines re-include.
    """
    patterns = []
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        line = line.lstrip("!").strip().lstrip("/").rstrip("/")
        regex, i = "", 0
        while i < len(line):
            if line.startswith("**/", i):
                regex, i = regex + "(?:.*/)?", i + 3
            elif line.startswith("**", i):
                regex, i = regex + ".*", i + 2
            elif line[i] == "*":
                regex, i = regex + "[^/]*", i + 1
            elif line[i] == "?":
                regex, i = regex + "[^/]", i + 1
            else:
                regex, i = regex + re.escape(line[i]), i + 1
        patterns.append((negated, re.compile(regex + r"\Z")))
    return patterns


def _excluded(rel_path, patterns):
    parts = rel_path.split("/")
    candidates = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    excluded = False
    for negated, regex in patterns:
        if any(regex.match(c) for c in candidates):
            excluded = not negated
    return excluded


class DeployStaticTests(unittest.TestCase):
    def test_no_vendor_host_in_deploy_files(self):
        files = [p for p in DEPLOY.rglob("*") if p.is_file()]
        files += [p for p in REPO.glob("*Dockerfile*") if p.is_file()]
        files.append(DOCKERIGNORE)
        self.assertIn(DOCKERFILE, files)
        self.assertIn(DEPLOY / "compose.yaml", files)
        offenders = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            offenders += [f"{path.relative_to(REPO)}: {host}" for host in VENDOR_HOSTS if host in text]
        self.assertEqual(offenders, [], "a deploy file names a vendor host")

    def test_dockerfile_pulls_no_nightly_build(self):
        self.assertNotIn("nightly.", DOCKERFILE.read_text(encoding="utf-8"))

    def test_dockerfile_checks_wkhtmltox_against_pinned_hashes(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        for arch in ("AMD64", "ARM64"):
            self.assertRegex(text, rf"WKHTMLTOX_SHA256_{arch}=[0-9a-f]{{64}}\n")
        self.assertIn("sha256sum -c", text)

    def test_compose_project_name_cannot_collide(self):
        # Plain `afenda` collides with an unrelated Compose project on the
        # developer machine; `down --remove-orphans` or `down -v` would reach it.
        names = re.findall(r"^name:\s*(\S+)\s*$",
                           (DEPLOY / "compose.yaml").read_text(encoding="utf-8"), re.MULTILINE)
        self.assertEqual(names, ["afenda-deploy"])

    def test_backup_output_is_private(self):
        # Root cron runs with umask 022; the dump holds password hashes, TOTP
        # secrets and database.secret, so backup.sh must tighten it itself,
        # before it creates any output.
        text = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
        umask = re.search(r"^umask 077$", text, re.MULTILINE)
        self.assertIsNotNone(umask, "backup.sh does not set umask 077")
        self.assertLess(umask.start(), text.index("mkdir -p"), "umask 077 must come before the first mkdir")

    def test_backup_prunes_only_after_verifying_the_new_backup(self):
        text = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
        prune = text.find("./prune-backups.sh")
        self.assertNotEqual(prune, -1, "backup.sh never prunes old backups")
        self.assertLess(text.index("tar -tzf"), prune, "pruning must follow the archive check")
        self.assertLess(text.index("pg_restore -l"), prune, "pruning must follow the dump check")

    def test_init_script_directory_is_traversable(self):
        # `COPY --chmod=644` into a directory that does not exist yet creates
        # the directory with 644 as well; the non-root afenda user then cannot
        # open init_params.py. The Dockerfile must create it 755 first.
        text = DOCKERFILE.read_text(encoding="utf-8")
        mkdir = re.search(r"install -d -m 755 /usr/local/lib/afenda\b", text)
        copy = re.search(r"^COPY\b.*\s/usr/local/lib/afenda/", text, re.MULTILINE)
        self.assertIsNotNone(mkdir, "Dockerfile never creates /usr/local/lib/afenda with mode 755")
        self.assertIsNotNone(copy, "Dockerfile no longer copies into /usr/local/lib/afenda")
        self.assertLess(mkdir.start(), copy.start(), "the 755 directory must exist before the COPY into it")

    def test_dockerignore_keeps_every_module_file(self):
        patterns = _dockerignore_patterns()
        addons = REPO / "afenda" / "addons"
        lost = []
        for dirpath, dirnames, filenames in os.walk(addons):
            # Bytecode caches are the one thing meant to go.
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in dirnames + filenames:
                rel = (Path(dirpath) / name).relative_to(REPO).as_posix()
                if _excluded(rel, patterns):
                    lost.append(rel)
        self.assertTrue(any(addons.iterdir()), "afenda/addons is empty; nothing was checked")
        self.assertEqual(lost, [], ".dockerignore drops files under afenda/addons")

    def test_dockerignore_excludes_what_it_must(self):
        patterns = _dockerignore_patterns()
        for rel in (".git/config", ".venv/pyvenv.cfg", ".agents/x", "docs/x.md",
                    "deploy/secrets/db_password",
                    "afenda/addons/afenda_brand/__pycache__/brand.cpython-311.pyc"):
            self.assertTrue(_excluded(rel, patterns), f"{rel} would enter the build context")
        # Root docs only: a module's own docs/ folder ships with the module.
        self.assertFalse(_excluded("afenda/addons/afenda_api_docs/docs/x.md", patterns))

    def test_deploy_text_files_use_lf(self):
        self.assertIn("deploy/** text eol=lf", (REPO / ".gitattributes").read_text(encoding="utf-8"))
        crlf = [
            str(p.relative_to(REPO))
            for p in DEPLOY.rglob("*")
            if p.is_file() and p.parent.name != "secrets" and p.suffix not in BINARY_SUFFIXES
            and b"\r\n" in p.read_bytes()
        ]
        self.assertEqual(crlf, [], "CRLF in a file that runs inside a Linux container")

    def test_binary_site_files_escape_the_lf_rule(self):
        # `deploy/** text eol=lf` would rewrite any CR LF byte pair inside a
        # compressed font on commit; the fonts must be declared binary after it.
        lines = [l.strip() for l in (REPO / ".gitattributes").read_text(encoding="utf-8").splitlines()]
        self.assertIn("deploy/**/*.woff2 binary", lines)
        self.assertGreater(lines.index("deploy/**/*.woff2 binary"), lines.index("deploy/** text eol=lf"))

    def test_every_base_image_is_pinned_by_digest(self):
        # A tag can move under us; a digest cannot. The tag stays for humans.
        pinned = re.compile(r"^[a-z0-9./-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")
        compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
        refs = re.findall(r"^\s+image:\s*(\S+)\s*$", compose, re.MULTILINE)
        refs = [r for r in refs if not r.startswith("${XFORGE_IMAGE")]
        self.assertEqual(len(refs), 2, refs)  # postgres and nginx
        arg = re.search(r"^ARG PYTHON_IMAGE=(\S+)$", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
        self.assertIsNotNone(arg)
        for ref in refs + [arg.group(1)]:
            self.assertRegex(ref, pinned)

    def test_ci_postgres_matches_the_pinned_compose_image(self):
        compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
        pinned = re.search(r"^\s+image:\s*(postgres:\S+)\s*$", compose, re.MULTILINE).group(1)
        workflow = (REPO / ".github" / "workflows" / "afenda-image.yml").read_text(encoding="utf-8")
        used = re.findall(r"^\s+image:\s*(postgres:\S+)\s*$", workflow, re.MULTILINE)
        self.assertEqual(used, [pinned])

    def test_ci_regenerates_the_api_asset_and_gates_changes(self):
        image = (REPO / ".github" / "workflows" / "afenda-image.yml").read_text(encoding="utf-8")
        step = re.search(r"^ {6}- name: API asset is current\n((?: {8}.*\n|\n)+)", image, re.MULTILINE)
        self.assertIsNotNone(step, 'no "API asset is current" step in afenda-image.yml')
        body = step.group(1)
        self.assertIn("timeout-minutes:", body, "the asset step has no timeout-minutes")
        # `-i` is mandatory: without it stdin is empty and the export is a
        # silent no-op (see the Task 6 brief).
        self.assertRegex(body, r"docker run -i --rm --network host[\s\S]*?< afenda/tools/export_openapi_shell\.py")
        self.assertIn("afenda-openapi: wrote", body)
        # The committed count must come from git, not from `ls` on the same
        # directory the export just wrote into (that would just measure the
        # exporter's own output and always agree with it).
        self.assertIn("git ls-files -- 'afenda/addons/afenda_api_docs/openapi/*.json' | wc -l", body)
        self.assertNotIn("ls afenda/addons/afenda_api_docs/openapi/*.json | wc -l", body)
        # And it must be read before the export mutates the directory.
        git_count_at = body.index("git ls-files -- 'afenda/addons/afenda_api_docs/openapi/*.json'")
        export_at = body.index("docker run -i")
        self.assertLess(git_count_at, export_at,
                         "the committed count must be read before the export runs")
        # The printed N is actually compared against that committed count,
        # and must be greater than zero.
        self.assertIn('[ "$n" -gt 0 ]', body)
        self.assertIn('[ "$n" -eq "$committed" ]', body)
        self.assertIn("git status --porcelain -- afenda/addons/afenda_api_docs/openapi", body)

        ci = (REPO / ".github" / "workflows" / "afenda-ci.yml").read_text(encoding="utf-8")
        # A shallow checkout has no history to diff against; api_diff needs a
        # local base ref, so main is fetched at depth 1 before the check.
        self.assertIn("git fetch --no-tags --depth=1 origin main:refs/remotes/origin/main", ci)
        self.assertIn("python -m afenda.tools.api_diff check --base-ref origin/main", ci)
        # GitHub's default `run:` shell is `bash -eo pipefail {0}`: a bare
        # `status=$?` after the piped check never runs on failure, because
        # errexit terminates the shell at the failing pipeline itself, before
        # the closing ```-fence is ever written. The pipeline must be
        # guarded by `|| status=$?` on the same line, so the fence always
        # closes.
        self.assertRegex(
            ci,
            r"python -m afenda\.tools\.api_diff check --base-ref origin/main[^\n]*\|\| status=\$\?",
        )

    def test_ci_odoo_bin_calls_all_pass_the_afenda_addons_path(self):
        # afenda/odoo.conf supplies addons_path locally, but every `odoo-bin`
        # invocation in CI runs inside a container with no config file, so
        # each one must pass --addons-path itself. CI run 36216051763 (at
        # 5c71e380d) shipped the exporter's shell call without it: the
        # database it opened had no afenda_api_docs on its addons path,
        # "not installable, skipped", and
        # afenda/tools/export_openapi_shell.py raised ModuleNotFoundError.
        image = (REPO / ".github" / "workflows" / "afenda-image.yml").read_text(encoding="utf-8")
        addons_path = (
            "/opt/afenda/addons,/opt/afenda/afenda/addons,"
            "/opt/afenda/afenda/oca/server-brand,/opt/afenda/afenda/oca/web"
        )
        # Join backslash-continued physical lines into logical shell
        # commands, the way bash itself does before running them, so a
        # `--addons-path` on its own continuation line still counts.
        logical_lines = []
        buf = ""
        for raw in image.splitlines():
            line = f"{buf} {raw.strip()}" if buf else raw
            if line.rstrip().endswith("\\"):
                buf = line.rstrip()[:-1].rstrip()
            else:
                logical_lines.append(line)
                buf = ""
        if buf:
            logical_lines.append(buf)

        odoo_bin_commands = [line for line in logical_lines if "/opt/afenda/odoo-bin" in line]
        self.assertGreaterEqual(
            len(odoo_bin_commands), 4,
            f"expected at least 4 odoo-bin invocations in afenda-image.yml, found {len(odoo_bin_commands)}",
        )
        for command in odoo_bin_commands:
            self.assertIn(
                f"--addons-path {addons_path}",
                command,
                f"odoo-bin call is missing --addons-path {addons_path!r}: {command!r}",
            )

    def test_ci_image_build_always_reports_docker_build_as_a_status(self):
        # afenda-image.yml used to filter push/pull_request by `paths:` at the
        # workflow `on:` level: on a PR whose diff touched none of those
        # globs, the `build` job never ran at all, so `docker build` could
        # never report a status and could not be a required check (PR #7
        # review, Codex). The filter must live in a `changes` job instead,
        # whose `if:` skips `build` when nothing matches - GitHub reports a
        # job skipped by `if:` as success for required status checks, so
        # `docker build` always reports (green on a skip, red on a real
        # failure).
        image = (REPO / ".github" / "workflows" / "afenda-image.yml").read_text(encoding="utf-8")

        on_block = re.search(r"^on:\n((?:.*\n)+?)^permissions:", image, re.MULTILINE).group(1)
        self.assertNotIn("paths:", on_block, "on: still filters push/pull_request by paths")
        self.assertIn("branches: [main]", on_block)
        self.assertIn("workflow_dispatch:", on_block)

        changes_job = re.search(r"^  changes:\n((?:.*\n)+?)^  build:\n", image, re.MULTILINE)
        self.assertIsNotNone(changes_job, "no changes job before build")
        changes_body = changes_job.group(1)
        self.assertIn("name: image inputs", changes_body)
        self.assertIn("image: ${{ steps.filter.outputs.image }}", changes_body)
        for pattern in ("deploy/**", "afenda/**", "odoo/**", "addons/**", "odoo-bin",
                        "requirements.txt", ".dockerignore",
                        ".github/workflows/afenda-image.yml"):
            self.assertIn(pattern, changes_body, f"changes job filter is missing {pattern!r}")

        build_job = re.search(r"^  build:\n((?:.*\n)+)", image, re.MULTILINE).group(1)
        self.assertIn("needs: changes", build_job)
        self.assertIn("if: needs.changes.outputs.image == 'true'", build_job)

        # No `run:` script inside the changes job may inline a `${{ }}`
        # expression; only `env:` may carry one (same rule as afenda-pr.yml,
        # test_afenda_pr_workflow_passes_the_body_through_env_not_expression).
        lines = changes_body.splitlines()
        offenders = []
        i = 0
        while i < len(lines):
            match = re.match(r"^(\s*)run:\s*(.*)$", lines[i])
            if match:
                indent, inline = len(match.group(1)), match.group(2).strip()
                if inline and inline not in ("|", ">", "|-", ">-"):
                    if "${{" in inline:
                        offenders.append(lines[i])
                    i += 1
                    continue
                i += 1
                while i < len(lines) and (lines[i].strip() == "" or len(lines[i]) - len(lines[i].lstrip()) > indent):
                    if "${{" in lines[i]:
                        offenders.append(lines[i])
                    i += 1
                continue
            i += 1
        self.assertEqual(offenders, [], f"a run: script in the changes job interpolates an expression: {offenders}")

    def test_afenda_pr_workflow_passes_the_body_through_env_not_expression(self):
        # afenda-pr.yml's `pr evidence` job must trigger when a PR description
        # is edited (the check re-runs against the new body, not just the
        # first one), and the body must reach the script through `env:` --
        # never interpolated into a `run:` script, where a crafted PR
        # description could inject shell syntax (docs/superpowers/specs/
        # 2026-09-26-pr-stewardship.md, decision 3).
        workflow = (REPO / ".github" / "workflows" / "afenda-pr.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"types:\s*\[[^\]]*\bedited\b[^\]]*\]")
        self.assertIn("PR_BODY: ${{ github.event.pull_request.body }}", workflow)

        # No `run:` step's script may contain a `${{ }}` expression, whether
        # inline or in a block scalar (`run: |`); only `env:` may carry one.
        lines = workflow.splitlines()
        offenders = []
        i = 0
        while i < len(lines):
            match = re.match(r"^(\s*)run:\s*(.*)$", lines[i])
            if match:
                indent, inline = len(match.group(1)), match.group(2).strip()
                if inline and inline not in ("|", ">", "|-", ">-"):
                    if "${{" in inline:
                        offenders.append(lines[i])
                    i += 1
                    continue
                i += 1
                while i < len(lines) and (lines[i].strip() == "" or len(lines[i]) - len(lines[i].lstrip()) > indent):
                    if "${{" in lines[i]:
                        offenders.append(lines[i])
                    i += 1
                continue
            i += 1
        self.assertEqual(offenders, [], f"a run: script interpolates an expression: {offenders}")

    def test_app_connects_as_the_least_privilege_role(self):
        compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
        env = re.search(r"^x-xforge-env: &xforge-env\n((?:  .*\n)+)", compose, re.MULTILINE).group(1)
        self.assertIn("PGUSER: afenda_app", env)
        self.assertIn("PGPASSWORD_FILE: /run/secrets/db_app_password", env)
        self.assertIn("./db-init:/docker-entrypoint-initdb.d:ro", compose)
        self.assertRegex(compose, r"db_app_password:\n\s+file: \./secrets/db_app_password")
        # The superuser stays the db container's bootstrap role only.
        self.assertIn("POSTGRES_USER: xforge", compose)

    def test_restore_recreates_objects_as_the_app_role(self):
        text = (DEPLOY / "restore.sh").read_text(encoding="utf-8")
        self.assertIn("createdb -U xforge -O afenda_app afenda", text)
        self.assertIn("--role=afenda_app", text)

    def test_restore_reruns_init_before_restarting_xforge(self):
        # Restarting xforge by container id (not `compose start`) no longer
        # brings init along, so a restore from another host's backup would
        # otherwise keep that host's web.base.url and outdated modules.
        # restore.sh must run init itself, after the data lands and before
        # the script ends (the trap restarts xforge on EXIT).
        text = (DEPLOY / "restore.sh").read_text(encoding="utf-8")
        rerun = text.find("docker compose run --rm -T init")
        self.assertNotEqual(rerun, -1, "restore.sh never reruns init")
        self.assertLess(text.index("pg_restore -U xforge -d afenda"), rerun,
                         "init must rerun after the database is restored")
        self.assertLess(text.index("tar -C /var/lib/afenda/filestore -xzf -"), rerun,
                         "init must rerun after the filestore is restored")
        self.assertLess(rerun, text.rindex("restore: done"),
                         "init must rerun before the script ends")

    def test_restore_refuses_before_dropping_if_the_app_role_is_missing(self):
        # dropdb must never run before we know afenda_app exists: createdb
        # -O afenda_app would fail after afenda is already gone, leaving the
        # last-resort rollback in a destructive state.
        text = (DEPLOY / "restore.sh").read_text(encoding="utf-8")
        role_check = re.search(r"SELECT 1 FROM pg_roles WHERE rolname = 'afenda_app'", text)
        self.assertIsNotNone(role_check, "restore.sh never checks pg_roles for afenda_app")
        self.assertLess(role_check.start(), text.index("docker compose stop xforge"),
                         "the role check must come before xforge is stopped")
        self.assertLess(role_check.start(), text.index("dropdb"),
                         "the role check must come before dropdb")

    def test_scripts_restart_only_the_app_container(self):
        # `docker compose start xforge` also starts xforge's depends_on
        # (init, service_completed_successfully): the stale one-shot init
        # container, whose environment can predate the current compose file.
        # Starting the existing container by id starts it alone.
        for name in ("backup.sh", "restore.sh", "migrate-db-role.sh"):
            with self.subTest(script=name):
                text = (DEPLOY / name).read_text(encoding="utf-8")
                self.assertNotIn("docker compose start xforge", text)
                restart = re.search(r"^restart_xforge\(\) \{\n(.*?)^\}", text, re.MULTILINE | re.DOTALL)
                self.assertIsNotNone(restart, f"{name} has no restart_xforge function")
                self.assertIn('docker start "$(docker compose ps -aq xforge)"', restart.group(1))
                self.assertIn("docker compose exec -T nginx nginx -s reload || true", restart.group(1))
                self.assertIn("trap restart_xforge EXIT", text)


class LocalFirstGatesCiTests(unittest.TestCase):
    """CI changes from docs/superpowers/specs/2026-09-26-local-first-gates.md
    decision 5 and Corrections after review items 6 and 8: a sparse checkout
    for `api_contract` (verified safe -- api_diff.py reads only git objects
    and `afenda/addons/afenda_api_docs/openapi/`, never the working tree
    under `odoo/`/root `addons/`), the `api_contract` push-branch fetch
    failing open like `afenda-image.yml`'s `changes` job already does, pip
    caching for the `tools` job, a cached Docker layer build for
    `afenda-image`, and the `afenda-pr` `edited`/`PR_COMMITS` changes.

    `tools`'s own checkout stays full (no sparse-checkout): `test_brand_images.py`
    (`test_every_listed_path_exists_and_is_actually_recoloured`,
    `brand_images.RECOLOUR`) reads 17 files spread across nine separate
    `addons/*` module directories (account, base_automation, hr_attendance,
    mass_mailing, stock, stock_picking_batch, survey, web,
    website_mass_mailing), and `test_no_svg_in_the_tree_still_carries_an_odoo_brand_colour`
    recursively scans the entirety of root `addons/` and `odoo/` for any
    `*.svg` carrying an Odoo brand colour -- a cone sparse-checkout narrow
    enough to save real time would either hard-fail the first test (a
    RECOLOUR path outside the pattern) or silently weaken the second's
    regression guarantee to whatever subset was listed. `submodules: true`
    is still dropped from that job: the only match for `afenda/oca` under
    `afenda/tools/tests` is `test_deploy_static.py`'s own string-literal
    comparison against `afenda-image.yml`'s text (see
    `test_ci_odoo_bin_calls_all_pass_the_afenda_addons_path` above), never a
    filesystem read of the submodules' checked-out content.
    """

    def _job_block(self, text, name, next_name=None):
        if next_name:
            pattern = rf"^  {re.escape(name)}:\n((?:.*\n)+?)^  {re.escape(next_name)}:\n"
        else:
            pattern = rf"^  {re.escape(name)}:\n((?:.*\n)+)"
        match = re.search(pattern, text, re.MULTILINE)
        self.assertIsNotNone(match, f"no {name!r} job found")
        return match.group(1)

    def test_tools_job_drops_unused_submodules_and_caches_pip(self):
        ci = (REPO / ".github" / "workflows" / "afenda-ci.yml").read_text(encoding="utf-8")
        tools = self._job_block(ci, "tools", "api_contract")
        self.assertNotIn("submodules: true", tools,
                         "afenda/oca is never read by afenda/tools/tests; see the class docstring")
        self.assertIn("cache: pip", tools)
        self.assertIn("cache-dependency-path: afenda/tools/requirements*.txt", tools)
        # The gate command itself is untouched (afenda.tools.check's static
        # test asserts this string equals GATES["tools"]'s own command).
        self.assertIn("python -m unittest discover afenda/tools/tests", tools)

    def test_api_contract_job_uses_a_safe_sparse_checkout(self):
        # api_diff.py reads only git objects (git show <ref>:<path>) for the
        # base side, and only afenda/addons/afenda_api_docs/openapi/*.json,
        # api_version.py and CHANGELOG.md (all under afenda/) for HEAD --
        # confirmed by reading afenda/tools/api_diff.py: no reference to
        # "odoo" or a bare "addons" path anywhere in it.
        ci = (REPO / ".github" / "workflows" / "afenda-ci.yml").read_text(encoding="utf-8")
        contract = self._job_block(ci, "api_contract", "nginx")
        self.assertIn("sparse-checkout: afenda", contract)
        api_diff_text = (REPO / "afenda" / "tools" / "api_diff.py").read_text(encoding="utf-8")
        self.assertNotRegex(api_diff_text, r"""['"]odoo['"]|['"]addons['"]""")

    def test_api_contract_push_fetch_fails_open(self):
        # Mirrors afenda-image.yml's `changes` job (git fetch ... || { echo
        # …; exit 0; }): a push whose `before` SHA is unreachable (a history
        # rewrite, GC) must degrade gracefully, not hard-fail a legitimate
        # push to main under this file's `bash -eo pipefail` default.
        ci = (REPO / ".github" / "workflows" / "afenda-ci.yml").read_text(encoding="utf-8")
        contract = self._job_block(ci, "api_contract", "nginx")
        self.assertRegex(
            contract,
            r'if ! git fetch --no-tags --depth=1 origin "\$BEFORE"; then\n\s*echo "::notice::[^\n]*failing open',
        )

    def test_image_build_uses_buildx_with_a_gha_layer_cache(self):
        # docs/superpowers/specs/2026-09-26-local-first-gates.md decision 5 /
        # Corrections after review item 6: load: true keeps every later
        # `docker run …afenda/xforge:ci…` step unchanged.
        image = (REPO / ".github" / "workflows" / "afenda-image.yml").read_text(encoding="utf-8")
        build = self._job_block(image, "build")
        self.assertNotIn("docker build -f deploy/Dockerfile -t afenda/xforge:ci .", build)
        self.assertIn("uses: docker/setup-buildx-action@v3", build)
        self.assertIn("uses: docker/build-push-action@v6", build)
        self.assertIn("context: .", build)
        self.assertIn("file: deploy/Dockerfile", build)
        self.assertIn("tags: afenda/xforge:ci", build)
        self.assertIn("load: true", build)
        self.assertIn("cache-from: type=gha,scope=afenda-image", build)
        self.assertIn("cache-to: type=gha,mode=max,scope=afenda-image", build)
        self.assertIn("BUILDKIT_PROGRESS: plain", build)

    def test_pr_evidence_job_is_never_skipped(self):
        # A skipped run counts as success for a required check, so a title-only edit
        # after a red `pr evidence` would turn it green (code review of 2e781020f).
        # The job runs on every event it is triggered by; a duplicate run costs ~10 s.
        pr = (REPO / ".github" / "workflows" / "afenda-pr.yml").read_text(encoding="utf-8")
        job = self._job_block(pr, "pr_evidence")
        self.assertNotRegex(job, r"(?m)^    if:")
        self.assertIn("pull-requests: read", pr)

    def test_pr_workflow_fetches_pr_commits_from_the_api_through_env(self):
        # Corrections after review item 8: the PR's commits come from
        # `GET /repos/{repo}/pulls/{number}/commits` via gh api + GITHUB_TOKEN,
        # not a local `git rev-list` (this checkout is shallow and sparse, so
        # it has no commit graph to walk). PR_COMMITS must reach
        # pr_evidence.py only through the environment.
        pr = (REPO / ".github" / "workflows" / "afenda-pr.yml").read_text(encoding="utf-8")
        job = self._job_block(pr, "pr_evidence")
        self.assertIn("gh api", job)
        self.assertRegex(job, r"pulls/\$PR_NUMBER/commits")
        self.assertIn('echo "PR_COMMITS=', job)
        self.assertIn('>> "$GITHUB_ENV"', job)
        # The no-${{-in-run: rule (same as PR_BODY) is enforced file-wide by
        # test_afenda_pr_workflow_passes_the_body_through_env_not_expression
        # below, which already re-scans this new step too.


class LandingSiteStaticTests(unittest.TestCase):
    """The nexuscanon.com landing page under deploy/site: one screen, black and
    white, styled and scripted only from same-origin files."""

    def _page(self):
        return (SITE / "index.html").read_text(encoding="utf-8")

    def test_page_has_no_script_and_no_inline_style(self):
        # No script at all (the entrance is CSS), and styles only from site.css,
        # so the CSP needs no hash and no 'unsafe-inline'.
        page = self._page()
        self.assertNotIn("<script", page.lower())
        self.assertEqual([p.name for p in SITE.glob("*.js")], [])
        self.assertNotIn("<style", page.lower())
        self.assertNotRegex(page, r"\sstyle=")
        self.assertIn('<link rel="stylesheet" href="site.css">', page)
        self.assertTrue((SITE / "site.css").is_file(), "site.css is missing")

    def test_site_names_no_absolute_url(self):
        # The only URL form is __PUBLIC_URL__/..., substituted at nginx start.
        # An SVG's xmlns is a namespace name, never fetched, so it is allowed.
        offenders = []
        for path in SITE.rglob("*"):
            if not path.is_file() or path.suffix in BINARY_SUFFIXES:
                continue
            text = SVG_NAMESPACE.sub("", path.read_text(encoding="utf-8"))
            offenders += [f"{path.relative_to(REPO)}: {m}" for m in re.findall(r"https?://\S*", text, re.I)]
            offenders += [f"{path.relative_to(REPO)}: {m}" for m in re.findall(r"""(?:href|src|srcset|url)\s*[=(]\s*["']?//""", text, re.I)]
        self.assertEqual(offenders, [], "a site file names an absolute URL")
        page = self._page()
        self.assertIn('href="__PUBLIC_URL__/request-access"', page)
        self.assertIn('href="__PUBLIC_URL__/web/login"', page)

    def test_page_texts_are_exact(self):
        page = self._page()
        h1 = re.search(r"<h1>(.*?)</h1>", page, re.S).group(1)
        self.assertEqual(" ".join(re.sub(r"<[^>]+>", " ", h1).split()), "The truth of your business, kept.")
        self.assertRegex(page, r'<a [^>]*href="__PUBLIC_URL__/request-access"[^>]*>Request access</a>')
        self.assertRegex(page, r'<a [^>]*href="__PUBLIC_URL__/web/login"[^>]*>Sign in</a>')

    def test_page_has_one_fixed_theme(self):
        # Black and white by design: no scheme switching, one logo file.
        for name in ("index.html", "site.css"):
            self.assertNotIn("prefers-color-scheme", (SITE / name).read_text(encoding="utf-8"), name)
        self.assertNotIn("<picture", self._page())

    def test_the_one_lockup_is_the_generated_dark_logo(self):
        svgs = sorted(p.relative_to(SITE).as_posix() for p in SITE.rglob("*.svg"))
        self.assertEqual(svgs, ["lockup-dark.svg"])
        # Byte-equal in git's canonical form. The source's working copy can end
        # in CR LF on a Windows checkout (core.autocrlf, or the generator), while
        # deploy/ is LF by .gitattributes; both commit to the same blob.
        source = REPO / "addons" / "web" / "static" / "img" / "odoo_logo_dark.svg"
        self.assertEqual((SITE / "lockup-dark.svg").read_bytes(),
                         source.read_bytes().replace(b"\r\n", b"\n"))

    def test_fonts_are_woff2(self):
        fonts = sorted(p.name for p in (SITE / "fonts").iterdir())
        self.assertEqual(fonts, ["SourceSans3.woff2"])
        self.assertEqual((SITE / "fonts" / "SourceSans3.woff2").read_bytes()[:4], b"wOF2")
        css = (SITE / "site.css").read_text(encoding="utf-8")
        self.assertNotIn(".ttf", css)
        self.assertEqual(css.count('format("woff2")'), 1)

    def test_entry_script_substitutes_public_url(self):
        text = (DEPLOY / "nginx" / "40-afenda-site.sh").read_text(encoding="utf-8")
        self.assertIn('${PUBLIC_URL:?', text)
        self.assertIn("__PUBLIC_URL__", text)
        self.assertTrue(text.startswith("#!/bin/sh\n"))

    def test_entry_script_drops_one_trailing_slash(self):
        # The page appends "/request-access" itself; "https://x/" would give "//".
        text = (DEPLOY / "nginx" / "40-afenda-site.sh").read_text(encoding="utf-8")
        strip = re.search(r"^PUBLIC_URL=\$\{PUBLIC_URL%/\}$", text, re.MULTILINE)
        self.assertIsNotNone(strip, "40-afenda-site.sh does not strip a trailing /")
        self.assertLess(strip.start(), text.index("sed -i"))

    def test_entry_script_rejects_sed_and_attribute_metacharacters(self):
        # `#` ends the sed expression, `&` and `\` act in its replacement, and
        # `"` would close the href: each must stop nginx from starting.
        text = (DEPLOY / "nginx" / "40-afenda-site.sh").read_text(encoding="utf-8")
        case = re.search(r'case "\$PUBLIC_URL" in\s*\n\s*(.+?)\)\s*\n(.*?);;', text, re.S)
        self.assertIsNotNone(case, "40-afenda-site.sh has no PUBLIC_URL character check")
        patterns, body = case.group(1), case.group(2)
        for pattern in ("*'#'*", "*'&'*", "*'\\'*", "*'\"'*"):
            self.assertIn(pattern, patterns)
        self.assertIn(">&2", body)
        self.assertRegex(body, r"\bexit 1\b")
        self.assertLess(case.start(), text.index("sed -i"))

    def _landing_servers(self, conf):
        """(server-level text, [location texts with an add_header]) for each
        server block that serves deploy/site."""
        text = (DEPLOY / "nginx" / conf).read_text(encoding="utf-8")
        text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        servers, i = [], 0
        while (start := text.find("server {", i)) != -1:
            depth, j = 0, text.index("{", start)
            while True:
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                if depth == 0:
                    break
                j += 1
            block, i = text[start:j + 1], j + 1
            if "root /usr/share/nginx/site;" not in block:
                continue
            locations = re.findall(r"location[^{]*\{[^{}]*\}", block)
            top = block
            for loc in locations:
                top = top.replace(loc, "")
            servers.append((top, [l for l in locations if "add_header" in l]))
        return servers

    def test_landing_servers_send_security_headers(self):
        # Everything is a same-origin file, so 'self' alone allows the page:
        # no style hash to keep in step, no 'unsafe-inline' anywhere.
        csp = ("add_header Content-Security-Policy \"default-src 'self'; "
               "frame-ancestors 'none'; base-uri 'none'; form-action 'none'\" always;")
        for conf, expected in (("afenda.conf", 1), ("afenda.tls.conf", 1)):
            servers = self._landing_servers(conf)
            self.assertEqual(len(servers), expected, f"{conf}: landing server blocks")
            for top, locations in servers:
                # A location with its own add_header inherits none of the server's.
                for scope in [top] + locations:
                    self.assertIn("add_header X-Content-Type-Options nosniff always;", scope, conf)
                    self.assertIn(csp, scope, f"{conf}: CSP missing, or its style hash is stale")
                    if conf == "afenda.tls.conf":
                        self.assertIn("add_header Strict-Transport-Security", scope, conf)


class DeployRedeployAndDnsTests(unittest.TestCase):
    def test_init_upgrades_modules_on_redeploy(self):
        # --outdated: a bumped manifest version applies on redeploy, and a
        # plain restart does not reload module data (odoo/cli/module.py).
        code = [l for l in (DEPLOY / "init.sh").read_text(encoding="utf-8").splitlines()
                if not l.lstrip().startswith("#")]
        self.assertTrue(any(re.search(r'module upgrade --outdated -c "\$RC" \$MODULES\b', l) for l in code),
                        "init.sh never runs `module upgrade`")

    def _records(self):
        rows = []
        for line in (DEPLOY / "dns" / "nexuscanon.com.records").read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split("\t")
            self.assertEqual(len(fields), 5, f"not five tab-separated fields: {line!r}")
            rows.append(tuple(fields))
        return rows

    def test_dns_zone_has_no_wildcard(self):
        rows = self._records()
        self.assertTrue(rows)
        for _rtype, name, _data, _priority, _ttl in rows:
            self.assertNotIn("*", name, "a wildcard record")

    def test_dns_zone_sends_app_mail_through_resend(self):
        # DigitalOcean blocks outbound SMTP 25/465/587, so the ERP relays
        # through Resend on 2587. The records are the ones Resend's API lists
        # for the domain (registered 2026-09-23, region ap-northeast-1): its
        # return path and SPF are the send. and rsend. CNAMEs, so the apex SPF
        # stays Zoho's alone.
        rows = self._records()
        resend = {(rtype, name) for rtype, name, _d, _p, _t in rows
                  if name in ("send", "rsend", "resend._domainkey")}
        self.assertEqual(resend, {("CNAME", "send"), ("CNAME", "rsend"), ("TXT", "resend._domainkey")})
        cnames = {(n, d) for r, n, d, _p, _t in rows if r == "CNAME"}
        self.assertIn(("send", "send.forge.rmta.net."), cnames)
        self.assertIn(("rsend", "rsend-apne1.forge.rmta.net."), cnames)
        dkim = [d for r, n, d, _p, _t in rows if (r, n) == ("TXT", "resend._domainkey")]
        self.assertTrue(dkim[0].startswith("p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDnMGq"), dkim)

    def test_dns_cname_names_hold_nothing_else(self):
        # RFC 1034 section 3.6.2: a name with a CNAME has no other records.
        rows = self._records()
        cname_names = {n for r, n, _d, _p, _t in rows if r == "CNAME"}
        others = [(r, n) for r, n, _d, _p, _t in rows if n in cname_names and r != "CNAME"]
        self.assertEqual(others, [])
        apex_spf = [d for r, n, d, _p, _t in rows if (r, n) == ("TXT", "@") and d.startswith("v=spf1")]
        self.assertEqual(apex_spf, ["v=spf1 include:zohomail.com ~all"])

    def test_dns_caa_issue_value_is_a_fqdn(self):
        # DigitalOcean's API answers 422 "Data needs to be a FQDN with issue or
        # issuewild" to a CAA value without its trailing dot.
        caa = [data for rtype, _name, data, _p, _t in self._records() if rtype == "CAA"]
        self.assertEqual(len(caa), 1)
        flags, tag, value = caa[0].split(" ", 2)
        self.assertEqual((flags, tag), ("0", "issue"))
        self.assertTrue(value.strip('"').endswith("."), f"CAA value without trailing dot: {value}")

    def test_dns_zone_keeps_zoho_mail(self):
        mx = {(name, data, priority) for rtype, name, data, priority, _ttl in self._records()
              if rtype == "MX" and name == "@"}
        self.assertEqual(mx, {("@", "mx.zoho.com.", "10"), ("@", "mx2.zoho.com.", "20"),
                              ("@", "mx3.zoho.com.", "50")})


if __name__ == "__main__":
    unittest.main()
