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
            self.assertTrue((target / "report.html").is_file())
            self.assertTrue((target / "report-summary.json").is_file())
            self.assertTrue((target / "social-card.svg").is_file())
            self.assertIn('href="/brain-surgery.zip"', page)
            self.assertIn('href="/report.html"', page)
            self.assertNotIn('href="#example"', page)
            self.assertIn("Brain Surgery by AGI Labs", page)
            self.assertIn("agi labs", page)
            self.assertNotIn("Building Edge", page)
            self.assertNotIn("Brain Surgery by Edge", page)
            self.assertIn('current 33 percent, tested 83 percent', page)
            self.assertIn('<div class="stat-big">33<small>%</small>', page)
            self.assertIn('<div class="stat-big blue">83<small>%</small>', page)
            self.assertIn('6 tasks · Same model · 2 targeted changes', page)
            self.assertNotIn('4 tasks · Same model · 3 targeted changes', page)
            report = (target / "report.html").read_text(encoding="utf-8")
            self.assertIn("Brain Surgery, by AGI Labs", report)
            self.assertIn("Illustrative example", report)
            self.assertNotIn('id="local-data"', report)
            self.assertIn("Same model. Better setup.", page)
            self.assertIn("Fictional tasks and results", page)
            self.assertNotIn("DESIGN PREVIEW", page)
            self.assertNotIn("brain scans shared", page)
            self.assertNotIn("Community average", page)
            self.assertNotIn('id="app-data"', page)
            self.assertNotIn('id="page-templates"', page)
            self.assertNotIn('<nav class="preview-dock"', page)
            self.assertNotIn("data-action=", page)
            self.assertNotIn("data-route=", page)
            self.assertNotIn("simulate-apply", page)
            self.assertNotIn("create-share-link", page)
            self.assertNotIn("Federico De Ponte", page)
            self.assertNotIn("not Example measured", page)
            self.assertIn("provided to show what the complete report contains", page)
            self.assertNotIn("/Users/", page)
            self.assertIn("Scan my recent work and installed skills", page)
            self.assertIn("Ask before running comparisons", page)
            self.assertNotIn("compare my current setup with the proposed setup", page)
            self.assertIn("Copy setup prompt", page)
            self.assertEqual(2, page.count("Install Brain Surgery from https://github.com/agilabs-ai/brain-surgery"))
            self.assertIn("Three things to know.", page)
            self.assertIn("Inspect. Test. Review.", page)
            self.assertIn("Would a different model help?", report)
            self.assertIn("33<small>% · 2/6", report)
            self.assertIn("50<small>% · 3/6", report)
            self.assertIn("83<small>% · 5/6", report)
            self.assertIn("The tasks behind the result.", report)
            self.assertIn("2 targeted changes.", report)
            self.assertIn("Current: Fail · Surgery: Pass", report)
            self.assertIn("View exact edit", report)
            self.assertIn("Affected tasks:", report)
            self.assertIn("Hi Lena, We just need your logo", report)

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
