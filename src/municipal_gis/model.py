"""Validation and transparent planning rules, independent of QGIS."""
import math
import geopandas as gpd
import numpy as np
import pandas as pd

SYSTEMS = {'Water': 0, 'Sanitary': 5, 'Stormwater': -5}
REQUIRED = ['asset_id','road_id','system','installed_year','condition','unit_cost_cad_m','service_life_years']


def clean_registry(frame, as_of_year):
    if not isinstance(as_of_year, int) or not 1900 <= as_of_year <= 2200:
        raise ValueError('as_of_year must be an integer from 1900 to 2200')
    if frame.empty or set(REQUIRED)-set(frame):
        raise ValueError('Registry is empty or missing required columns')
    result=frame[REQUIRED].copy()
    for name in ['asset_id','system']:
        if result[name].isna().any(): raise ValueError(f'Missing {name}')
        result[name]=result[name].astype(str).str.strip()
    result['system']=result.system.str.title()
    if (result.asset_id=='').any(): raise ValueError('Empty asset_id')
    if result.asset_id.duplicated().any(): raise ValueError('duplicate asset_id')
    if not result.system.isin(SYSTEMS).all(): raise ValueError('Unknown system')
    for name in REQUIRED[1:]:
        if name=='system': continue
        result[name]=pd.to_numeric(result[name], errors='coerce')
        if not np.isfinite(result[name]).all(): raise ValueError(f'Invalid {name}')
    for name in ['road_id','installed_year','condition','service_life_years']:
        if (result[name]%1!=0).any(): raise ValueError(f'{name} must be whole numbers')
        result[name]=result[name].astype(int)
    if not result.condition.between(1,5).all(): raise ValueError('condition must be 1 to 5')
    if not result.installed_year.between(1850,as_of_year).all(): raise ValueError('Invalid installation year')
    if (result.road_id<=0).any() or (result.unit_cost_cad_m<=0).any() or (result.service_life_years<=0).any():
        raise ValueError('IDs, cost and service life must be positive')
    return result


def priority_score(condition, age, service_life, unit_cost):
    values=[condition,age,service_life,unit_cost]
    if not all(math.isfinite(float(v)) for v in values) or not 1<=condition<=5 or condition%1 or age<0 or service_life<=0 or unit_cost<=0:
        raise ValueError('Invalid scoring inputs')
    # Fixed bounds keep scores comparable between imports; no dataset min/max scaling.
    cost_factor=max(0,min(1,(unit_cost-500)/4500))
    return round(100*(.60*(condition-1)/4 + .30*min(age/service_life,1) + .10*cost_factor),2)


def prepare_assets(registry, roads, as_of_year=2026):
    frame=clean_registry(registry,as_of_year)
    if roads.crs is None: raise ValueError('Road CRS is required')
    if 'OBJECTID' not in roads or roads.OBJECTID.duplicated().any(): raise ValueError('Missing or duplicate road IDs')
    if roads.empty or roads.geometry.isna().any() or roads.geometry.is_empty.any() or not roads.geometry.is_valid.all() or not roads.geom_type.isin(['LineString','MultiLineString']).all():
        raise ValueError('Invalid road geometry')
    base=roads.to_crs(26917).copy()  # NAD83 / UTM zone 17N, metres in Waterloo
    base=base.explode(index_parts=False).dissolve(by='OBJECTID',aggfunc='first').reset_index()
    joined=frame.merge(base[['OBJECTID','STREET_NAME','geometry']],left_on='road_id',right_on='OBJECTID',how='left',validate='many_to_one')
    if joined.geometry.isna().any(): raise ValueError('Registry references an unknown road')
    assets=gpd.GeoDataFrame(joined,geometry='geometry',crs=26917).drop(columns='OBJECTID')
    # Lateral offsets separate synthetic systems visually, never claim surveyed utility positions.
    assets.geometry=[geom.offset_curve(SYSTEMS[system]) if geom.geom_type=='LineString' else geom for geom,system in zip(assets.geometry,assets.system)]
    if assets.geometry.is_empty.any() or not assets.geometry.is_valid.all(): raise ValueError('Invalid offset geometry')
    assets['length_m']=assets.geometry.length.round(3)
    if (assets.length_m<=0).any(): raise ValueError('Zero length geometry')
    assets['age_years']=as_of_year-assets.installed_year
    assets['priority_score']=[priority_score(r.condition,r.age_years,r.service_life_years,r.unit_cost_cad_m) for r in assets.itertuples()]
    assets['replacement_cost_cad']=(assets.length_m*assets.unit_cost_cad_m).round(2)
    assets['replacement_year']=[as_of_year if r.condition>=4 else max(as_of_year,r.installed_year+r.service_life_years) for r in assets.itertuples()]
    assets['lifecycle_cost_cad']=(assets.replacement_cost_cad*1.025**(assets.replacement_year-as_of_year)).round(2)
    return assets.sort_values(['priority_score','asset_id'],ascending=[False,True]).reset_index(drop=True)
