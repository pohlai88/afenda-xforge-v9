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
import time
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
class PruneBackupsTests(unittest.TestCase):
    """deploy/prune-backups.sh ROOT KEEP_DAYS, called by backup.sh."""

    def _root(self, folders):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        now = time.time()
        for name, age_days in folders.items():
            (root / name).mkdir()
            (root / name / "afenda.dump").write_bytes(b"x")
            stamp = now - age_days * 86400
            os.utime(root / name, (stamp, stamp))
        return root

    def _prune(self, root, days):
        return subprocess.run([BASH, str(DEPLOY / "prune-backups.sh"), str(root), str(days)],
                              capture_output=True, text=True, timeout=60)

    def test_deletes_old_stamp_folders_only(self):
        root = self._root({"20260801T024000Z": 40, "20260905T024000Z": 15,
                           "20260920T024000Z": 3, "20260923T024000Z": 0, "manual-copy": 40})
        proc = self._prune(root, 14)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(sorted(p.name for p in root.iterdir()),
                         ["20260920T024000Z", "20260923T024000Z", "manual-copy"])

    def test_never_deletes_the_newest_backup(self):
        # A host whose backups stopped a month ago must not lose the last one.
        root = self._root({"20260801T024000Z": 40, "20260802T024000Z": 39})
        proc = self._prune(root, 14)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([p.name for p in root.iterdir()], ["20260802T024000Z"])

    def test_rejects_a_keep_days_that_is_not_a_positive_integer(self):
        root = self._root({"20260801T024000Z": 40})
        for bad in ("0", "-3", "14d", ""):
            self.assertEqual(self._prune(root, bad).returncode, 2, bad)
        self.assertTrue((root / "20260801T024000Z").exists())


FAKE_RCLONE = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_LOG"
[ "$1" = "${FAKE_FAIL:-}" ] && exit 1
exit 0
"""


@unittest.skipUnless(BASH, "needs bash")
class OffsiteTests(unittest.TestCase):
    """deploy/offsite.sh ROOT REMOTE: copy, verify, and only then expire."""

    def _run(self, *args, env_extra=None):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "bin").mkdir()
        _write(tmp / "bin" / "rclone", FAKE_RCLONE)
        os.chmod(tmp / "bin" / "rclone", 0o755)
        (tmp / "backups").mkdir()
        log = tmp / "rclone.log"
        env = dict(os.environ, FAKE_LOG=str(log),
                   PATH=str(tmp / "bin") + os.pathsep + os.environ.get("PATH", ""))
        env.update(env_extra or {})
        argv = [a.replace("{root}", str(tmp / "backups")) for a in args]
        proc = subprocess.run([BASH, str(DEPLOY / "offsite.sh"), *argv], env=env,
                              capture_output=True, text=True, timeout=60)
        calls = [line.split()[0] for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        full = log.read_text(encoding="utf-8") if log.exists() else ""
        return proc, calls, full

    def test_copies_verifies_then_expires(self):
        proc, calls, full = self._run("{root}", "spaces:afenda-backups-sgp1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, ["copy", "check", "delete", "rmdirs"])
        self.assertIn("--one-way", full)
        self.assertIn("--min-age 30d", full)

    def test_keep_remote_days_is_configurable(self):
        proc, _calls, full = self._run("{root}", "spaces:b", env_extra={"KEEP_REMOTE_DAYS": "60"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--min-age 60d", full)

    def test_a_failed_verification_expires_nothing(self):
        proc, calls, _full = self._run("{root}", "spaces:b", env_extra={"FAKE_FAIL": "check"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(calls, ["copy", "check"])

    def test_bad_arguments_touch_nothing(self):
        for args, extra in ((("{root}",), None), (("{root}", "spaces:b"), {"KEEP_REMOTE_DAYS": "0"})):
            proc, calls, _full = self._run(*args, env_extra=extra)
            self.assertEqual(proc.returncode, 2, (args, extra, proc.stderr))
            self.assertEqual(calls, [])


FAKE_GIT = """#!/bin/sh
[ "$1" = -C ] && shift 2
printf 'git %s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  "rev-parse --show-toplevel") echo "$FAKE_REPO" ;;
  *"status --porcelain"*|*"status --short"*) printf '%s' "${FAKE_DIRTY:-}" ;;
  *"rev-parse HEAD") cat "$FAKE_HEAD" ;;
  *"checkout --detach FETCH_HEAD") echo newsha > "$FAKE_HEAD" ;;
  *"checkout --detach "*) for a; do last=$a; done; echo "$last" > "$FAKE_HEAD" ;;
