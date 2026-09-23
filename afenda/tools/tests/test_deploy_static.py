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
        # through Resend on 2587. Resend's return path is the send. subdomain
        # (its own MX and SPF), so the apex SPF stays Zoho's alone.
        rows = self._records()
        resend = {(rtype, name) for rtype, name, _d, _p, _t in rows
                  if name == "send" or name == "resend._domainkey"}
        self.assertEqual(resend, {("MX", "send"), ("TXT", "send"), ("TXT", "resend._domainkey")})
        self.assertIn(("MX", "send", "feedback-smtp.ap-northeast-1.amazonses.com.", "10"),
                      {(r, n, d, p) for r, n, d, p, _t in rows})
        self.assertIn(("TXT", "send", "v=spf1 include:amazonses.com ~all"),
                      {(r, n, d) for r, n, d, _p, _t in rows})
        dkim = [d for r, n, d, _p, _t in rows if (r, n) == ("TXT", "resend._domainkey")]
        self.assertTrue(dkim[0].startswith("p=MIGf"), dkim)
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
