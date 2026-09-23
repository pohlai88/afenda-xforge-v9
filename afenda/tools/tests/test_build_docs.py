import tempfile
import unittest
from pathlib import Path

from afenda.tools.build_docs import build, slug_for


class SlugTests(unittest.TestCase):
    def test_path_becomes_a_template_slug(self):
        self.assertEqual(slug_for("applications/general/users.md"), "applications_general_users")


class BuildTests(unittest.TestCase):
    def test_a_markdown_page_becomes_a_qweb_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            (src / "applications").mkdir(parents=True)
            (src / "applications" / "users.md").write_text(
                "# Users\n\nHow to add a user.\n", encoding="utf-8"
            )
            out = Path(tmp) / "guides.xml"
            count = build(src, out)
            self.assertEqual(count, 1)
            xml = out.read_text(encoding="utf-8")
            self.assertIn('id="guide_applications_users"', xml)
            self.assertIn("<h1>Users</h1>", xml)

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "a.md").write_text("# A\n", encoding="utf-8")
            (src / "b.md").write_text("# B\n", encoding="utf-8")
            out1, out2 = Path(tmp) / "1.xml", Path(tmp) / "2.xml"
            build(src, out1)
            build(src, out2)
            self.assertEqual(out1.read_text(encoding="utf-8"), out2.read_text(encoding="utf-8"))
