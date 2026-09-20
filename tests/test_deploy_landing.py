import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductionLandingTests(unittest.TestCase):
    def stage(self, target: Path) -> str:
        subprocess.run(
            [str(ROOT / "deploy" / "build_stage.sh"), str(target)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return (target / "index.html").read_text(encoding="utf-8")

    def test_stage_is_static_safe_and_has_real_download(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "stage"
            page = self.stage(target)
            self.assertTrue((target / "brain-surgery.zip").is_file())
            self.assertTrue((target / "brain-surgery.zip.sha256").is_file())
            self.assertIn('href="/brain-surgery.zip"', page)
            self.assertIn("ILLUSTRATIVE EXAMPLE", page)
            self.assertIn("SAMPLE RESULTS", page)
            self.assertNotIn('id="app-data"', page)
            self.assertNotIn('id="page-templates"', page)
            self.assertNotIn('<nav class="preview-dock"', page)
            self.assertNotIn("data-action=", page)
            self.assertNotIn("data-route=", page)
            self.assertNotIn("simulate-apply", page)
            self.assertNotIn("create-share-link", page)
            self.assertNotIn("Federico De Ponte", page)
            self.assertNotIn("not Example measured", page)
            self.assertIn("not a measured personal result", page)
            self.assertNotIn("/Users/", page)
            self.assertIn("default read-only scan", page)
            self.assertIn("wait for my approval before running it", page)
            self.assertNotIn("compare my current setup with the proposed setup", page)

    def test_stage_builder_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "stage"
            target.mkdir()
            (target / "keep.txt").write_text("keep", encoding="utf-8")
            result = subprocess.run(
                [str(ROOT / "deploy" / "build_stage.sh"), str(target)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("keep", (target / "keep.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
