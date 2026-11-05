# How the example works

## Public roads, invented utilities

I use 382 public City of Waterloo road segments intersecting a small central Waterloo bounding box. The cached GeoJSON contains only road IDs, road names and geometry. `data/base/source.json` records the exact query, download date, count and SHA-256 checksum. The City permits reuse under its Open Data Licence: https://www.waterloo.ca/council-and-city-administration/open-data-and-maps/ and https://data.waterloo.ca/.

The script `scripts/fetch_roads.py` checks for service errors, missing features and truncation. It does not refresh automatically during a build. A source refresh is an explicit action because changed road IDs could break an existing registry. Run `scripts/make_registry.py` afterwards only if you want to discard and regenerate the sample registry.

Every utility record is synthetic. A stable hash of system and road ID assigns an installation year, condition and sample unit cost. There is one invented pipe per system per road, totalling 1,146 records. Pipe centre lines follow roads with a 0 m, +5 m or -5 m illustrative offset. These offsets make systems visible; they are not survey positions, a network model or proof of buried infrastructure. There are no real utility records or private inputs.

## Cleaning

I trim asset IDs and normalize system names, convert numerical text to numbers, then reject missing fields, blank or duplicate IDs, non-finite numbers, fractional condition/year/road IDs, future installation years, nonpositive costs and service lives, and unknown systems. The spatial join rejects missing road IDs, duplicate road keys, missing coordinate systems, empty and non-line geometries. Nothing silently receives a good condition or zero replacement cost.

GeoPandas projects road geometry into EPSG:26917, NAD83 / UTM zone 17N. This stores Waterloo coordinates in metres, so length times CAD per metre produces a replacement cost in CAD. Geographic longitude/latitude degrees are never treated as metres. Synthetic line offsets are applied before length is measured. Display exports transform back to latitude/longitude for the web map.

## Score and schedule

Condition uses 1 for good and 5 for very poor. The score is:

```
condition_factor = (condition - 1) / 4
age_factor = min(age_years / service_life_years, 1)
cost_factor = clamp((unit_cost_cad_m - 500) / 4500, 0, 1)
priority_score = 100 * (0.60*condition_factor + 0.30*age_factor + 0.10*cost_factor)
```

The bounds are fixed between imports. A 3/5 condition, half-used service life and CAD 2,750/m gives 50/100. High unit cost increases the small cost exposure component. This ranks urgency and financial exposure; it does not optimize benefit per dollar. I sort highest score first, breaking ties by asset ID. I do not claim a calibrated probability of failure or use the score as a funded construction order.

The base year defaults to 2026. Conditions 4 and 5 are due now. Other assets are due at installation year plus service life, or now if overdue. I use sample service lives of 80 years for water, 75 for sanitary and 60 for stormwater. Rates start at CAD 1,800/m, 2,200/m and 2,600/m with synthetic variation. These rates are illustrative assumptions, not municipal estimates.

```
replacement_cost_cad = measured_length_m * unit_cost_cad_m
lifecycle_cost_cad = replacement_cost_cad * 1.025 ** (replacement_year - base_year)
```

Costs round to cents per asset. The workbook sums those rounded records. The lifecycle schedule includes one replacement for each asset, including years beyond the first ten. It excludes repeat replacement cycles, operations, rehabilitation, discounting, annual funding limits and failure consequences. The first-ten-year chart is deliberately a shorter view of the full annual PivotTable. Inflation is an explicit 2.5% sample assumption. For another scenario edit the Python rules and rebuild; editing the Excel schedule does not update GIS outputs.

## Files and portability

`model.py` owns cleaning, scoring, spatial joins and scheduling. `pipeline.py` writes two GeoPackage layers, an inspectable ranked CSV, the workbook, a summary and the web map. A GeoPackage is a single database file that stores map shapes and their attributes. Rebuilding replaces its named output instead of appending records.

`qgis_project.py` uses real PyQGIS APIs to create six asset layers, three by condition and three by age, plus the public roads. The project saves relative paths, disables the age group initially and includes an A3 print layout with map, legend, north arrow, scale, source attribution and synthetic-data warning. The CI test moves the folder and reloads every layer, so a saved path from the build machine cannot pass unnoticed.

`workbook.py` populates `templates/lifecycle.xlsx`, then creates Excel's native PivotTable definition, source relationship and complete cache records through openpyxl. It also writes the visible annual totals so readers can see the results before a refresh. The source table is `AssetSchedule`, and the PivotTable references its current rectangular range. After changing existing source rows, use Data > Refresh All in Excel. When adding or deleting rows, rebuild with Python so both the source range and cache match. The chart reads the first ten years of the PivotTable cells and refreshes with those cells. This is a normal chart connected to a PivotTable range, not an Excel PivotChart object.

The web export embeds all asset geometry and attributes in a single HTML file. Open it locally and send it as a file. Leaflet libraries load from public CDNs; optional OpenStreetMap tiles require internet. The QGIS project, GeoPackage, PDF and workbook are usable offline.

## Rebuild and verification

The Ubuntu workflow installs PyQGIS, builds all exports, runs the full test suite and uploads the generated files. Local Python tests can run without QGIS; the QGIS integration test skips in that environment. CI explicitly imports QGIS first, so its absence fails the build instead of silently skipping desktop coverage. Tests cover scoring boundaries and monotonicity, strict cleaning, spatial matching, geometry validation, metre-based length, year/inflation calculations, source checksum, GeoPackage totals, native PivotTable/cache relationships, every annual system total, chart presence, repeat builds and project portability.
