# table_SI_1_gtfs_stats.py

import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import pygadm
import rasterio
from rasterio.mask import mask as rio_mask
from shapely.ops import unary_union

# 1. Setup ----

# 1.1. Imports

# 1.2. Config
BASE_DIR = Path("accessibility_hanoi")

CFG = {
    "gtfs_dir": BASE_DIR / "hanoi_gtfs_am_clean",
    "boundary_gpkg": BASE_DIR / "data/boundaries/hanoi_boundary.gpkg",
    "boundary_layer": "hanoi_boundary",
    "poi_gpkg": BASE_DIR / "output/hanoi_POI_2018_reconstructed_standardised_2.gpkg",
    "poi_layer": "poi_2018_combined",
    "crs_proj": 32648,  # UTM zone 48N (metres) - for area & length
    "am_start_hm": "06:30",
    "am_end_hm": "10:00",
    "output_csv": BASE_DIR / "output/hanoi_gtfs_summary_stats.csv",
    # Study area inputs
    "h3_gpkg": BASE_DIR / "output/h3_origins_centroids.gpkg",
    "h3_layer": "h3_origins_polygons",
    "worldpop_h3_gpkg": BASE_DIR / "data/worldpop_hanoi_2018/h3_res9/worldpop_hanoi_h3_res9_total_pop.gpkg",
    "osm_cache_dir": BASE_DIR / "osm_cache",
    "lulc_tif": BASE_DIR / "data/lulc/lulc2018_hanoi_10m.tif",
    # ^ from Land_use_hanoi_1.R: lulc2018_hanoi_10m.tif (already masked to Hanoi)
    # If the file lives elsewhere, update this path
    "c2g_gpkg": BASE_DIR / "output/hanoi_bus_network_city2graph.gpkg",
}

# 2. Boundaries and district zones ----

# 2.1. Load Hanoi boundary
hanoi_boundary = gpd.read_file(CFG["boundary_gpkg"], layer=CFG["boundary_layer"])
hanoi_boundary["geometry"] = hanoi_boundary.geometry.make_valid()
hanoi_boundary = hanoi_boundary.to_crs(CFG["crs_proj"])

hanoi_area_km2 = hanoi_boundary.geometry.area.sum() / 1e6

