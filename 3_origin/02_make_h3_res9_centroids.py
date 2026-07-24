from pathlib import Path

import geopandas as gpd
import h3
import matplotlib.pyplot as plt
import pandas as pd
from shapely.geometry import Polygon

# 1. Setup ----

# 1.1. Imports

# 1.2. Paths and parameters
PROJECT_DIR = Path("accessibility_hanoi")

VNM1_PATH = PROJECT_DIR / "vnm_admin_boundaries" / "vnm_admin1.geojson"
OUT_GPKG = PROJECT_DIR / "output" / "h3_origins_centroids.gpkg"
OUT_CSV = PROJECT_DIR / "output" / "h3_res9_summary.csv"
MAP_OUT = PROJECT_DIR / "output" / "hanoi_h3_res9_map.png"

H3_RES = 9
CRS_GEO = 4326
CRS_PROJ = 32648

# 2. Read and prepare Hanoi boundary ----
vnm1 = gpd.read_file(VNM1_PATH)

ha_noi = (
    vnm1[vnm1["adm1_name"] == "Ha Noi"]
    .assign(geometry=lambda d: d.geometry.make_valid())
    .to_crs(CRS_GEO)
    .dissolve()
    .assign(adm1_name="Ha Noi")
)

if len(ha_noi) != 1:
    raise ValueError("Hanoi boundary could not be reduced to a single polygon feature.")

# 3. Create H3 cells covering Hanoi ----
# polygon_to_cells() returns all H3 cell indexes whose centres fall inside the polygon


def to_latlng_poly(geom):
    exterior = [(lat, lng) for lng, lat in geom.exterior.coords]
    holes = [[(lat, lng) for lng, lat in ring.coords] for ring in geom.interiors]
    return h3.LatLngPoly(exterior, *holes)


hanoi_geom = ha_noi.geometry.iloc[0]
polys = hanoi_geom.geoms if hanoi_geom.geom_type == "MultiPolygon" else [hanoi_geom]

h3_ids = set()
for poly in polys:
    h3_ids.update(h3.polygon_to_cells(to_latlng_poly(poly), H3_RES))
h3_ids = sorted(h3_ids)

if len(h3_ids) == 0:
    raise ValueError("No H3 cells were created. Check boundary geometry and H3 resolution.")

# 4. Convert H3 cells to polygons ----
h3_poly = gpd.GeoDataFrame(
    {
        "origin_id": [f"orig_{i + 1}" for i in range(len(h3_ids))],
        "h3_id": h3_ids,
        "h3_res": H3_RES,
    },
    geometry=[
        Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)]) for cell in h3_ids
    ],
    crs=CRS_GEO,
)
h3_poly["geometry"] = h3_poly.geometry.make_valid()

# 5. Create centroids for accessibility origins ----
# Use a projected CRS for centroid calculation, then convert back to WGS84
h3_centroids = h3_poly.copy()
h3_centroids["geometry"] = h3_centroids.to_crs(CRS_PROJ).geometry.centroid.to_crs(CRS_GEO)

# 6. Summary table ----
h3_area = h3_poly.to_crs(CRS_PROJ).geometry.area
h3_summary = pd.DataFrame({
    "city": ["Ha Noi"],
    "h3_res": [H3_RES],
    "n_hex": [len(h3_poly)],
    "mean_hex_area_m2": [h3_area.mean()],
    "median_hex_area_m2": [h3_area.median()],
    "min_hex_area_m2": [h3_area.min()],
    "max_hex_area_m2": [h3_area.max()],
})

# 7. Export outputs ----
OUT_GPKG.parent.mkdir(parents=True, exist_ok=True)
OUT_GPKG.unlink(missing_ok=True)

h3_poly.to_file(OUT_GPKG, layer="h3_origins_polygons", driver="GPKG")
h3_centroids.to_file(OUT_GPKG, layer="h3_origins_centroids", driver="GPKG")
h3_summary.to_csv(OUT_CSV, index=False)

# 8. Visualise Hanoi H3 hexagon grid ----
bb = ha_noi.total_bounds  # [xmin, ymin, xmax, ymax]

h3_poly_plot = h3_poly.copy()
h3_poly_plot["fill_var"] = h3_poly_plot.geometry.centroid.x

fig, ax = plt.subplots(figsize=(10, 9))
ha_noi.plot(ax=ax, facecolor="none", edgecolor="#1a1a2e", linewidth=0.7)
h3_poly_plot.plot(
    ax=ax, column="fill_var", cmap="viridis", edgecolor="#262626",
    alpha=0.85, linewidth=0.12,
)

ax.text(
    bb[2] - 0.02, bb[1] + 0.02, f"n = {len(h3_poly):,} hexagons",
    ha="right", va="bottom", fontsize=9, color="#4d4d4d",
)

ax.set_title("Hanoi \u2014 H3 Resolution 9 Hexagon Grid", fontsize=13, fontweight="bold", color="#1a1a2e")
ax.text(
    0.0, 1.02,
    f"H3 resolution {H3_RES}  |  {len(h3_poly):,} cells  |  CRS: WGS 84 (EPSG:{CRS_GEO})",
    transform=ax.transAxes, fontsize=9, color="#666666",
)

ax.set_xlim(bb[0], bb[2])
ax.set_ylim(bb[1], bb[3])
ax.set_facecolor("#dde3ea")
ax.set_xticks([])
ax.set_yticks([])

fig.savefig(MAP_OUT, dpi=300, bbox_inches="tight", facecolor="white")
plt.show()
