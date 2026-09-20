import hashlib
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "brain-surgery/SKILL.md",
    "brain-surgery/README.md",
    "brain-surgery/METHOD.md",
    "brain-surgery/PRIVACY.md",
    "brain-surgery/SECURITY.md",
    "brain-surgery/LICENSE",
    "brain-surgery/assets/approved-ui.css",
    "brain-surgery/assets/approved-cloud.js",
    "brain-surgery/scripts/render_scan.py",
    "brain-surgery/scripts/render_report.py",
}
PROTOTYPE_ONLY = {
    "brain-surgery/assets/approved-common.js",
    "brain-surgery/assets/approved-private.js",
    "brain-surgery/assets/approved-brain.svg",
}


def build(out: Path) -> Path:
    subprocess.run([str(ROOT / "scripts/package.sh"), str(out)], cwd=ROOT, check=True,
                   capture_output=True, text=True)
    return out / "brain-surgery.zip"


def test_package_contains_runtime_contract_and_excludes_prototype_js(tmp_path):
    archive = build(tmp_path / "one")
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
    assert REQUIRED <= names
    assert names.isdisjoint(PROTOTYPE_ONLY)
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)


def test_package_is_reproducible(tmp_path):
    first = build(tmp_path / "one").read_bytes()
    second = build(tmp_path / "two").read_bytes()
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    assert first == second


def test_deploy_tool_only_stages_a_labeled_preview(tmp_path):
    result = subprocess.run(
        [str(ROOT / "deploy/publish.sh"), "--build-only", str((tmp_path / "preview").resolve())],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    page = (tmp_path / "preview" / "index.html").read_text()
    assert "Brain Surgery by AGI Labs" in page
    assert "getedge.cc" not in page
    assert "Copy setup prompt" in page
    assert "DESIGN PREVIEW" not in page
    assert "preview:" in result.stdout


def test_deploy_tool_refuses_implicit_remote_publish():
    result = subprocess.run([str(ROOT / "deploy/publish.sh")], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "--publish" in result.stderr
