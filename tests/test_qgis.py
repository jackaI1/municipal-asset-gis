"""Real PyQGIS integration tests. CI requires QGIS; plain Python skips this file."""
import shutil
from pathlib import Path
import pytest
from pypdf import PdfReader
pytest.importorskip('qgis.core')
from qgis.core import QgsApplication, QgsProject
from municipal_gis.qgis_project import create_project

ROOT=Path(__file__).resolve().parents[1]


def test_qgis_project_portable_layout_and_exports(tmp_path):
    app=QgsApplication.instance() or QgsApplication([],False)
    app.initQgis()
    source=tmp_path/'original';source.mkdir()
    shutil.copy(ROOT/'outputs/assets.gpkg',source/'assets.gpkg')
    create_project(source)
    assert (source/'replacement_map.pdf').stat().st_size>20000
    assert len(PdfReader(source/'replacement_map.pdf').pages)==1
    moved=tmp_path/'moved';shutil.move(source,moved)
    project=QgsProject()
    assert project.read(str(moved/'municipal_assets.qgz'))
    assert len(project.mapLayers())==7
    assert all(layer.isValid() for layer in project.mapLayers().values())
    assert project.crs().authid()=='EPSG:26917'
    assert len(project.layoutManager().layouts())==1
    layout=project.layoutManager().layouts()[0]
    assert layout.itemById('main_map') is not None
    assert layout.itemById('scale_bar') is not None
    for layer in project.mapLayers().values():
        if 'condition' in layer.name(): assert layer.renderer().classAttribute()=='condition'
        if 'age' in layer.name(): assert layer.renderer().classAttribute()=='age_years'
    project.clear()
