"""Behaviour of the deploy shell scripts, run for real against stand-ins.

`deploy/dns/apply-do-dns.sh` runs against a fake `doctl` on PATH that
answers the listing from a file and logs every create call, so the tests
see exactly which records the script would publish. Every script under
`deploy/` is also parsed with `bash -n`. Needs a POSIX `sh` and `bash`
(Git Bash on Windows, any Linux CI runner); no Docker, no network.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "deploy"
SH = shutil.which("sh")
BASH = shutil.which("bash")

FAKE_DOCTL = """#!/bin/sh
case "$*" in
  "compute domain list"*) echo nexuscanon.com ;;
  "compute domain records list"*) cat "$FAKE_LISTING" ;;
  "compute domain records create"*) printf '%s\\n' "$*" >> "$FAKE_LOG" ;;
  *) echo "fake doctl: unexpected: $*" >&2; exit 9 ;;
esac
"""


def _write(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


@unittest.skipUnless(SH, "needs a POSIX sh")
class ApplyDoDnsDriftTests(unittest.TestCase):
    """A record edited by hand in the console must be reported, not doubled.

    The zone file said `v=DMARC1; p=none;` while the live record had been
    changed to `p=quarantine`; the script compared whole values, created a
    second _dmarc TXT, and two DMARC records make receivers ignore DMARC
    (RFC 7489 section 6.6.3). SPF has the same rule (RFC 7208 section 4.5).
    """

    def _run(self, records, listing):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "bin").mkdir()
        _write(tmp / "bin" / "doctl", FAKE_DOCTL)
        os.chmod(tmp / "bin" / "doctl", 0o755)
        shutil.copy(DEPLOY / "dns" / "apply-do-dns.sh", tmp / "apply-do-dns.sh")
        _write(tmp / "nexuscanon.com.records", "".join("\t".join(r) + "\n" for r in records))
        _write(tmp / "listing.txt", "".join(f"{t}    {n}    {d}\n" for t, n, d in listing))
        log = tmp / "creates.log"
        env = dict(os.environ, FAKE_LISTING=str(tmp / "listing.txt"), FAKE_LOG=str(log),
                   PATH=str(tmp / "bin") + os.pathsep + os.environ.get("PATH", ""))
        proc = subprocess.run([SH, str(tmp / "apply-do-dns.sh"), "203.0.113.7"], env=env,
                              capture_output=True, text=True, timeout=60)
        creates = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return proc, creates

    def test_changed_dmarc_is_reported_not_duplicated(self):
        proc, creates = self._run(
            records=[("TXT", "_dmarc", "v=DMARC1; p=none;", "", "3600"),
                     ("A", "app", "{{DROPLET_IP}}", "", "3600")],
            listing=[("TXT", "_dmarc", "v=DMARC1; p=quarantine;")])
        self.assertEqual(len(creates), 1, creates)
        self.assertIn("--record-name app", creates[0])
        self.assertIn("drift", proc.stderr)
        self.assertIn("_dmarc", proc.stderr)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)

    def test_changed_spf_is_reported_not_duplicated(self):
        proc, creates = self._run(
            records=[("TXT", "@", "v=spf1 include:zohomail.com ~all", "", "3600")],
            listing=[("TXT", "@", "v=spf1 include:zohomail.com include:example.net ~all")])
        self.assertEqual(creates, [])
        self.assertIn("drift", proc.stderr)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)

    def test_other_txt_on_the_same_name_is_still_created(self):
        # Only SPF and DMARC are one-per-name; a verification TXT next to the
        # SPF record is a separate record and must be published.
        proc, creates = self._run(
            records=[("TXT", "@", "v=spf1 include:zohomail.com ~all", "", "3600"),
                     ("TXT", "@", "zoho-verification=zb1.zmverify.zoho.com", "", "3600")],
            listing=[("TXT", "@", "v=spf1 include:zohomail.com ~all")])
        self.assertEqual(len(creates), 1, creates)
        self.assertIn("zoho-verification", creates[0])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_identical_zone_creates_nothing(self):
        proc, creates = self._run(
            records=[("TXT", "_dmarc", "v=DMARC1; p=quarantine;", "", "3600")],
            listing=[("TXT", "_dmarc", "v=DMARC1; p=quarantine;")])
        self.assertEqual(creates, [])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


@unittest.skipUnless(BASH, "needs bash")
class DeployScriptsParseTests(unittest.TestCase):
    def test_every_deploy_script_parses(self):
        scripts = sorted(p for p in DEPLOY.rglob("*.sh") if "secrets" not in p.parts)
        self.assertTrue(scripts)
        broken = []
        for script in scripts:
            proc = subprocess.run([BASH, "-n", str(script)], capture_output=True, text=True, timeout=30)
            if proc.returncode:
                broken.append(f"{script.relative_to(REPO)}: {proc.stderr.strip()}")
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
