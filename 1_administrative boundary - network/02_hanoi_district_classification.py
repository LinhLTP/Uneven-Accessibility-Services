import re
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import osmnx as ox
import pandas as pd
import pygadm
from matplotlib.lines import Line2D
from matplotlib_scalebar.scalebar import ScaleBar

# 1. Setup ----

# 1.1. Imports

# 1.2. Output paths
out_png = "accessibility_hanoi/hanoi_district_map_v3.png"

cache_dir = Path("accessibility_hanoi/osm_cache")
cache_dir.mkdir(parents=True, exist_ok=True)

gpkg_rivers = cache_dir / "hanoi_osm_rivers.gpkg"
gpkg_water = cache_dir / "hanoi_osm_water_poly.gpkg"

# 2. Read boundaries ----

# 2.1. Read local GeoJSON boundaries
# -> vnm_admin0 and vnm_admin1 already include Hoang Sa / Truong Sa
# -> use the adm1_name field
print("Reading local GeoJSON boundaries...")

vnm0_inset = gpd.read_file(
    "accessibility_hanoi/vnm_admin_boundaries/vnm_admin0.geojson"
).to_crs(4326)

vnm1_inset = gpd.read_file(
    "accessibility_hanoi/vnm_admin_boundaries/vnm_admin1.geojson"
).to_crs(4326)

# 2.2. Isolate Hanoi
# use adm1_name (field from the HDX/OCHA GeoJSON)
hanoi_prov = vnm1_inset[vnm1_inset["adm1_name"] == "Ha Noi"]

# Districts come from GADM level 2 (the local GeoJSON only has admin1)
print("Downloading GADM level 2 for Hanoi districts...")

vnm2 = pygadm.Items(name="Vietnam", content_level=2).to_crs(4326)

hanoi_districts = vnm2[
    vnm2["NAME_1"].str.contains("H.*N.*i|Ha Noi|Hanoi", case=False, regex=True, na=False)
].copy()
hanoi_districts["geometry"] = hanoi_districts.geometry.make_valid()

print(f"Hanoi districts found: {len(hanoi_districts)}")
print(", ".join(sorted(hanoi_districts["NAME_2"])))

# 3. District classification ----

# 3.1. Classify districts
urban_core_list = [
    "Ba Đình", "Cầu Giấy", "Đống Đa",
    "Hai Bà Trưng", "Hoàn Kiếm", "Thanh Xuân",
]
urban_district_list = [
    "Bắc Từ Liêm", "Hà Đông", "Hoàng Mai",
    "Long Biên", "Nam Từ Liêm", "Tây Hồ",
]
rural_district_list = [
    "Ba Vì", "Chương Mỹ", "Đan Phượng", "Đông Anh",
    "Gia Lâm", "Hoài Đức", "Mê Linh", "Mỹ Đức",
    "Phú Xuyên", "Phúc Thọ", "Quốc Oai", "Sóc Sơn",
    "Thạch Thất", "Thanh Oai", "Thanh Trì",
    "Thường Tín", "Ứng Hòa", "Sơn Tây",
]


def classify_district(name: str) -> str:
    n = name.strip()

    def fuzzy(lst):
        return any(
            re.search(re.escape(x), n, re.IGNORECASE) or re.search(re.escape(n), x, re.IGNORECASE)
            for x in lst
        )

    if fuzzy(urban_core_list):
        return "Urban core"
    if fuzzy(urban_district_list):
        return "Urban district"
    if fuzzy(rural_district_list):
        return "Rural district"
    return "Other"


hanoi_districts["district_type"] = hanoi_districts["NAME_2"].apply(classify_district)
hanoi_districts["district_type"] = hanoi_districts["district_type"].astype(
    pd.CategoricalDtype(
        categories=["Urban core", "Urban district", "Rural district", "Other"], ordered=True
    )
)

print("Classification counts:")
print(hanoi_districts["district_type"].value_counts())

# 3.2. Vietnamese display labels
viet_names = {
    "Ba Dinh": "Ba Đình",
    "Cau Giay": "Cầu Giấy",
    "Dong Da": "Đống Đa",
    "Hai Ba Trung": "Hai Bà Trưng",
    "Hoan Kiem": "Hoàn Kiếm",
    "Thanh Xuan": "Thanh Xuân",
    "Bac Tu Liem": "Bắc Từ Liêm",
    "Ha Dong": "Hà Đông",
    "Hoang Mai": "Hoàng Mai",
    "Long Bien": "Long Biên",
    "Nam Tu Liem": "Nam Từ Liêm",
    "Tay Ho": "Tây Hồ",
    "Ba Vi": "Ba Vì",
    "Chuong My": "Chương Mỹ",
    "Dan Phuong": "Đan Phượng",
    "Dong Anh": "Đông Anh",
    "Gia Lam": "Gia Lâm",
    "Hoai Duc": "Hoài Đức",
    "Me Linh": "Mê Linh",
    "My Duc": "Mỹ Đức",
    "Phu Xuyen": "Phú Xuyên",
    "Phuc Tho": "Phúc Thọ",
    "Quoc Oai": "Quốc Oai",
    "Soc Son": "Sóc Sơn",
    "Son Tay": "Sơn Tây",
    "Thach That": "Thạch Thất",
    "Thanh Oai": "Thanh Oai",
    "Thanh Tri": "Thanh Trì",
    "Thuong Tin": "Thường Tín",
    "Ung Hoa": "Ứng Hòa",
}