esac
exit 0
"""

FAKE_DOCKER = """#!/bin/sh
printf 'docker %s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  "compose build") [ "${FAKE_FAIL:-}" = build ] && exit 1 ;;
  "compose ps -a init"*) echo "${FAKE_INIT_STATE:-exited 0}" ;;
esac
exit 0
"""

FAKE_CURL = """#!/bin/sh
printf 'curl %s\\n' "$*" >> "$FAKE_LOG"
[ "${FAKE_FAIL:-}" = health ] && exit 22
echo '{"status": "pass"}'
"""

FAKE_BACKUP = """#!/bin/sh
printf 'backup.sh %s\\n' "$*" >> "$FAKE_LOG"
mkdir -p "$1/20260923T024000Z"
"""


@unittest.skipUnless(BASH, "needs bash")
class RedeployTests(unittest.TestCase):
    """deploy/redeploy.sh [REF]: back up, fetch, build, start, check health."""

    def _run(self, *args, **fake):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "bin").mkdir()
        (tmp / "deploy").mkdir()
        for name, body in (("git", FAKE_GIT), ("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
            _write(tmp / "bin" / name, body)
            os.chmod(tmp / "bin" / name, 0o755)
        _write(tmp / "deploy" / "backup.sh", FAKE_BACKUP)
        os.chmod(tmp / "deploy" / "backup.sh", 0o755)
        shutil.copy(DEPLOY / "redeploy.sh", tmp / "deploy" / "redeploy.sh")
        _write(tmp / "deploy" / ".env", "COMPOSE_FILE=compose.yaml\nPUBLIC_URL=https://app.example.test/\n")
        _write(tmp / "head", "oldsha\n")
        log = tmp / "calls.log"
        env = dict(os.environ, FAKE_LOG=str(log), FAKE_REPO=str(tmp), FAKE_HEAD=str(tmp / "head"),
                   BACKUP_ROOT=str(tmp / "backups"), HEALTH_TRIES="2", HEALTH_WAIT="0",
                   PATH=str(tmp / "bin") + os.pathsep + os.environ.get("PATH", ""))
        env.update({f"FAKE_{k.upper()}": v for k, v in fake.items()})
        proc = subprocess.run([BASH, str(tmp / "deploy" / "redeploy.sh"), *args], env=env,
                              capture_output=True, text=True, timeout=60)
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        head = (tmp / "head").read_text(encoding="utf-8").strip()
        return proc, calls, head

    @staticmethod
    def _index(calls, prefix):
        return next(i for i, c in enumerate(calls) if c.startswith(prefix))

    def test_backs_up_before_changing_anything_then_checks_health(self):
        proc, calls, head = self._run("afenda/deidentify-phase1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        order = [self._index(calls, p) for p in (
            "backup.sh", "git fetch --depth 1 origin afenda/deidentify-phase1",
            "git checkout --detach FETCH_HEAD", "git submodule update --init --depth 1",
            "docker compose build", "docker compose up -d", "docker compose ps -a init",
            "curl")]
        self.assertEqual(order, sorted(order), calls)
        self.assertIn("https://app.example.test/web/health", [c for c in calls if c.startswith("curl")][0])
        self.assertEqual(head, "newsha")

    def test_refuses_a_checkout_with_tracked_changes(self):
        proc, calls, head = self._run(dirty=" M deploy/compose.yaml\n")
        self.assertEqual(proc.returncode, 1)
        self.assertFalse([c for c in calls if c.startswith(("backup.sh", "git fetch", "docker"))], calls)
        self.assertEqual(head, "oldsha")

    def test_a_failed_build_puts_the_previous_commit_back(self):
        proc, calls, head = self._run(fail="build")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(head, "oldsha")
        self.assertFalse([c for c in calls if c.startswith("docker compose up")], calls)

    def test_a_failed_init_or_health_check_names_the_backup_to_restore(self):
        for fake in ({"init_state": "exited 1"}, {"fail": "health"}):
            proc, _calls, _head = self._run(**fake)
            self.assertNotEqual(proc.returncode, 0, fake)
            self.assertIn("restore.sh", proc.stderr, fake)
            self.assertIn("20260923T024000Z", proc.stderr, fake)
            self.assertIn("oldsha", proc.stderr, fake)


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
