"""The tenant's signature: the crystal bear, pinned byte for byte.

The owner ruled on 2026-09-26 that the auth-page crystal bear (68b0b9913) is the tenant's
signature design and must not be overridden again: after the four-season stage recoloured
it, it was restored (docs/superpowers/specs/2026-09-26-tenant-signature.md). Seasons, weather
and anything else may only be added AROUND it, in their own files.

These digests fail the moment either signature file changes. The generator's own golden tests
(test_crystal_bear) only prove the files match the generator; this pins what the generator is
allowed to produce. Changing a digest here is the owner's decision, never a fix for a red test.
"""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SIGNATURE = {
    # the standalone master, rendered on its own
    "afenda/addons/afenda_brand/static/src/img/auth_hero/crystal_bear.svg":
        "98a47d9726f170e56e7b42a773db0c856a406f8e35f15ecd8d7e160952d64792",
    # the same bear, inline in the auth pages' QWeb template
    "afenda/addons/afenda_brand/views/auth_bear.xml":
        "6cd2b5ce299514a2a3dfc0cf0ad07fd5925bccd36d52a974ff7a2d3e019c26d6",
}


class TenantSignatureTests(unittest.TestCase):
    def test_the_signature_files_are_byte_identical_to_the_approved_bear(self):
        for rel, expected in SIGNATURE.items():
            with self.subTest(path=rel):
                digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
                self.assertEqual(
                    digest, expected,
                    f"{rel} changed. It is the tenant's signature design (owner ruling "
                    "2026-09-26): add seasonal or decorative work in separate files around "
                    "it, never in it. Only the owner may re-pin this digest.",
                )

    def test_agents_are_denied_edits_to_the_signature(self):
        import json
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        deny = settings.get("permissions", {}).get("deny", [])
        for rel in SIGNATURE:
            with self.subTest(path=rel):
                self.assertIn(f"Edit(/{rel})", deny)


if __name__ == "__main__":
    unittest.main()
