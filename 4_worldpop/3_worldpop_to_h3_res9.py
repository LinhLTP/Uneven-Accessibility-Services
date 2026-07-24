import re
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from exactextract import exact_extract
from shapely.geometry import Polygon

# 1. Setup ----

# 1.1. Imports
# (see above)

# 1.2. Paths and config
project_dir = Path("data/worldpop_hanoi_2018")
clip_dir = project_dir / "clipped"
out_dir = project_dir / "h3_res9"
out_dir.mkdir(parents=True, exist_ok=True)

boundary_path = "data/boundaries/hanoi_boundary.gpkg"
boundary_layer = None
h3_res = 9

# 2. Helper functions ----

# 2.1. Boundary reader
def read_boundary(path, layer=None):
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf.to_crs(4326)


# 2.2. WorldPop age-band labelling and filename parsing
def age_label(age_code):
    if age_code == 0:
        return "0_12m"
    if age_code == 1:
        return "1_4"
    if age_code == 80:
        return "80_plus"
    return f"{age_code}_{age_code + 4}"


def parse_worldpop_name(x):
    nm = Path(x).stem

    if nm == "vnm_ppp_2018_hanoi":
        return {"variable": "total_pop", "sex": "both", "age_code": None, "age_group": "total"}

    m = re.match(r"^vnm_(f|m)_(\d+)_2018_hanoi$", nm)
    if not m:
        return {"variable": "unknown", "sex": None, "age_code": None, "age_group": None}

    age_code = int(m.group(2))
    sex = "female" if m.group(1) == "f" else "male"
    return {"variable": "age_sex", "sex": sex, "age_code": age_code, "age_group": age_label(age_code)}


# 2.3. Convert a shapely polygon to an H3 LatLngPoly (lat/lng ordering)
def to_latlng_poly(geom):
    exterior = [(lat, lng) for lng, lat in geom.exterior.coords]
    holes = [[(lat, lng) for lng, lat in ring.coords] for ring in geom.interiors]
    return h3.LatLngPoly(exterior, *holes)


# 2.4. Aggregate one clipped raster onto the H3 hex grid
def aggregate_raster_to_h3(raster_path, hexes_gdf):
    values = exact_extract(str(raster_path), hexes_gdf, ["sum"], output="pandas")["sum"]

    df = pd.DataFrame({
        "h3_id": hexes_gdf["h3_id"].to_numpy(),
        "population": values.to_numpy(),
        "source_file": Path(raster_path).name,
    })
    parsed = parse_worldpop_name(raster_path)
    for k, v in parsed.items():
        df[k] = v
    return df


# 3. Build the H3 hex grid over Hanoi ----
hanoi = read_boundary(boundary_path, boundary_layer)

hanoi_geom = hanoi.geometry.union_all()
polys = hanoi_geom.geoms if hanoi_geom.geom_type == "MultiPolygon" else [hanoi_geom]

h3_ids = set()
for poly in polys:
    h3_ids.update(h3.polygon_to_cells(to_latlng_poly(poly), h3_res))
h3_ids = sorted(h3_ids)

hexes = gpd.GeoDataFrame(
    {"h3_id": h3_ids},
    geometry=[Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)]) for cell in h3_ids],
    crs=4326,
)
hexes["geometry"] = hexes.geometry.make_valid()

# 4. Aggregate clipped rasters onto the hex grid ----
clipped_rasters = sorted(clip_dir.glob("*_hanoi.tif"))

if len(clipped_rasters) == 0:
    raise FileNotFoundError(f"No clipped rasters found in: {clip_dir.resolve()}")

h3_long = pd.concat(
    [aggregate_raster_to_h3(f, hexes) for f in clipped_rasters], ignore_index=True
).sort_values(["variable", "sex", "age_code", "h3_id"])

h3_total = (
    h3_long[h3_long["variable"] == "total_pop"][["h3_id", "population"]]
    .rename(columns={"population": "total_pop"})
)

h3_age_sex_wide = (
    h3_long[h3_long["variable"] == "age_sex"]
    .assign(var_name=lambda d: d["sex"].map({"female": "f", "male": "m"}) + "_" + d["age_group"])
    [["h3_id", "var_name", "population"]]
    .pivot(index="h3_id", columns="var_name", values="population")
    .reset_index()
)

hexes_total = hexes.merge(h3_total, on="h3_id", how="left")
hexes_age_sex = hexes.merge(h3_age_sex_wide, on="h3_id", how="left")

validation = (
    h3_long.groupby(["source_file", "variable", "sex", "age_code", "age_group"], dropna=False)
    ["population"].sum().reset_index(name="h3_sum")
)

# 5. Export outputs ----
h3_long.to_csv(out_dir / "worldpop_hanoi_h3_res9_long.csv", index=False)
validation.to_csv(out_dir / "worldpop_hanoi_h3_res9_validation.csv", index=False)

hexes.to_file(out_dir / "worldpop_hanoi_h3_res9_geometry.gpkg", driver="GPKG")
hexes_total.to_file(out_dir / "worldpop_hanoi_h3_res9_total_pop.gpkg", driver="GPKG")
hexes_age_sex.to_file(out_dir / "worldpop_hanoi_h3_res9_age_sex_wide.gpkg", driver="GPKG")
