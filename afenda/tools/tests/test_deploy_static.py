"""Static checks on the deploy files: no vendor host, pinned build inputs,
and a build context that carries every module.

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
            if p.is_file() and p.parent.name != "secrets" and b"\r\n" in p.read_bytes()
        ]
        self.assertEqual(crlf, [], "CRLF in a file that runs inside a Linux container")


if __name__ == "__main__":
    unittest.main()
