"""Refresh the bounded Waterloo open-data snapshot, never utility records."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://services.arcgis.com/ZpeBVw5o1kjit7LT/arcgis/rest/services/Roads/FeatureServer/0/query"
PARAMS = {
    "where": "1=1",
    "geometry": "-80.545,43.458,-80.515,43.478",
    "geometryType": "esriGeometryEnvelope",
    "inSR": 4326,
    "spatialRel": "esriSpatialRelIntersects",
    "outFields": "OBJECTID,STREET_NAME",
    "outSR": 4326,
    "f": "geojson",
    "orderByFields": "OBJECTID",
    "resultRecordCount": 1000,
}


def main():
    response = requests.get(URL, params=PARAMS, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "error" in data or not data.get("features") or data.get("exceededTransferLimit"):
        raise RuntimeError("Missing or truncated source response")
    # Keep only public road identifiers and names, no address fields.
    data["features"].sort(key=lambda f: f["properties"]["OBJECTID"])
    content = (json.dumps(data, indent=2) + "\n").encode()
    (ROOT / "data/base/waterloo_roads.geojson").write_bytes(content)
    metadata = {
        "publisher": "City of Waterloo",
        "dataset": "Roads",
        "query_url": response.url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "City of Waterloo Open Data Licence",
        "catalogue": "https://data.waterloo.ca/",
        "permission": "https://www.waterloo.ca/council-and-city-administration/open-data-and-maps/",
        "feature_count": len(data["features"]),
        "sha256": hashlib.sha256(content).hexdigest(),
        "scope": "Roads intersecting a small central Waterloo envelope; not the whole city",
    }
    (ROOT / "data/base/source.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Saved {len(data['features'])} public road segments")


if __name__ == "__main__":
    main()
