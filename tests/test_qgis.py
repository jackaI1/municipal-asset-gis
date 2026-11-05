"""Run system QGIS in its own process, isolated from GeoPandas' bundled GDAL."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    importlib.util.find_spec("qgis") is None,
    reason="PyQGIS is installed in the full Ubuntu build",
)
def test_qgis_project_portable_layout_and_exports(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_qgis.py"), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=90,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "QT_QPA_PLATFORM": "offscreen",
        },
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
