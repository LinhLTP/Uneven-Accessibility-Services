# HANOI ACCESSIBILITY PIPELINE

import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import r5py
from shapely.geometry import Point

# 1. Setup ----

# 1.1. Imports

# 1.2. Settings
PROJECT_DIR = Path("accessibility_hanoi/output")

# GTFS settings
GTFS_TXT_DIR = PROJECT_DIR / "hanoi_gtfs_am"
GTFS_ZIP_CLEAN = PROJECT_DIR / "hanoi_gtfs_am_clean.zip"
GTFS_ZIP_OLD = PROJECT_DIR / "hanoi_gtfs_am.zip"

AGENCY_ID = "HN"
AGENCY_NAME = "Hanoi Bus"
AGENCY_URL = "https://example.com"
AGENCY_TIMEZONE = "Asia/Ho_Chi_Minh"

REQUIRED_GTFS = ["agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"]
CALENDAR_CANDIDATES = ["calendar.txt", "calendar_dates.txt"]
OPTIONAL_GTFS = [
    "calendar.txt", "calendar_dates.txt", "shapes.txt", "frequencies.txt",
    "transfers.txt", "feed_info.txt", "pathways.txt", "levels.txt",
    "fare_attributes.txt", "fare_rules.txt",
]

# Input data
POI_PATH = PROJECT_DIR / "hanoi_POI_2018_reconstructed_standardised_2.gpkg"
POI_LAYER = "poi_2018_combined"

H3_CENTROIDS_PATH = PROJECT_DIR / "h3_origins_centroids.gpkg"
H3_CENTROIDS_LAYER = None  # set a layer name if needed, otherwise leave None

# Optional H3 polygon export
EXPORT_H3_POLYGONS = False
H3_POLYGONS_PATH = PROJECT_DIR / "h3_grid.gpkg"
H3_POLYGONS_LAYER = None

# Output
OUT_DIR = PROJECT_DIR / "accessibility_r5r"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# r5py / accessibility settings
DEPARTURE_DATETIME = datetime(2018, 9, 10, 7, 0, 0)

CUTOFFS = [15, 30, 45, 60, 90, 120]
TIME_WINDOW = 180  # minutes: covers departures 07:00-10:00
PERCENTILES = [50]  # median travel time within the window
MAX_WALK_TIME = 15  # minutes per walking leg
MAX_TRIP_DURATION = max(CUTOFFS)
MAX_RIDES = 3
WALK_SPEED = 4.8  # km/h

# 2. Helper functions ----

# 2.1. I/O helpers
def read_vector_any(path, layer=None):
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if ext in {"gpkg", "geojson", "shp", "json", "sqlite"}:
        return gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)

    if ext == "csv":
        df = pd.read_csv(path)
        cols_lower = {c.lower(): c for c in df.columns}
        lon_col = next((cols_lower[c] for c in ["lon", "lng", "longitude", "x"] if c in cols_lower), None)
        lat_col = next((cols_lower[c] for c in ["lat", "latitude", "y"] if c in cols_lower), None)
        if lon_col is None or lat_col is None:
            raise ValueError("CSV input must contain lon/lat columns.")
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs=4326)

    raise ValueError(f"Unsupported file extension: {ext}")


def make_points_wgs84(gdf):
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.make_valid()
    if gdf.crs is None:
        raise ValueError("Input layer has no CRS.")
    gdf = gdf.to_crs(4326)
    geom_types = set(gdf.geom_type.unique())
    if geom_types <= {"Point", "MultiPoint"}:
        return gdf.explode(index_parts=False)
    gdf["geometry"] = gdf.geometry.representative_point()
    return gdf


def normalize_active_geometry(gdf, target_name="geometry"):
    if gdf.geometry.name != target_name:
        gdf = gdf.rename_geometry(target_name)
    return gdf


def choose_id_col(gdf):
    candidates = ["id", "h3_id", "hex_id", "cell_id", "grid_id"]
    hit = next((c for c in candidates if c in gdf.columns), None)
    if hit is not None:
        return hit
    gdf["id"] = range(len(gdf))
    return "id"