hanoi_centroids = hanoi_districts.copy()
hanoi_centroids["geometry"] = hanoi_centroids.geometry.centroid
hanoi_centroids["lon"] = hanoi_centroids.geometry.x
hanoi_centroids["lat"] = hanoi_centroids.geometry.y
hanoi_centroids["label"] = hanoi_centroids["NAME_2"].map(viet_names).fillna(hanoi_centroids["NAME_2"])
hanoi_centroids = hanoi_centroids.drop(columns="geometry")

# 4. OSM water layers ----

# 4.1. Rivers / canals
bb = hanoi_prov.total_bounds  # [xmin, ymin, xmax, ymax]

if gpkg_rivers.exists():
    print(f"Loading rivers from cache: {gpkg_rivers}")
    rivers = gpd.read_file(gpkg_rivers, layer="rivers")
else:
    print("Fetching rivers from OSM (first run, will cache to .gpkg)...")
    rivers = None
    try:
        osm_river = ox.features_from_bbox(
            bbox=(bb[3], bb[1], bb[2], bb[0]),  # north, south, east, west
            tags={"waterway": ["river", "canal"]},
        )
        osm_lines = osm_river[osm_river.geom_type.isin(["LineString", "MultiLineString"])]
        if len(osm_lines) > 0:
            rivers = (
                osm_lines.to_crs(4326)
                .assign(geometry=lambda d: d.geometry.make_valid())
                .pipe(lambda d: gpd.sjoin(d, hanoi_prov[["geometry"]], predicate="intersects"))
                .drop(columns=[c for c in ["index_right"] if c in osm_lines.columns])
            )
    except Exception:
        rivers = None

    if rivers is not None and len(rivers) > 0:
        print(f"Rivers fetched: {len(rivers)}, saving to cache...")
        rivers.to_file(gpkg_rivers, layer="rivers", driver="GPKG")
        print(f"Saved -> {gpkg_rivers}")
    else:
        print("No river data returned from OSM.")

# 4.2. Water polygons (lakes, ponds, reservoirs)
if gpkg_water.exists():
    print(f"Loading water polygons from cache: {gpkg_water}")
    water_poly = gpd.read_file(gpkg_water, layer="water_poly")
else:
    print("Fetching water polygons from OSM (first run, will cache to .gpkg)...")
    water_poly = None
    try:
        osm_water = ox.features_from_bbox(
            bbox=(bb[3], bb[1], bb[2], bb[0]),
            tags={"natural": "water"},
        )
        osm_polys = osm_water[osm_water.geom_type.isin(["Polygon", "MultiPolygon"])]
        if len(osm_polys) > 0:
            water_poly = (
                osm_polys.to_crs(4326)
                .assign(geometry=lambda d: d.geometry.make_valid())
                .pipe(lambda d: gpd.sjoin(d, hanoi_prov[["geometry"]], predicate="intersects"))
                .drop(columns=[c for c in ["index_right"] if c in osm_polys.columns])
            )
    except Exception:
        water_poly = None

    if water_poly is not None and len(water_poly) > 0:
        print(f"Water polygons fetched: {len(water_poly)}, saving to cache...")
        water_poly.to_file(gpkg_water, layer="water_poly", driver="GPKG")
        print(f"Saved -> {gpkg_water}")
    else:
        print("No water polygon data returned from OSM.")

# 5. Map styling ----

# 5.1. Colours
# use border colour to distinguish classes, fill stays uniform
type_border_colours = {
    "Urban core": "#E75480",
    "Urban district": "darkgreen",
    "Rural district": "#525252",
}

type_border_widths = {
    "Urban core": 1.2,
    "Urban district": 0.85,
    "Rural district": 0.45,
}

# 5.2. Tight zoom: clip to Hanoi bbox + 2% padding
hanoi_bbox = hanoi_prov.total_bounds
x_pad = (hanoi_bbox[2] - hanoi_bbox[0]) * 0.02
y_pad = (hanoi_bbox[3] - hanoi_bbox[1]) * 0.02

# 6. Hanoi district map ----

# 6.1. Main map
fig, ax = plt.subplots(figsize=(10, 11))

hanoi_prov.plot(ax=ax, facecolor="#fafafa", edgecolor="none")

for group in ["Rural district", "Urban district", "Urban core"]:
    subset = hanoi_districts[hanoi_districts["district_type"] == group]
    fill = {"Rural district": "#f5f5f5", "Urban district": "#f0f0f0", "Urban core": "#ececec"}[group]
    subset.plot(
        ax=ax,
        facecolor=fill,
        edgecolor=type_border_colours[group],
        linewidth=type_border_widths[group],
    )

