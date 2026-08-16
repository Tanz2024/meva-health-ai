"""Regression test for the Streamlit Cloud synthetic-data-discovery incident.

Root cause: meva.mcp.registry.DATA_DIR is computed relative to registry.py's
own __file__ (four .parent calls -> repo root -> data/synthetic/synthea). A
NON-editable install (`pip install .`) copies package files into
site-packages, so that arithmetic lands inside the venv instead of the
cloned repository, and every public synthetic patient silently disappears —
this is exactly what requirements.txt using `.[playground]` instead of
`-e .[playground]` caused on Streamlit Community Cloud.

This test builds a real, disposable venv and performs an actual editable
install from this repository (the same installation style
requirements.txt now uses and Streamlit Cloud will perform), then confirms
DATA_DIR resolves inside the repo and all 21 public patients are visible.
It is slower than the rest of the suite (a real `pip install`) but is the
only way to actually catch this class of packaging regression — a purely
in-process test would still be running from whatever install mode already
happens to be active in the current environment and could miss the bug.
"""

import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.slow
def test_editable_install_resolves_data_dir_inside_repo(tmp_path):
    venv_dir = tmp_path / "venv"
    venv.create(venv_dir, with_pip=True)
    venv_python = venv_dir / "bin" / "python3"
    if not venv_python.exists():
        venv_python = venv_dir / "Scripts" / "python.exe"  # Windows, just in case

    install = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--quiet", "-e", str(REPO_ROOT)],
        capture_output=True, text=True, timeout=300,
    )
    assert install.returncode == 0, f"editable install failed:\n{install.stdout}\n{install.stderr}"

    check = subprocess.run(
        [str(venv_python), "-c", (
            "from meva.mcp.registry import DATA_DIR; "
            "from meva.mcp.server import list_patients; "
            "print(DATA_DIR); "
            "print(DATA_DIR.exists()); "
            "print(len(list_patients()))"
        )],
        capture_output=True, text=True, timeout=60,
    )
    assert check.returncode == 0, f"post-install check failed:\n{check.stdout}\n{check.stderr}"

    lines = check.stdout.strip().splitlines()
    resolved_data_dir, exists, patient_count = lines[0], lines[1], int(lines[2])

    assert resolved_data_dir == str(REPO_ROOT / "data" / "synthetic" / "synthea")
    assert exists == "True"
    assert patient_count == 21


def test_requirements_txt_uses_editable_install():
    """requirements.txt (what Streamlit Cloud reads) must install MEVA editable —
    a plain, non-editable `.[playground]` reproduces the exact incident above."""
    text = (REPO_ROOT / "requirements.txt").read_text()
    non_comment_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert non_comment_lines == ["-e .[playground]"]
