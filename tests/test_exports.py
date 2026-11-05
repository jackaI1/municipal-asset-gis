import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import geopandas as gpd
import openpyxl
import pandas as pd
import pytest
from municipal_gis.pipeline import build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    destination = tmp_path_factory.mktemp("exports")
    build(
        ROOT / "data/input/registry.csv",
        ROOT / "data/base/waterloo_roads.geojson",
        destination,
    )
    return destination


def test_snapshot_provenance():
    source = json.loads((ROOT / "data/base/source.json").read_text())
    assert (
        hashlib.sha256(
            (ROOT / "data/base/waterloo_roads.geojson").read_bytes()
        ).hexdigest()
        == source["sha256"]
    )
    assert source["feature_count"] == len(
        gpd.read_file(ROOT / "data/base/waterloo_roads.geojson")
    )


def test_geopackage_layers_and_reconciliation(exported):
    a = gpd.read_file(exported / "assets.gpkg", layer="assets")
    assert len(a) == len(pd.read_csv(ROOT / "data/input/registry.csv"))
    assert set(a.system) == {"Water", "Sanitary", "Stormwater"}
    assert a.priority_score.between(0, 100).all()
    summary = json.loads((exported / "summary.json").read_text())
    assert summary["assets"] == len(a)
    assert summary["replacement_cost_cad"] == round(a.replacement_cost_cad.sum(), 2)
    assert "roads" in gpd.list_layers(exported / "assets.gpkg").name.values


def test_native_pivot_cache_chart_and_totals(exported):
    path = exported / "lifecycle.xlsx"
    book = openpyxl.load_workbook(path)
    sheet = book["Lifecycle"]
    assert len(sheet._pivots) == 1 and len(sheet._charts) == 1
    pivot = sheet._pivots[0]
    assert pivot.cache.recordCount == len(book["Assets"]["A"]) - 4
    assert len(pivot.cache.records.r) == pivot.cache.recordCount
    assert pivot.cache.cacheSource.worksheetSource.sheet == "Assets"
    # Cached visible PivotTable values are useful even without Excel installed.
    rows = list(book["Assets"].values)[4:]
    total = sum(r[3] for r in rows)
    grand = next(row for row in sheet.values if row[0] == "Grand Total")
    assert grand[4] == pytest.approx(total, abs=0.01)
    for row in list(sheet.values)[5:]:
        if isinstance(row[0], int):
            for i, system in enumerate(["Sanitary", "Stormwater", "Water"], 1):
                expected = sum(r[3] for r in rows if r[1] == system and r[2] == row[0])
                assert (row[i] or 0) == pytest.approx(expected, abs=0.01)
    with ZipFile(path) as archive:
        assert "xl/pivotTables/pivotTable1.xml" in archive.namelist()
        assert "xl/pivotCache/pivotCacheRecords1.xml" in archive.namelist()


def test_web_map_has_embedded_assets_and_disclaimer(exported):
    html = (exported / "web_map.html").read_text()
    assert "SYNTHETIC" in html and "Water" in html and "priority_score" in html
    assert "L.control.layers" in html and "City of Waterloo" in html


def test_rebuild_same_destination(exported):
    build(
        ROOT / "data/input/registry.csv",
        ROOT / "data/base/waterloo_roads.geojson",
        exported,
    )
    assert len(gpd.read_file(exported / "assets.gpkg", layer="assets")) == len(
        pd.read_csv(ROOT / "data/input/registry.csv")
    )


def test_workbook_subset_of_systems_has_valid_pivot_indices(tmp_path):
    from municipal_gis.workbook import export_workbook
    from municipal_gis.model import prepare_assets

    roads = gpd.read_file(ROOT / "data/base/waterloo_roads.geojson")
    frame = pd.read_csv(ROOT / "data/input/registry.csv")
    assets = prepare_assets(frame[frame.system == "Water"].head(3), roads)
    path = tmp_path / "single-system.xlsx"
    export_workbook(assets, path, 2026)
    book = openpyxl.load_workbook(path)
    pivot = book["Lifecycle"]._pivots[0]
    items = pivot.cache.cacheFields[1].sharedItems._fields
    assert [item.v for item in items] == ["Sanitary", "Stormwater", "Water"]
    for record in pivot.cache.records.r:
        assert record._fields[1].v == 2
    assert all(item.x[0].v < len(items) for item in pivot.colItems)


def test_pivot_layout_and_chart_use_native_two_header_rows(exported):
    book = openpyxl.load_workbook(exported / "lifecycle.xlsx")
    sheet = book["Lifecycle"]
    pivot = sheet._pivots[0]
    assert sheet["A7"].value == 2026
    assert sheet["A6"].value == "Year"
    assert pivot.location.firstDataRow == 2
    assert sheet._charts[0].ser[0].cat.strRef.f == "'Lifecycle'!$A$7:$A$16"
