import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point
from municipal_gis.model import clean_registry, priority_score, prepare_assets


def registry():
    return pd.DataFrame(
        [
            dict(
                asset_id=" W-1 ",
                road_id=1,
                system=" water ",
                installed_year="1980",
                condition="4",
                unit_cost_cad_m="1500",
                service_life_years="80",
            )
        ]
    )


def roads():
    return gpd.GeoDataFrame(
        {"OBJECTID": [1], "STREET_NAME": ["King"]},
        geometry=[LineString([(-80.53, 43.46), (-80.529, 43.46)])],
        crs=4326,
    )


def test_clean_types_and_spaces():
    row = clean_registry(registry(), 2026).iloc[0]
    assert row.asset_id == "W-1" and row.system == "Water" and row.condition == 4


@pytest.mark.parametrize(
    "column,value",
    [
        ("condition", 0),
        ("condition", 6),
        ("condition", 2.5),
        ("installed_year", 2027),
        ("installed_year", 1970.5),
        ("installed_year", 0),
        ("unit_cost_cad_m", 0),
        ("unit_cost_cad_m", float("inf")),
        ("condition", None),
        ("service_life_years", 0),
        ("system", "gas"),
        ("asset_id", " "),
        ("road_id", 1.2),
    ],
)
def test_reject_bad_inputs(column, value):
    frame = registry()
    frame[column] = value
    with pytest.raises(ValueError):
        clean_registry(frame, 2026)


def test_reject_duplicate_ids_after_trimming():
    frame = pd.concat([registry(), registry()])
    with pytest.raises(ValueError, match="duplicate"):
        clean_registry(frame, 2026)


def test_missing_column_and_empty():
    with pytest.raises(ValueError):
        clean_registry(registry().drop(columns="condition"), 2026)
    with pytest.raises(ValueError):
        clean_registry(registry().iloc[:0], 2026)


def test_score_known_value_and_bounds():
    assert priority_score(1, 0, 80, 500) == 0
    assert priority_score(5, 160, 80, 5000) == 100
    assert priority_score(3, 40, 80, 2750) == 50


def test_score_monotonic():
    assert priority_score(4, 40, 80, 1000) > priority_score(3, 40, 80, 1000)
    assert priority_score(3, 60, 80, 1000) > priority_score(3, 40, 80, 1000)
    assert priority_score(3, 40, 80, 2000) > priority_score(3, 40, 80, 1000)


@pytest.mark.parametrize(
    "args",
    [(0, 2, 80, 500), (3, -1, 80, 500), (3, 40, 0, 500), (3, 40, 80, float("nan"))],
)
def test_score_rejects_invalid(args):
    with pytest.raises(ValueError):
        priority_score(*args)


def test_geometry_join_length_cost_and_schedule():
    assets = prepare_assets(registry(), roads(), 2026)
    a = assets.iloc[0]
    assert assets.crs.to_epsg() == 26917
    assert 70 < a.length_m < 90
    assert a.replacement_cost_cad == round(a.length_m * 1500, 2)
    assert a.replacement_year == 2026  # condition 4 is due now
    assert a.lifecycle_cost_cad == a.replacement_cost_cad


def test_unknown_road_and_duplicate_road_rejected():
    frame = registry()
    frame["road_id"] = 2
    with pytest.raises(ValueError, match="road"):
        prepare_assets(frame, roads(), 2026)
    with pytest.raises(ValueError, match="road"):
        prepare_assets(registry(), pd.concat([roads(), roads()]), 2026)


def test_bad_geometry_and_missing_crs_rejected():
    r = roads()
    r.geometry = [Point(-80, 43)]
    with pytest.raises(ValueError, match="geometry"):
        prepare_assets(registry(), r, 2026)
    r = roads().set_crs(None, allow_override=True)
    with pytest.raises(ValueError, match="CRS"):
        prepare_assets(registry(), r, 2026)


def test_schedule_has_backlog_and_inflation():
    frame = registry()
    frame["installed_year"] = 2020
    frame["condition"] = 1
    a = prepare_assets(frame, roads(), 2026).iloc[0]
    assert a.replacement_year == 2100
    assert a.lifecycle_cost_cad == round(a.replacement_cost_cad * 1.025**74, 2)


def test_multiple_systems_share_road_without_overlapping_geometry():
    frame = pd.concat([registry(), registry()], ignore_index=True)
    frame.loc[1, ["asset_id", "system"]] = ["S-1", "Sanitary"]
    assets = prepare_assets(frame, roads(), 2026)
    assert not assets.geometry.iloc[0].equals(assets.geometry.iloc[1])


def test_missing_road_key_is_rejected():
    r = pd.concat([roads(), roads()], ignore_index=True)
    r.loc[1, "OBJECTID"] = None
    with pytest.raises(ValueError, match="road"):
        prepare_assets(registry(), r, 2026)


def test_calculated_cost_overflow_is_rejected():
    frame = registry()
    frame["unit_cost_cad_m"] = 1e308
    with pytest.raises(ValueError, match="cost"):
        prepare_assets(frame, roads(), 2026)
