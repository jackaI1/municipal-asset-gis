import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import geopandas as gpd
import openpyxl
import pandas as pd
import pytest
from municipal_gis.pipeline import build

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def exported(tmp_path_factory):
    destination=tmp_path_factory.mktemp('exports')
    build(ROOT/'data/input/registry.csv', ROOT/'data/base/waterloo_roads.geojson',destination)
    return destination


def test_snapshot_provenance():
    source=json.loads((ROOT/'data/base/source.json').read_text())
    assert hashlib.sha256((ROOT/'data/base/waterloo_roads.geojson').read_bytes()).hexdigest()==source['sha256']
    assert source['feature_count']==len(gpd.read_file(ROOT/'data/base/waterloo_roads.geojson'))


def test_geopackage_layers_and_reconciliation(exported):
    a=gpd.read_file(exported/'assets.gpkg',layer='assets')
    assert len(a)==len(pd.read_csv(ROOT/'data/input/registry.csv'))
    assert set(a.system)=={'Water','Sanitary','Stormwater'}
    assert a.priority_score.between(0,100).all()
    summary=json.loads((exported/'summary.json').read_text())
    assert summary['assets']==len(a)
    assert summary['replacement_cost_cad']==round(a.replacement_cost_cad.sum(),2)
    assert 'roads' in gpd.list_layers(exported/'assets.gpkg').name.values


def test_native_pivot_cache_chart_and_totals(exported):
    path=exported/'lifecycle.xlsx'
    book=openpyxl.load_workbook(path)
    sheet=book['Lifecycle']
    assert len(sheet._pivots)==1 and len(sheet._charts)==1
    pivot=sheet._pivots[0]
    assert pivot.cache.recordCount==len(book['Assets']['A'])-4
    assert len(pivot.cache.records.r)==pivot.cache.recordCount
    assert pivot.cache.cacheSource.worksheetSource.sheet=='Assets'
    # Cached visible PivotTable values are useful even without Excel installed.
    rows=list(book['Assets'].values)[4:]
    total=sum(r[3] for r in rows)
    grand=next(row for row in sheet.values if row[0]=='Grand Total')
    assert grand[4]==pytest.approx(total,abs=.01)
    for row in list(sheet.values)[5:]:
        if isinstance(row[0],int):
            for i,system in enumerate(['Sanitary','Stormwater','Water'],1):
                expected=sum(r[3] for r in rows if r[1]==system and r[2]==row[0])
                assert (row[i] or 0)==pytest.approx(expected,abs=.01)
    with ZipFile(path) as archive:
        assert 'xl/pivotTables/pivotTable1.xml' in archive.namelist()
        assert 'xl/pivotCache/pivotCacheRecords1.xml' in archive.namelist()


def test_web_map_has_embedded_assets_and_disclaimer(exported):
    html=(exported/'web_map.html').read_text()
    assert 'SYNTHETIC' in html and 'Water' in html and 'priority_score' in html
    assert 'L.control.layers' in html and 'City of Waterloo' in html


def test_rebuild_same_destination(exported):
    build(ROOT/'data/input/registry.csv',ROOT/'data/base/waterloo_roads.geojson',exported)
    assert len(gpd.read_file(exported/'assets.gpkg',layer='assets'))==len(pd.read_csv(ROOT/'data/input/registry.csv'))