# 2.2. POI standardisation
def standardise_poi_type(series):
    x_std = series.astype(str).str.strip().str.lower()
    x_std = x_std.str.replace(r"[&/]", " ", regex=True)
    x_std = x_std.str.replace(r"\s+", " ", regex=True).str.strip()

    mapping = {
        "healthcare": ["healthcare", "hospital", "clinic", "hospital clinic", "health", "medical"],
        "education": ["education", "school university", "school", "university", "college", "kindergarten"],
        "retail_grocery": ["retail grocery", "retail_grocery", "supermarket market", "supermarket",
                            "market", "marketplace", "grocery"],
        "parks_public_open_space": ["parks public open space", "parks_public_open_space", "park",
                                     "public open space", "green space"],
        "sports_facilities": ["sports facilities", "sports_facilities", "sports culture", "sports",
                               "sport", "leisure"],
        "cultural_facilities": ["cultural facilities", "cultural_facilities", "culture", "arts centre",
                                 "cinema", "museum", "community cultural", "community centre", "theatre"],
        "religious_sites": ["religious sites", "religious_sites", "worship", "temple pagoda", "church",
                             "mosque", "pagoda", "temple"],
        "local_government": ["local government", "local_government", "people s committee",
                              "people committee", "ubnd"],
        "food_beverage": ["food beverage", "food_beverage", "restaurant cafe", "restaurant", "cafe",
                           "food", "beverage"],
    }
    value_to_group = {v: k for k, vals in mapping.items() for v in vals}

    def clean_name(x):
        return "".join(c if c.isalnum() else "_" for c in x).strip("_")

    return x_std.map(value_to_group).fillna(x_std.map(clean_name))


def add_opportunity_columns(poi_gdf, poi_type_col=None):
    if poi_type_col is None:
        cols_lower = {c.lower(): c for c in poi_gdf.columns}
        poi_type_col = next((cols_lower[c] for c in ["poi_type", "poi_class", "type"] if c in cols_lower), None)
    if poi_type_col is None:
        raise ValueError("No POI type column found. Expected one of: poi_type, poi_class, type")

    poi_gdf = poi_gdf.copy()
    poi_gdf["poi_group"] = standardise_poi_type(poi_gdf[poi_type_col])

    opp_groups = [
        "healthcare", "education", "retail_grocery", "parks_public_open_space",
        "sports_facilities", "cultural_facilities", "religious_sites",
        "local_government", "food_beverage",
    ]
    for g in opp_groups:
        poi_gdf[g] = (poi_gdf["poi_group"] == g).astype(int)
    return poi_gdf


# 2.3. r5py input prep
def prepare_points(gdf, id_col):
    out = gdf[[id_col, "geometry"]].rename(columns={id_col: "id"}).copy()
    out["id"] = out["id"].astype(str)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=4326)


# 2.4. Safe write helper
def safe_write_gpkg(gdf, dsn, layer):
    gdf.to_file(dsn, layer=layer, driver="GPKG")


# 2.5. Cumulative accessibility (step decay) from a travel-time matrix
def cumulative_accessibility(ttm, destinations_df, opp_cols, cutoffs, percentile):
    merged = ttm.merge(
        destinations_df[["id"] + opp_cols].rename(columns={"id": "to_id"}), on="to_id", how="left"
    )

    rows = []
    for cutoff in cutoffs:
        reachable = merged[merged["travel_time"] <= cutoff]
        agg = reachable.groupby("from_id")[opp_cols].sum()
        agg = agg.reindex(ttm["from_id"].unique(), fill_value=0)
        long = agg.reset_index().melt(id_vars="from_id", var_name="opportunity", value_name="accessibility")
        long["cutoff"] = cutoff
        long["percentile"] = percentile
        rows.append(long)

    out = pd.concat(rows, ignore_index=True).rename(columns={"from_id": "id"})
    return out


# 3. Part 1: clean GTFS & build the r5py network ----

# 3.1. Validate inputs
if not GTFS_TXT_DIR.exists():
    raise FileNotFoundError(f"GTFS_TXT_DIR does not exist: {GTFS_TXT_DIR}")

pbf_files = sorted(PROJECT_DIR.glob("*.pbf"))
if len(pbf_files) == 0:
    raise FileNotFoundError(f"No .osm.pbf file found in PROJECT_DIR: {PROJECT_DIR}")

# 3.2. Stage GTFS files
stage_dir = Path("/tmp/gtfs_clean_stage")
if stage_dir.exists():
    shutil.rmtree(stage_dir)
stage_dir.mkdir(parents=True)