# 2.2. District classification (from hanoi_district_classification_v4.R)
urban_core_list = ["Ba Đình", "Cầu Giấy", "Đống Đa", "Hai Bà Trưng", "Hoàn Kiếm", "Thanh Xuân"]
urban_district_list = ["Bắc Từ Liêm", "Hà Đông", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Tây Hồ"]
rural_district_list = [
    "Ba Vì", "Chương Mỹ", "Đan Phượng", "Đông Anh", "Gia Lâm", "Hoài Đức", "Mê Linh", "Mỹ Đức",
    "Phú Xuyên", "Phúc Thọ", "Quốc Oai", "Sóc Sơn", "Thạch Thất", "Thanh Oai", "Thanh Trì",
    "Thường Tín", "Ứng Hòa", "Sơn Tây",
]


def classify_district(name):
    n = name.strip()

    def fuzzy(lst):
        return any(
            re.search(re.escape(x), n, re.IGNORECASE) or re.search(re.escape(n), x, re.IGNORECASE)
            for x in lst
        )

    if fuzzy(urban_core_list) or fuzzy(urban_district_list):
        return "Urban"
    if fuzzy(rural_district_list):
        return "Rural"
    return None


vnm2 = pygadm.Items(name="Vietnam", content_level=2).to_crs(CFG["crs_proj"])

hanoi_districts = vnm2[
    vnm2["NAME_1"].str.contains("H.*N.*i|Ha Noi|Hanoi", case=False, regex=True, na=False)
].copy()
hanoi_districts["geometry"] = hanoi_districts.geometry.make_valid()
hanoi_districts["zone"] = hanoi_districts["NAME_2"].apply(classify_district)
hanoi_districts = hanoi_districts[hanoi_districts["zone"].notna()]

# 2.3. Zone geometries (clipped to boundary)
# Clip zone geometries to the Hanoi boundary before computing area
# -> ensures Urban + Rural area sums exactly to the citywide area
urban_geom_raw = unary_union(hanoi_districts.loc[hanoi_districts["zone"] == "Urban", "geometry"])
rural_geom_raw = unary_union(hanoi_districts.loc[hanoi_districts["zone"] == "Rural", "geometry"])

hanoi_union = hanoi_boundary.geometry.union_all()
urban_geom = urban_geom_raw.intersection(hanoi_union)
rural_geom = rural_geom_raw.intersection(hanoi_union)

urban_area_km2 = urban_geom.area / 1e6
rural_area_km2 = rural_geom.area / 1e6

zone_geom = gpd.GeoDataFrame(
    {"zone": ["Urban", "Rural"]}, geometry=[urban_geom, rural_geom], crs=CFG["crs_proj"]
)

# 2.4. Helper: assign_zone()
# st_within() misses units that straddle the Urban/Rural boundary.
# Nearest-centroid is used instead: each unit is assigned to the zone
# with the nearest centroid - this guarantees Urban + Rural = Citywide.
def assign_zone(gdf, zone_gdf):
    centroids = gpd.GeoDataFrame(geometry=gdf.geometry.centroid, crs=gdf.crs)
    nearest = gpd.sjoin_nearest(centroids, zone_gdf[["zone", "geometry"]], how="left")
    return nearest["zone"].to_numpy()


# 3. Study area descriptors ----

# 3.1. Number of districts per zone
n_districts_hanoi = len(hanoi_districts)
n_districts_urban = (hanoi_districts["zone"] == "Urban").sum()
n_districts_rural = (hanoi_districts["zone"] == "Rural").sum()

# 3.2. H3 res9 hexagon counts per zone
import h3
from shapely.geometry import Polygon


def to_latlng_poly(geom):
    exterior = [(lat, lng) for lng, lat in geom.exterior.coords]
    holes = [[(lat, lng) for lng, lat in ring.coords] for ring in geom.interiors]
    return h3.LatLngPoly(exterior, *holes)


try:
    h3_poly = gpd.read_file(CFG["h3_gpkg"], layer=CFG["h3_layer"])
    h3_poly["geometry"] = h3_poly.geometry.make_valid()
    h3_poly = h3_poly.to_crs(CFG["crs_proj"])
except Exception:
    hanoi_wgs = hanoi_boundary.to_crs(4326)
    hanoi_wgs_geom = hanoi_wgs.geometry.union_all()
    polys = hanoi_wgs_geom.geoms if hanoi_wgs_geom.geom_type == "MultiPolygon" else [hanoi_wgs_geom]
    h3_ids = set()
    for poly in polys:
        h3_ids.update(h3.polygon_to_cells(to_latlng_poly(poly), 9))
    h3_poly = gpd.GeoDataFrame(
        {"h3_id": sorted(h3_ids)},
        geometry=[Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in sorted(h3_ids)],
        crs=4326,
    )
    h3_poly["geometry"] = h3_poly.geometry.make_valid()
    h3_poly = h3_poly.to_crs(CFG["crs_proj"])

h3_poly["zone"] = assign_zone(h3_poly, zone_geom)

n_hex_hanoi = len(h3_poly)
n_hex_urban = (h3_poly["zone"] == "Urban").sum()
n_hex_rural = (h3_poly["zone"] == "Rural").sum()

# 3.3. Population from the WorldPop H3 aggregate
# Source: worldpop_02_hanoi_worldpop_to_h3_res9.R
# File  : data/worldpop_hanoi_2018/h3_res9/worldpop_hanoi_h3_res9_total_pop.gpkg
# Column: total_pop (sum of WorldPop 2018 population per H3 res9 hex)
pop_hanoi = pop_urban = pop_rural = np.nan

if CFG["worldpop_h3_gpkg"].exists():
    wp_h3 = gpd.read_file(CFG["worldpop_h3_gpkg"]).to_crs(CFG["crs_proj"])
    wp_h3["zone"] = assign_zone(wp_h3, zone_geom)

    pop_hanoi = wp_h3["total_pop"].sum(skipna=True)
    pop_urban = wp_h3.loc[wp_h3["zone"] == "Urban", "total_pop"].sum(skipna=True)
    pop_rural = wp_h3.loc[wp_h3["zone"] == "Rural", "total_pop"].sum(skipna=True)

# 3.4. Road network density from OSM (cached)
CFG["osm_cache_dir"].mkdir(parents=True, exist_ok=True)
road_cache = CFG["osm_cache_dir"] / "hanoi_osm_roads.gpkg"

if road_cache.exists():
    roads_sf = gpd.read_file(road_cache, layer="roads").to_crs(CFG["crs_proj"])
else:
    bb = hanoi_boundary.to_crs(4326).total_bounds  # xmin, ymin, xmax, ymax
    roads_sf = None
    try:
        osm_roads = ox.features_from_bbox(
            bbox=(bb[3], bb[1], bb[2], bb[0]),
            tags={"highway": [
                "motorway", "trunk", "primary", "secondary", "tertiary",
                "residential", "unclassified", "motorway_link", "trunk_link",
                "primary_link", "secondary_link", "tertiary_link",
            ]},
        )
        osm_lines = osm_roads[osm_roads.geom_type.isin(["LineString", "MultiLineString"])]
        if len(osm_lines) > 0:
            roads_sf = (
                osm_lines.to_crs(CFG["crs_proj"])
                .assign(geometry=lambda d: d.geometry.make_valid())
            )
            roads_sf = gpd.clip(roads_sf, hanoi_boundary)
            roads_sf.to_file(road_cache, layer="roads", driver="GPKG")
    except Exception:
        roads_sf = None


def measure_road_km(roads, clip_geom):
    if roads is None or len(roads) == 0:
        return np.nan
    clipped = gpd.clip(roads, clip_geom)
    if len(clipped) == 0:
        return 0.0
    return clipped.geometry.length.sum() / 1e3


road_hanoi_km = measure_road_km(roads_sf, hanoi_boundary)
road_urban_km = measure_road_km(roads_sf, gpd.GeoSeries([urban_geom], crs=CFG["crs_proj"]))
road_rural_km = measure_road_km(roads_sf, gpd.GeoSeries([rural_geom], crs=CFG["crs_proj"]))

# 4. Load GTFS ----
stops = pd.read_csv(CFG["gtfs_dir"] / "stops.txt")
trips = pd.read_csv(CFG["gtfs_dir"] / "trips.txt")
stop_times = pd.read_csv(CFG["gtfs_dir"] / "stop_times.txt")
try:
    shapes = pd.read_csv(CFG["gtfs_dir"] / "shapes.txt")
except FileNotFoundError:
    shapes = None

try:
    calendar = pd.read_csv(CFG["gtfs_dir"] / "calendar.txt")
except FileNotFoundError:
    calendar = None

# 5. Stops - spatial join with zones ----
stops_sf = stops[stops["stop_lat"].notna() & stops["stop_lon"].notna()].copy()
stops_sf = gpd.GeoDataFrame(
    stops_sf, geometry=gpd.points_from_xy(stops_sf["stop_lon"], stops_sf["stop_lat"]), crs=4326
).to_crs(CFG["crs_proj"])

# Keep only stops within the Hanoi boundary
stops_sf = gpd.sjoin(stops_sf, hanoi_boundary[["geometry"]], predicate="within", how="inner").drop(
    columns="index_right"
)

# Assign zone via nearest centroid - ensures Urban + Rural = Citywide
stops_sf["zone"] = assign_zone(stops_sf, zone_geom)

n_stops_hanoi = len(stops_sf)
n_stops_urban = (stops_sf["zone"] == "Urban").sum()
n_stops_rural = (stops_sf["zone"] == "Rural").sum()

# 6. Network length ----
# Priority order:
#   A. bus_edges from the city2graph GeoPackage <- real geometry from the Python script
#   B. shapes.txt (if present in the GTFS dir)
#   C. Fallback: connect consecutive stops within a trip (straight lines between stops)
# Duplicate segments shared between routes are dissolved (union) before measuring.

# 6.1. Helpers
def measure_km(lines_gdf, clip_geom):
    if lines_gdf is None or len(lines_gdf) == 0:
        return np.nan
    clipped = gpd.clip(lines_gdf, clip_geom)
    if len(clipped) == 0:
        return 0.0
    return clipped.geometry.length.sum() / 1e3


# 6.2. Path A: city2graph bus_edges
def load_c2g_edges(gpkg_path, crs_proj):
    if not gpkg_path.exists():
        return None
    try:
        import fiona
        layers = fiona.listlayers(str(gpkg_path))
    except Exception:
        layers = []
    if "bus_edges" not in layers:
        return None

    edges = gpd.read_file(gpkg_path, layer="bus_edges")
    edges["geometry"] = edges.geometry.make_valid()
    edges = edges.to_crs(crs_proj)
    edges = edges[edges.geom_type.isin(["LineString", "MultiLineString"])]
    if len(edges) == 0:
        return None

    dissolved = edges.geometry.union_all()
    return gpd.GeoDataFrame(geometry=[dissolved], crs=crs_proj)


route_lines = load_c2g_edges(CFG["c2g_gpkg"], CFG["crs_proj"])

if route_lines is not None:
    pass
elif shapes is not None and len(shapes) > 0:
    # 6.3. Path B: shapes.txt
    from shapely.geometry import LineString

    shapes_sorted = shapes.sort_values(["shape_id", "shape_pt_sequence"])
    lines = shapes_sorted.groupby("shape_id").apply(
        lambda d: LineString(zip(d["shape_pt_lon"], d["shape_pt_lat"]))
    )
    route_lines = gpd.GeoDataFrame(geometry=lines.to_numpy(), crs=4326).to_crs(CFG["crs_proj"])
    route_lines = gpd.GeoDataFrame(geometry=[route_lines.geometry.union_all()], crs=CFG["crs_proj"])
else:
    # 6.4. Path C: fallback stop-sequence linestrings
    from shapely.geometry import LineString

    stop_coords = stops[stops["stop_lat"].notna() & stops["stop_lon"].notna()][
        ["stop_id", "stop_lon", "stop_lat"]
    ]
    st_coords = (
        stop_times.merge(stop_coords, on="stop_id", how="left")
        .dropna(subset=["stop_lon", "stop_lat"])
        .sort_values(["trip_id", "stop_sequence"])
    )

    trip_groups = st_coords.groupby("trip_id").filter(lambda d: len(d) >= 2).groupby("trip_id")
    trip_lines = trip_groups.apply(lambda d: LineString(zip(d["stop_lon"], d["stop_lat"])))

    if len(trip_lines) == 0:
        route_lines = None
    else:
        route_lines = gpd.GeoDataFrame(geometry=trip_lines.to_numpy(), crs=4326).to_crs(CFG["crs_proj"])
        route_lines = gpd.GeoDataFrame(geometry=[route_lines.geometry.union_all()], crs=CFG["crs_proj"])

# 6.5. Measure network length by zone
net_hanoi_km = measure_km(route_lines, hanoi_boundary)
net_urban_km = measure_km(route_lines, gpd.GeoSeries([urban_geom], crs=CFG["crs_proj"]))
net_rural_km = measure_km(route_lines, gpd.GeoSeries([rural_geom], crs=CFG["crs_proj"]))

# 7. AM peak departures (6:30-10:00) ----

# GTFS times can exceed 24:00 - parse to decimal minutes manually
def parse_gtfs_min(t):
    m = re.match(r"^(\d+):(\d{2}):(\d{2})", str(t))
    if not m:
        return np.nan
    h, mi, s = (int(x) for x in m.groups())
    return h * 60 + mi + s / 60


am_start_h, am_start_m = (int(x) for x in CFG["am_start_hm"].split(":"))
am_end_h, am_end_m = (int(x) for x in CFG["am_end_hm"].split(":"))
am_start_min = am_start_h * 60 + am_start_m
am_end_min = am_end_h * 60 + am_end_m
am_duration_h = (am_end_min - am_start_min) / 60  # 3.5 hrs

dep_col = "departure_time" if "departure_time" in stop_times.columns else "arrival_time"

st_am = stop_times.copy()
st_am["dep_min"] = st_am[dep_col].apply(parse_gtfs_min)
st_am = st_am[st_am["dep_min"].notna() & (st_am["dep_min"] >= am_start_min) & (st_am["dep_min"] < am_end_min)]

stop_zones = stops_sf[["stop_id", "zone"]]
st_am = st_am.merge(stop_zones, on="stop_id", how="left")


def count_departures(df):
    return df[["trip_id", "stop_id"]].drop_duplicates().shape[0]


dep_hanoi = count_departures(st_am)
dep_urban = count_departures(st_am[st_am["zone"] == "Urban"])
dep_rural = count_departures(st_am[st_am["zone"] == "Rural"])

# 8. Average headway ----
# Average inter-departure gap at each stop, averaged across stops
def compute_headway(df):
    def stop_gap(d):
        d = d.sort_values("dep_min")
        if len(d) < 2:
            return np.nan
        return np.diff(d["dep_min"]).mean()

    hw = df.groupby("stop_id").apply(stop_gap).dropna()
    return hw.mean() if len(hw) > 0 else np.nan


hw_hanoi = compute_headway(st_am)
hw_urban = compute_headway(st_am[st_am["zone"] == "Urban"])
hw_rural = compute_headway(st_am[st_am["zone"] == "Rural"])

# 9. Opportunity density (POI / km2) ----

# 9.1. POIs
poi_sf = gpd.read_file(CFG["poi_gpkg"], layer=CFG["poi_layer"])
poi_sf["geometry"] = poi_sf.geometry.make_valid()
poi_sf = poi_sf.to_crs(CFG["crs_proj"])

poi_sf = gpd.sjoin(poi_sf, hanoi_boundary[["geometry"]], predicate="within", how="inner").drop(
    columns="index_right"
)
poi_sf["zone"] = assign_zone(poi_sf, zone_geom)

n_poi_hanoi = len(poi_sf)
n_poi_urban = (poi_sf["zone"] == "Urban").sum()
n_poi_rural = (poi_sf["zone"] == "Rural").sum()

# 9.2. LULC area by zone (km^2) - from lulc2018_hanoi_10m.tif
# Class lookup - from Land_use_hanoi_1.R
lulc_classes = pd.DataFrame({
    "value": [1, 2, 4, 5, 7, 8, 9, 10, 11],
    "label": ["Water", "Trees", "Flooded veg", "Crops", "Built area", "Bare ground", "Snow/Ice", "Clouds", "Rangeland"],
    "color": ["#1A5BAB", "#358221", "#87D19E", "#FFDB5C", "#ED022A", "#EDE9E4", "#F2FAFF", "#C8C8C8", "#C6AD8D"],
})

lulc_zone_wide = None  # default if the raster is unavailable

if CFG["lulc_tif"].exists():
    def lulc_area_zone(raster_path, mask_gdf, zone_label):
        with rasterio.open(raster_path) as src:
            mask_geom = mask_gdf.to_crs(src.crs).geometry
            out_image, out_transform = rio_mask(src, mask_geom, crop=True)
            pixel_area_km2 = abs(out_transform.a * out_transform.e) / 1e6

        band = out_image[0]
        values, counts = np.unique(band, return_counts=True)

        rows = []
        for value, count in zip(values, counts):
            if value in lulc_classes["value"].to_numpy():
                label = lulc_classes.loc[lulc_classes["value"] == value, "label"].iloc[0]
                rows.append({"zone": zone_label, "value": value, "label": label, "area_km2": count * pixel_area_km2})
        return pd.DataFrame(rows)

    hanoi_sf_4326 = hanoi_boundary.to_crs(4326)
    urban_sf_4326 = gpd.GeoDataFrame(geometry=[urban_geom], crs=CFG["crs_proj"]).to_crs(4326)
    rural_sf_4326 = gpd.GeoDataFrame(geometry=[rural_geom], crs=CFG["crs_proj"]).to_crs(4326)

    lulc_hanoi = lulc_area_zone(CFG["lulc_tif"], hanoi_sf_4326, "Citywide")
    lulc_urban = lulc_area_zone(CFG["lulc_tif"], urban_sf_4326, "Urban")
    lulc_rural = lulc_area_zone(CFG["lulc_tif"], rural_sf_4326, "Rural")

    lulc_long = pd.concat([lulc_hanoi, lulc_urban, lulc_rural], ignore_index=True)

    lulc_zone_wide = (
        lulc_long.pivot_table(index=["value", "label"], columns="zone", values="area_km2", fill_value=0)
        .reset_index()
        .sort_values("value")
    )
    for col in ["Citywide", "Urban", "Rural"]:
        if col not in lulc_zone_wide.columns:
            lulc_zone_wide[col] = 0.0

    lulc_zone_wide["pct_citywide"] = lulc_zone_wide["Citywide"] / lulc_zone_wide["Citywide"].sum() * 100
    lulc_zone_wide["pct_urban"] = lulc_zone_wide["Urban"] / lulc_zone_wide["Urban"].sum() * 100
    lulc_zone_wide["pct_rural"] = lulc_zone_wide["Rural"] / lulc_zone_wide["Rural"].sum() * 100

# 10. Assemble results table ----
def fmt(x, d=1):
    return "\u2014" if pd.isna(x) else f"{round(x, d):.{d}f}"


def fmt0(x):
    return "\u2014" if pd.isna(x) else f"{round(x):,}"


results = pd.DataFrame([
    # --- A. Study Area ---
    ["Study Area", "Number of districts", fmt0(n_districts_hanoi), fmt0(n_districts_urban), fmt0(n_districts_rural)],
    ["Study Area", "Spatial unit: Hexagon res9 (count)", fmt0(n_hex_hanoi), fmt0(n_hex_urban), fmt0(n_hex_rural)],
    ["Study Area", "Area (km2)", fmt(hanoi_area_km2, 1), fmt(urban_area_km2, 1), fmt(rural_area_km2, 1)],
    ["Study Area", "Population", fmt0(pop_hanoi), fmt0(pop_urban), fmt0(pop_rural)],
    ["Study Area", "Population density (pop/km2)",
     fmt(pop_hanoi / hanoi_area_km2, 1), fmt(pop_urban / urban_area_km2, 1), fmt(pop_rural / rural_area_km2, 1)],
    ["Study Area", "Road network density (km/km2)",
     fmt(road_hanoi_km / hanoi_area_km2, 3), fmt(road_urban_km / urban_area_km2, 3), fmt(road_rural_km / rural_area_km2, 3)],

    # --- B. Bus Infrastructure ---
    ["Bus Infrastructure", "Bus stops", fmt0(n_stops_hanoi), fmt0(n_stops_urban), fmt0(n_stops_rural)],
    ["Bus Infrastructure", "Stop density (stops/km2)",
     fmt(n_stops_hanoi / hanoi_area_km2, 2), fmt(n_stops_urban / urban_area_km2, 2), fmt(n_stops_rural / rural_area_km2, 2)],
    ["Bus Infrastructure", "Network length (km)", fmt(net_hanoi_km, 1), fmt(net_urban_km, 1), fmt(net_rural_km, 1)],
    ["Bus Infrastructure", "Network density (km/km2)",
     fmt(net_hanoi_km / hanoi_area_km2, 3), fmt(net_urban_km / urban_area_km2, 3), fmt(net_rural_km / rural_area_km2, 3)],

    # --- C. Bus Service Frequency ---
    ["Service Frequency", "Total departures", fmt0(dep_hanoi), fmt0(dep_urban), fmt0(dep_rural)],
    ["Service Frequency", "Departures per stop",
     fmt(dep_hanoi / n_stops_hanoi, 1), fmt(dep_urban / n_stops_urban, 1), fmt(dep_rural / n_stops_rural, 1)],
    ["Service Frequency", "Departures per stop per hour",
     fmt(dep_hanoi / n_stops_hanoi / am_duration_h, 2),
     fmt(dep_urban / n_stops_urban / am_duration_h, 2),
     fmt(dep_rural / n_stops_rural / am_duration_h, 2)],
    ["Service Frequency", "Average headway (min)", fmt(hw_hanoi, 1), fmt(hw_urban, 1), fmt(hw_rural, 1)],

    # --- D. Opportunity Density ---
    ["Opportunity", "Opportunity density (opp./km2)",
     fmt(n_poi_hanoi / hanoi_area_km2, 2), fmt(n_poi_urban / urban_area_km2, 2), fmt(n_poi_rural / rural_area_km2, 2)],
], columns=["Section", "Metric", "Citywide", "Urban", "Rural"])

# 11. Export ----
CFG["output_csv"].parent.mkdir(parents=True, exist_ok=True)
results.to_csv(CFG["output_csv"], index=False)

if lulc_zone_wide is not None:
    lulc_csv = BASE_DIR / "output/hanoi_lulc_zone_breakdown.csv"
    lulc_zone_wide.to_csv(lulc_csv, index=False)
