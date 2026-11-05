"""Isolated desktop integration check; do not load wheel-bundled GDAL here."""

import shutil
import sys
from pathlib import Path
from pypdf import PdfReader
from qgis.core import QgsApplication, QgsProject
from municipal_gis.qgis_project import create_project

ROOT = Path(__file__).resolve().parents[1]


def verify(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    shutil.copy(ROOT / "outputs/assets.gpkg", source / "assets.gpkg")
    create_project(source)
    assert (source / "replacement_map.pdf").stat().st_size > 20000
    assert len(PdfReader(source / "replacement_map.pdf").pages) == 1
    moved = tmp_path / "moved"
    shutil.move(source, moved)
    project = QgsProject()
    assert project.read(str(moved / "municipal_assets.qgz"))
    assert len(project.mapLayers()) == 7
    assert all(layer.isValid() for layer in project.mapLayers().values())
    assert project.crs().authid() == "EPSG:26917"
    assert len(project.layoutManager().layouts()) == 1
    layout = project.layoutManager().layouts()[0]
    assert layout.itemById("main_map") is not None
    assert layout.itemById("scale_bar") is not None
    for layer in project.mapLayers().values():
        if "condition" in layer.name():
            assert layer.renderer().classAttribute() == "condition"
        if "age" in layer.name():
            assert layer.renderer().classAttribute() == "age_years"
            assert layer.renderer().ranges()[-1].upperValue() == 350
    project.clear()


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    try:
        verify(Path(sys.argv[1]))
    finally:
        app.exitQgis()
    print("QGIS project reload, all 7 layers, relative paths, PDF and layout verified")