all_txt = sorted(GTFS_TXT_DIR.glob("*.txt"))
keep_files = set(REQUIRED_GTFS) | set(OPTIONAL_GTFS)
keep_present = [f for f in all_txt if f.name in keep_files]

if len(keep_present) == 0:
    raise FileNotFoundError("No GTFS .txt files found in source folder.")

for f in keep_present:
    shutil.copy(f, stage_dir / f.name)

# 3.3. Create agency.txt if missing
agency_path = stage_dir / "agency.txt"
if not agency_path.exists():
    pd.DataFrame([{
        "agency_id": AGENCY_ID, "agency_name": AGENCY_NAME,
        "agency_url": AGENCY_URL, "agency_timezone": AGENCY_TIMEZONE,
    }]).to_csv(agency_path, index=False)

# 3.4. Patch routes.txt: ensure agency_id is not empty
routes_path = stage_dir / "routes.txt"
if not routes_path.exists():
    raise FileNotFoundError("routes.txt is missing.")

routes = pd.read_csv(routes_path)
if "agency_id" in routes.columns:
    routes["agency_id"] = routes["agency_id"].fillna("").astype(str).str.strip()
    routes.loc[routes["agency_id"] == "", "agency_id"] = AGENCY_ID
else:
    routes.insert(1, "agency_id", AGENCY_ID)
routes.to_csv(routes_path, index=False)

# 3.5. Validate staged files & create the clean zip
stage_files = {f.name for f in stage_dir.iterdir()}
missing_required = set(REQUIRED_GTFS) - stage_files
if missing_required:
    raise FileNotFoundError(f"Missing required GTFS file(s): {', '.join(sorted(missing_required))}")
if not (set(CALENDAR_CANDIDATES) & stage_files):
    raise FileNotFoundError("Neither calendar.txt nor calendar_dates.txt found.")

if GTFS_ZIP_CLEAN.exists():
    GTFS_ZIP_CLEAN.unlink()
