"""Isolated desktop integration check; do not load wheel-bundled GDAL here."""

import math
import shutil
import sys
from pathlib import Path
from pypdf import PdfReader
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtGui import QImage, QColor
from municipal_gis.qgis_project import create_project

ROOT = Path(__file__).resolve().parents[1]


def verify(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    shutil.copy(ROOT / "outputs/assets.gpkg", source / "assets.gpkg")
    create_project(source)
    image = QImage(str(source / "replacement_map.png"))
    assert not image.isNull()
    # Count only the map interior, excluding the legend and text.
    colors = {
        QColor(c).rgb() for c in ["#177C66", "#73A857", "#E1AD38", "#D46B32", "#A12B3A"]
    }
    hits = sum(
        image.pixel(x, y) in colors
        for x in range(int(image.width() * 0.05), int(image.width() * 0.68), 2)
        for y in range(int(image.height() * 0.16), int(image.height() * 0.87), 2)
    )
    assert hits > 500, f"Map is missing rendered utility lines: {hits} colour pixels"
    assert (source / "replacement_map.pdf").stat().st_size > 20000
    assert len(PdfReader(source / "replacement_map.pdf").pages) == 1
    moved = tmp_path / "moved"
    shutil.move(source, moved)
    project = QgsProject()
    assert project.read(str(moved / "municipal_assets.qgz"))
    assert len(project.mapLayers()) == 7
    assert all(layer.isValid() for layer in project.mapLayers().values())
    for layer in project.mapLayers().values():
        assert layer.featureCount() == 382
        assert layer.crs().authid() == "EPSG:26917"
        assert all(
            math.isfinite(v)
            for v in [
                layer.extent().xMinimum(),
                layer.extent().xMaximum(),
                layer.extent().yMinimum(),
                layer.extent().yMaximum(),
            ]
        )
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
