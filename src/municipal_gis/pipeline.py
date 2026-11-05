"""Build local GIS, workbook and sharing outputs from a registry."""
import argparse
import json
from pathlib import Path
import folium
import geopandas as gpd
import pandas as pd
from branca.element import Element
from .model import prepare_assets
from .workbook import export_workbook

COLORS={1:'#177C66',2:'#73A857',3:'#E1AD38',4:'#D46B32',5:'#A12B3A'}


def export_web(assets, roads, path):
    web=folium.Map(location=[43.468,-80.53],zoom_start=14,tiles=None)
    folium.TileLayer('OpenStreetMap',name='Online street labels').add_to(web)
    folium.GeoJson(roads.to_crs(4326),name='Waterloo public roads',style_function=lambda _: {'color':'#8a959d','weight':1.5},tooltip=folium.GeoJsonTooltip(fields=['STREET_NAME'],aliases=['Road'])).add_to(web)
    for system in ['Water','Sanitary','Stormwater']:
        frame=assets[assets.system==system].to_crs(4326)
        folium.GeoJson(frame,name=system,style_function=lambda f: {'color':COLORS[f['properties']['condition']],'weight':4,'opacity':.85},highlight_function=lambda _: {'weight':8},tooltip=folium.GeoJsonTooltip(fields=['asset_id','condition','age_years','priority_score','replacement_year','lifecycle_cost_cad'],aliases=['Synthetic asset','Condition (1 good, 5 poor)','Age (years)','Priority /100','Replacement year','Nominal cost CAD'])).add_to(web)
    bounds=assets.to_crs(4326).total_bounds
    web.fit_bounds([[bounds[1],bounds[0]],[bounds[3],bounds[2]]])
    folium.LayerControl(collapsed=False).add_to(web)
    web.get_root().html.add_child(Element('<div style="position:fixed;bottom:24px;left:16px;z-index:9999;background:white;padding:14px;max-width:330px;font:14px Arial;box-shadow:0 1px 8px #888"><b>SYNTHETIC utility replacement map</b><br>Waterloo, Ontario. Pipes are invented; never use for excavation.<br><span style="color:#177C66">1 Good</span> | 2 | 3 | 4 | <span style="color:#A12B3A">5 Very poor</span><br>Colour: condition. Hover for age, score and cost. Toggle systems at top right.<br>Roads: City of Waterloo Open Data Licence.<br>Asset data is embedded; map libraries and optional tiles require internet.</div>'))
    web.save(str(path))
    path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')


def build(registry_path, roads_path, destination, as_of_year=2026):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    roads=gpd.read_file(roads_path)
    assets=prepare_assets(pd.read_csv(registry_path),roads,as_of_year)
    package=destination/'assets.gpkg'
    # Only overwrite this pipeline's named output, so reruns never append duplicate features.
    if package.exists(): package.unlink()
    assets.to_file(package,layer='assets',driver='GPKG')
    roads.to_crs(26917).to_file(package,layer='roads',driver='GPKG')
    assets.drop(columns='geometry').to_csv(destination/'ranked_assets.csv',index=False)
    export_workbook(assets,destination/'lifecycle.xlsx',as_of_year)
    export_web(assets,roads,destination/'web_map.html')
    summary={'assets':len(assets),'roads':len(roads),'base_year':as_of_year,'replacement_cost_cad':round(float(assets.replacement_cost_cad.sum()),2),'lifecycle_cost_cad':round(float(assets.lifecycle_cost_cad.sum()),2),'due_now':int((assets.replacement_year==as_of_year).sum()),'length_km':round(float(assets.length_m.sum()/1000),3),'crs':'EPSG:26917','synthetic':True}
    (destination/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))
    return assets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,default=Path('data/input/registry.csv'))
    parser.add_argument('--roads',type=Path,default=Path('data/base/waterloo_roads.geojson'))
    parser.add_argument('--out',type=Path,default=Path('outputs'))
    parser.add_argument('--as-of-year',type=int,default=2026)
    args=parser.parse_args();build(args.registry,args.roads,args.out,args.as_of_year)

if __name__=='__main__': main()