with zipfile.ZipFile(GTFS_ZIP_CLEAN, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in stage_dir.iterdir():
        zf.write(f, arcname=f.name)

# Rename the old zip to avoid r5py reading multiple feeds
if GTFS_ZIP_OLD.exists():
    old_backup = PROJECT_DIR / "hanoi_gtfs_am_old_backup.zip.bak"
    if old_backup.exists():
        old_backup.unlink()
    GTFS_ZIP_OLD.rename(old_backup)

# Remove a stale MapDB network cache if present
for cache_file in PROJECT_DIR.glob("network.dat*"):
    cache_file.unlink()

# 3.6. Build the r5py transport network
transport_network = r5py.TransportNetwork(str(pbf_files[0]), [str(GTFS_ZIP_CLEAN)])

# 4. Part 2: read origins & POIs ----

# Origins
origins_sf = read_vector_any(H3_CENTROIDS_PATH, H3_CENTROIDS_LAYER)
origins_sf = make_points_wgs84(origins_sf)
origins_sf = normalize_active_geometry(origins_sf)

origin_id_col = choose_id_col(origins_sf)
origins_sf = origins_sf.rename(columns={origin_id_col: "id"})
origins_sf["id"] = origins_sf["id"].astype(str)
origins_sf = origins_sf.drop_duplicates(subset="id")

# POIs
pois_sf = read_vector_any(POI_PATH, POI_LAYER)
pois_sf = make_points_wgs84(pois_sf)
pois_sf = normalize_active_geometry(pois_sf)
pois_sf = add_opportunity_columns(pois_sf)

if "osm_id" not in pois_sf.columns:
    pois_sf["osm_id"] = range(len(pois_sf))

pois_sf = pois_sf.reset_index(drop=True)
pois_sf["dest_id"] = [f"poi_{i + 1}" for i in range(len(pois_sf))]

opp_cols = [
    "healthcare", "education", "retail_grocery", "parks_public_open_space",
    "sports_facilities", "cultural_facilities", "religious_sites",
    "local_government", "food_beverage",
]
opp_cols = [c for c in opp_cols if c in pois_sf.columns]
if len(opp_cols) == 0:
    raise ValueError("No opportunity columns found in POI layer after preparation.")

poi_summary = pois_sf[opp_cols].sum().reset_index()
poi_summary.columns = ["opportunity", "n_pois"]
poi_summary.to_csv(OUT_DIR / "poi_counts_used_in_accessibility.csv", index=False)

# 5. Part 3: run cumulative accessibility ----
origins_r5py = prepare_points(origins_sf, "id")
destinations_r5py = prepare_points(pois_sf, "dest_id")
destinations_r5py = destinations_r5py.merge(
    pois_sf[["dest_id"] + opp_cols].rename(columns={"dest_id": "id"}), on="id"
)

ttm_computer = r5py.TravelTimeMatrixComputer(
    transport_network,
    origins=origins_r5py,
    destinations=destinations_r5py,
    departure=DEPARTURE_DATETIME,
    departure_time_window=timedelta(minutes=TIME_WINDOW),
    percentiles=PERCENTILES,
    transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
    max_time=timedelta(minutes=MAX_TRIP_DURATION),
    max_time_walking=timedelta(minutes=MAX_WALK_TIME),
    speed_walking=WALK_SPEED,
)
ttm = ttm_computer.compute_travel_times()

# ttm has one travel_time column per requested percentile when len(PERCENTILES) > 1;
# with a single percentile it is named "travel_time".
if "travel_time" not in ttm.columns:
    ttm = ttm.rename(columns={f"travel_time_p{PERCENTILES[0]}": "travel_time"})

access_long = cumulative_accessibility(ttm, destinations_r5py, opp_cols, CUTOFFS, PERCENTILES[0])
access_long["id"] = access_long["id"].astype(str)
access_long = access_long.sort_values(["id", "opportunity", "cutoff"])

access_long.to_csv(OUT_DIR / "accessibility_long.csv", index=False)

# 6. Part 4: reshape outputs ----
access_long = access_long.rename(columns={"id": "origin_id"})
access_long["percentile_label"] = "p" + access_long["percentile"].astype(str)
access_long["cutoff_label"] = "cum" + access_long["cutoff"].astype(str) + "m"

if access_long["percentile"].nunique() == 1:
    access_wide = access_long.pivot_table(
        index="origin_id", columns=["opportunity", "cutoff_label"], values="accessibility"
    )
    access_wide.columns = [f"{opp}_{cl}" for opp, cl in access_wide.columns]
else:
    access_wide = access_long.pivot_table(
        index="origin_id", columns=["opportunity", "percentile_label", "cutoff_label"], values="accessibility"
    )
    access_wide.columns = [f"{opp}_{pl}_{cl}" for opp, pl, cl in access_wide.columns]
access_wide = access_wide.reset_index()

access_wide.to_csv(OUT_DIR / "accessibility_wide.csv", index=False)

access_summary = access_long.groupby(["opportunity", "cutoff"])["accessibility"].agg(
    min_access="min", mean_access="mean", median_access="median", max_access="max", sd_access="std"
).reset_index()

access_summary.to_csv(OUT_DIR / "accessibility_summary_by_opportunity_cutoff.csv", index=False)

# 7. Part 5: spatial exports ----
origins_access_sf = origins_sf.merge(access_wide, left_on="id", right_on="origin_id", how="left")

safe_write_gpkg(origins_access_sf, OUT_DIR / "accessibility_outputs.gpkg", "h3_centroids_accessibility")

if EXPORT_H3_POLYGONS:
    h3_polygons_sf = read_vector_any(H3_POLYGONS_PATH, H3_POLYGONS_LAYER)
    h3_polygons_sf = normalize_active_geometry(h3_polygons_sf)

    if "id" not in h3_polygons_sf.columns:
        cols_lower = {c.lower(): c for c in h3_polygons_sf.columns}
        poly_id_col = next((cols_lower[c] for c in ["h3_id", "hex_id", "cell_id", "grid_id"] if c in cols_lower), None)
        if poly_id_col is None:
            raise ValueError("H3 polygon layer must contain id or h3_id/hex_id/cell_id/grid_id.")
        h3_polygons_sf = h3_polygons_sf.rename(columns={poly_id_col: "id"})

    h3_polygons_sf["id"] = h3_polygons_sf["id"].astype(str)
    h3_polygons_sf = h3_polygons_sf.merge(access_wide, left_on="id", right_on="origin_id", how="left")

    safe_write_gpkg(h3_polygons_sf, OUT_DIR / "accessibility_outputs.gpkg", "h3_polygons_accessibility")

# 8. Clean up ----
transport_network.close()