if water_poly is not None and len(water_poly) > 0:
    water_poly.plot(ax=ax, facecolor="#AED6E8", edgecolor="#7BB8D0", linewidth=0.10, alpha=0.90)

if rivers is not None and len(rivers) > 0:
    rivers.plot(ax=ax, color="#4A90C4", linewidth=0.55, alpha=0.85)

hanoi_prov.plot(ax=ax, facecolor="none", edgecolor="grey", linewidth=0.55)

for _, row in hanoi_centroids.iterrows():
    ax.annotate(
        row["label"], (row["lon"], row["lat"]),
        fontsize=6.5, color="#262626", ha="center", va="center",
    )

for group, colour in type_border_colours.items():
    subset = hanoi_districts[hanoi_districts["district_type"] == group]
    subset.plot(ax=ax, facecolor="none", edgecolor=colour, linewidth=0, label=group)

ax.set_xlim(hanoi_bbox[0] - x_pad, hanoi_bbox[2] + x_pad)
ax.set_ylim(hanoi_bbox[1] - y_pad, hanoi_bbox[3] + y_pad)
ax.set_axis_off()

# 6.2. Legend
legend_elements = [
    Line2D([0], [0], marker="s", color="w", label="Urban core",
           markerfacecolor="#ececec", markeredgecolor=type_border_colours["Urban core"], markersize=12),
    Line2D([0], [0], marker="s", color="w", label="Urban district",
           markerfacecolor="#f0f0f0", markeredgecolor=type_border_colours["Urban district"], markersize=12),
    Line2D([0], [0], marker="s", color="w", label="Town/Rural district",
           markerfacecolor="#f5f5f5", markeredgecolor=type_border_colours["Rural district"], markersize=12),
    Line2D([0], [0], marker="s", color="w", label="Water/Lake",
           markerfacecolor="#AED6E8", markeredgecolor="#7BB8D0", markersize=12),
]
ax.legend(handles=legend_elements, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8)

# 6.3. Scale bar and north arrow
ax.add_artist(ScaleBar(1, units="deg", dimension="angle", location="lower right", scale_loc="bottom"))

ax.annotate(
    "N", xy=(0.95, 0.92), xytext=(0.95, 0.85), xycoords="axes fraction",
    ha="center", fontsize=8, fontweight="bold",
    arrowprops=dict(facecolor="black", width=3, headwidth=8, headlength=8),
)

# 7. Vietnam inset map ----
# -> islands rendered directly from vnm_admin1.geojson geometry
# -> use the adm1_name field to identify Hanoi
# -> Hoang Sa / Truong Sa labels use real centroid geometry
vnm1_inset = vnm1_inset.copy()
vnm1_inset["is_hanoi"] = vnm1_inset["adm1_name"] == "Ha Noi"
vnm1_inset["is_islands"] = vnm1_inset["adm1_name"].str.contains(
    "Hoang Sa|Truong Sa|Paracel|Spratly", case=False, regex=True, na=False
)

island_features = vnm1_inset[vnm1_inset["is_islands"]]
print(f"Island features found in GeoJSON: {len(island_features)}")
if len(island_features) > 0:
    print(", ".join(island_features["adm1_name"]))

island_labels = island_features.copy()
island_labels["geometry"] = island_labels.geometry.centroid
island_labels["lon"] = island_labels.geometry.x
island_labels["lat"] = island_labels.geometry.y


def island_label(name: str) -> str:
    if re.search("Hoang Sa|Paracel", name, re.IGNORECASE):
        return "Hoàng Sa"
    if re.search("Truong Sa|Spratly", name, re.IGNORECASE):
        return "Trường Sa"
    return name


island_labels["label"] = island_labels["adm1_name"].apply(island_label)
island_labels = island_labels.drop(columns="geometry")

inset_ax = fig.add_axes([0.08, 0.08, 0.27, 0.27])  # left, bottom, width, height (fig fraction)

vnm0_inset.plot(ax=inset_ax, facecolor="#E8EEF4", edgecolor="grey", linewidth=0.3)
vnm1_inset[~vnm1_inset["is_hanoi"]].plot(ax=inset_ax, facecolor="#e6e6e6", edgecolor="grey", linewidth=0.12)
vnm1_inset[vnm1_inset["is_hanoi"]].plot(ax=inset_ax, facecolor="red", edgecolor="grey", linewidth=0.12)

inset_ax.annotate("Hà Nội", xy=(105.85, 21.55), fontsize=5, fontweight="bold", color="#1a1a1a")

for _, row in island_labels.iterrows():
    inset_ax.annotate(
        row["label"], (row["lon"], row["lat"] + 0.8),
        fontsize=4.5, style="italic", color="#333333", ha="center",
    )

inset_ax.set_xlim(102.0, 117.5)
inset_ax.set_ylim(7.0, 23.5)
inset_ax.set_axis_off()
for spine in inset_ax.spines.values():
    spine.set_visible(True)
    spine.set_edgecolor("grey")
    spine.set_linewidth(0.5)

# 8. Save ----
fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
print(f"Saved -> {out_png}")
plt.show()
