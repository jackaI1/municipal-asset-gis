"""Create a repeatable synthetic inventory; nothing is surveyed utility data."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    roads = json.loads((ROOT / "data/base/waterloo_roads.geojson").read_text())[
        "features"
    ]
    rows = []
    for feature in roads:
        road_id = feature["properties"]["OBJECTID"]
        for system, life, rate in [
            ("Water", 80, 1800),
            ("Sanitary", 75, 2200),
            ("Stormwater", 60, 2600),
        ]:
            key = f"{system}-{road_id}"
            seed = int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)
            rows.append(
                dict(
                    asset_id=key,
                    road_id=road_id,
                    system=system,
                    installed_year=1945 + seed % 79,
                    condition=1 + (seed // 79) % 5,
                    unit_cost_cad_m=rate + 100 * ((seed // 395) % 9),
                    service_life_years=life,
                )
            )
    with (ROOT / "data/input/registry.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic pipe records")


if __name__ == "__main__":
    main()
