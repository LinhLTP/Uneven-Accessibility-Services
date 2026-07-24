# PLOT ACCESSIBILITY MAPS - relative accessibilit

import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib.colors import Normalize
from matplotlib.ticker import PercentFormatter

# 1. Setup ----

# 1.1. Imports

# 1.2. Plot config
CFG = {
    # --- Paths ---
    "project_dir": Path("accessibility_hanoi"),
    # Wide accessibility CSV from the pipeline (must contain an origin_id / id column)
    "acc_wide_csv": "output/accessibility_r5r/accessibility_wide.csv",
    # WorldPop H3 long CSV - used for population-weighted stats
    "pop_long_csv": "data/worldpop_hanoi_2018/h3_res9/worldpop_hanoi_h3_res9_long.csv",
    # H3 polygon GeoPackage - used for the map
    "h3_gpkg": "h3_origins_centroids.gpkg",
    "h3_poly_layer": "h3_origins_polygons",  # must be polygons, not points
    # H3 centroid GPKG - used for the urban/rural spatial join (point layer)
    "h3_centroid_gpkg": "output/accessibility_r5r/accessibility_outputs.gpkg",
    "h3_centroid_layer": "h3_centroids_accessibility",
    # District boundary for urban/rural classification
    "boundary_district": "data_raw/odm_vietnam_district.geojson",  # local cache
    # Hanoi outer boundary - overlaid on the map
    "boundary_path": "data/boundaries/hanoi_boundary.gpkg",
    "boundary_layer": None,  # None = auto-detect the first layer
    # Output folder (created automatically if missing)
    "map_dir": "output/accessibility_r5r/maps_relative_30min",

    # --- Cutoff - a single cutoff is plotted ---
    "cutoff": 60,  # minutes

    # --- Output flags ---
    "save_individual": True,   # True = save 9 individual JPEGs (one per POI type)
    "save_combined": True,     # True = save one combined 3x3 JPEG

    # --- Figure size & resolution ---
    "fig_w_single": 10, "fig_h_single": 9,
    "fig_w_combined": 26, "fig_h_combined": 30,
    "fig_dpi": 300,

    # --- Font size ---
    "base_size_single": 12,
    "base_size_combined": 30,
    "label_size_single": 20.0,
    "strip_size": 30,

    # --- Legend: "Relative accessibility" ---
    "legend_position": "bottom",       # "right" | "bottom"
    "legend_title_size": 30,
    "legend_text_size": 25,
    "legend_bar_width_cm": 10,
    "legend_bar_height_cm": 0.5,

    # --- Palette ---
    # 1=turbo 2=plasma 3=inferno 4=magma 5=mako 6=rocket 7=viridis 8=cividis
    # 9=YlOrRd 10=YlGnBu 11=Spectral 12=RdYlGn 13=RdYlBu 14=YlGnBu
    "palette_preset": 1,
    "zero_as_white": True,

    # --- Boundary overlay ---
    "boundary_colour": "#4d4d4d",
    "boundary_linewidth": 0.45,

    # --- Basemap: road network + bus stops ---
    "combined_gpkg": "hanoi_combined_networks.gpkg",
    "show_roads": True,
    "road_types": ["motorway", "trunk", "primary", "secondary", "tertiary"],
    "road_colour": "#999999",
    "road_lw": 0.18,
    "road_alpha": 0.45,

    "show_bus_stops": True,
    "bus_stop_colour": "#084594",
    "bus_stop_size": 0.10,
    "bus_stop_alpha": 0.50,
}

# --- POI display labels ---
POI_LABELS = {
    "Healthcare": "healthcare",
    "Education": "education",
    "Retail & Grocery": "retail_grocery",
    "Parks & Public Open Space": "parks_public_open_space",
    "Sports Facilities": "sports_facilities",
    "Cultural Facilities": "cultural_facilities",
    "Religious Sites": "religious_sites",
    "Local Government": "local_government",
    "Food & Beverage": "food_beverage",
}

# --- Urban / rural district lists ---
URBAN_DISTRICTS = [
    "Hoan Kiem", "Ba Dinh", "Dong Da", "Hai Ba Trung", "Thanh Xuan", "Cau Giay",
    "Tay Ho", "Hoang Mai", "Long Bien", "Ha Dong", "Tu Liem", "Bac Tu Liem", "Nam Tu Liem",
]
RURAL_DISTRICTS = [
    "Ba Vi", "Soc Son", "My Duc", "Chuong My", "Dong Anh", "Ung Hoa", "Phu Xuyen",
    "Thach That", "Quoc Oai", "Thuong Tin", "Me Linh", "Thanh Oai", "Son Tay",
    "Phuc Tho", "Gia Lam", "Hoai Duc", "Dan Phuong", "Thanh Tri",
]

# 1.3. Derived paths & constants
PROJECT_DIR = CFG["project_dir"]
MAP_DIR = PROJECT_DIR / CFG["map_dir"]
ACCESS_WIDE_CSV = PROJECT_DIR / CFG["acc_wide_csv"]
POP_LONG_CSV = PROJECT_DIR / CFG["pop_long_csv"]
H3_GPKG = PROJECT_DIR / CFG["h3_gpkg"]
H3_CENTROID_GPKG = PROJECT_DIR / CFG["h3_centroid_gpkg"]
BOUNDARY_PATH = PROJECT_DIR / CFG["boundary_path"]
BOUNDARY_DISTRICT = PROJECT_DIR / CFG["boundary_district"]
ODM_URL = (
    "https://data.opendevelopmentmekong.net/dataset/6f054351-bf2c-422e-8deb-0a511d63a315/"
    "resource/c906af7a-e7a0-4776-95d4-5ee815dba760/download/district.geojson"
)

OPP_GROUPS = list(POI_LABELS.values())
opp_to_label = {v: k for k, v in POI_LABELS.items()}

MAP_DIR.mkdir(parents=True, exist_ok=True)
BOUNDARY_DISTRICT.parent.mkdir(parents=True, exist_ok=True)

# Palette lookup (matplotlib colormap names; mako/rocket fall back to viridis/magma
# since they are seaborn-only palettes with no built-in matplotlib equivalent)
PALETTE_LOOKUP = {
    1: ("turbo", 1), 2: ("plasma", 1), 3: ("inferno", 1), 4: ("magma", 1),
    5: ("mako", 1), 6: ("rocket", 1), 7: ("viridis", 1), 8: ("cividis", 1),
    9: ("YlOrRd", 1), 10: ("YlGnBu", 1), 11: ("Spectral", 1),
    12: ("RdYlGn", -1), 13: ("RdYlBu", 1), 14: ("YlGnBu", 1),
}
_FALLBACK = {"mako": "crest", "rocket": "flare"}
pal_name, pal_dir = PALETTE_LOOKUP[CFG["palette_preset"]]
pal_name = _FALLBACK.get(pal_name, pal_name)

# 2. Helper functions ----

# 2.1. Geometry / name helpers
def normalize_active_geometry(gdf):
    if gdf.geometry.name != "geometry":
        gdf = gdf.rename_geometry("geometry")
    return gdf


def standardise_name(x):
    x = x.astype(str).map(lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode())
    x = x.str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    return x


def extract_cutoff_cols(df, cutoff_min):
    pat = re.compile(rf"^[a-z][a-z0-9_]*_(?:p\d+_)?cum{cutoff_min}m$")
    return [c for c in df.columns if pat.match(c)]


# 2.2. Fill scale / map styling helpers
def get_cmap(zero_as_white=CFG["zero_as_white"]):
    cmap = plt.get_cmap(pal_name + ("_r" if pal_dir == -1 else ""))
    cmap.set_bad("white" if zero_as_white else "#d9d9d9")
    return cmap


def style_map_bare(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    for spine in ax.spines.values():
        spine.set_visible(False)


# 3. Read data ----
access_wide = pd.read_csv(ACCESS_WIDE_CSV)
if "origin_id" not in access_wide.columns and "id" in access_wide.columns:
    access_wide = access_wide.rename(columns={"id": "origin_id"})
if "origin_id" not in access_wide.columns:
    raise ValueError("accessibility_wide.csv must contain 'origin_id' or 'id'.")

h3_poly = gpd.read_file(H3_GPKG, layer=CFG["h3_poly_layer"])
h3_poly = normalize_active_geometry(h3_poly)
if set(h3_poly.geom_type.unique()) == {"Point"}:
    raise ValueError('H3 layer is POINT - set h3_poly_layer = "h3_origins_polygons" in CFG.')

access_wide_str = access_wide.copy()
access_wide_str["origin_id"] = access_wide_str["origin_id"].astype(str)

access_sf = h3_poly.copy()
access_sf["h3_id"] = access_sf["h3_id"].astype(str)
access_sf = access_sf.merge(access_wide_str, left_on="h3_id", right_on="origin_id", how="left")

acc_cols = extract_cutoff_cols(access_sf, CFG["cutoff"])
n_matched = access_sf[acc_cols[0]].notna().sum() if acc_cols else 0
if n_matched == 0:
    raise ValueError("Join produced 0 matches - check origin_id vs h3_id.")

# 4. Pivot to long + compute relative accessibility ----
id_col = next((c for c in ["join_id", "origin_id", "id"] if c in access_sf.columns), None)
if id_col is None:
    raise ValueError("Could not find an ID column (join_id / origin_id / id).")

geom_df = access_sf.rename(columns={id_col: "row_id"}).copy()
geom_df["row_id"] = geom_df["row_id"].astype(str)
geom_df["h3_id"] = geom_df["h3_id"].astype(str)
geom_df = geom_df[["row_id", "h3_id", "geometry"]]

access_long = access_sf.rename(columns={id_col: "row_id"}).copy()
access_long["row_id"] = access_long["row_id"].astype(str)
access_long = access_long[["row_id"] + acc_cols].melt(
    id_vars="row_id", value_vars=acc_cols, var_name="var_name", value_name="accessibility"
)
suffix_pat = re.compile(rf"(_p\d+)?_cum{CFG['cutoff']}m$")
access_long["opportunity"] = access_long["var_name"].apply(lambda v: suffix_pat.sub("", v))
access_long = access_long[access_long["opportunity"].isin(OPP_GROUPS)]

# Total POIs per category = max reachable across all H3 cells
total_poi = access_long.groupby("opportunity")["accessibility"].max().reset_index(name="total")

access_long = access_long.merge(total_poi, on="opportunity", how="left")
access_long["rel_acc"] = np.where(access_long["total"] > 0, access_long["accessibility"] / access_long["total"], 0)
access_long["poi_label"] = access_long["opportunity"].map(opp_to_label)
access_long["display_val"] = access_long["rel_acc"].where(
    ~(CFG["zero_as_white"] & (access_long["rel_acc"] == 0))
)

access_long_sf = access_long.merge(geom_df[["row_id", "geometry"]], on="row_id", how="left")
access_long_sf = gpd.GeoDataFrame(access_long_sf, geometry="geometry", crs=h3_poly.crs)

# 5. Load Hanoi boundary (outer boundary - for map overlay) ----
hanoi_boundary = None
try:
    if not BOUNDARY_PATH.exists():
        b = gpd.read_file(ODM_URL)
        b = normalize_active_geometry(b)
        char_cols = [c for c in b.columns if b[c].dtype == object and c != "geometry"]
        match_col = next(
            (c for c in char_cols if standardise_name(b[c].astype(str)).str.contains("ha noi|hanoi").any()),
            None,
        )
        if match_col is None:
            raise ValueError("Cannot find Hanoi in ODM file.")
        b = b[standardise_name(b[match_col].astype(str)).str.contains("ha noi|hanoi")]
    else:
        layer = CFG["boundary_layer"]
        b = gpd.read_file(BOUNDARY_PATH, layer=layer) if layer else gpd.read_file(BOUNDARY_PATH)
        b = normalize_active_geometry(b)

    hanoi_boundary = gpd.GeoDataFrame(geometry=[b.geometry.union_all()], crs=b.crs).to_crs(access_long_sf.crs)
except Exception:
    hanoi_boundary = None

# 6. Load basemap layers (roads + bus stops) ----
COMBINED_GPKG = PROJECT_DIR / CFG["combined_gpkg"]
roads_major = None
bus_nodes = None

if COMBINED_GPKG.exists():
    if CFG["show_roads"]:
        try:
            roads_major = gpd.read_file(COMBINED_GPKG, layer="osm_roads").to_crs(access_long_sf.crs)
            roads_major = roads_major[roads_major["highway"].isin(CFG["road_types"])]
            roads_major["geometry"] = roads_major.geometry.make_valid()
            if hanoi_boundary is not None:
                roads_major = gpd.clip(roads_major, hanoi_boundary)
        except Exception:
            roads_major = None
    if CFG["show_bus_stops"]:
        try:
            bus_nodes = gpd.read_file(COMBINED_GPKG, layer="bus_nodes").to_crs(access_long_sf.crs)
        except Exception:
            bus_nodes = None

# 7. Urban / rural lookup ----
# Spatial join: H3 centroid point -> district polygon -> urban_rural_group
h3_centroids_sf = gpd.read_file(H3_CENTROID_GPKG, layer=CFG["h3_centroid_layer"])[["id", "geometry"]]
h3_centroids_sf = h3_centroids_sf.rename(columns={"id": "h3_id"})
h3_centroids_sf["h3_id"] = h3_centroids_sf["h3_id"].astype(str)

if not BOUNDARY_DISTRICT.exists():
    with requests.get(ODM_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(BOUNDARY_DISTRICT, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

odm_dist = gpd.read_file(BOUNDARY_DISTRICT)
odm_dist["geometry"] = odm_dist.geometry.make_valid()

hanoi_districts = odm_dist[odm_dist["Province"] == "Ha Noi"].copy()
hanoi_districts["district_std"] = standardise_name(hanoi_districts["District"])
urban_std = set(standardise_name(pd.Series(URBAN_DISTRICTS)))
rural_std = set(standardise_name(pd.Series(RURAL_DISTRICTS)))
hanoi_districts["urban_rural_group"] = np.select(
    [hanoi_districts["district_std"].isin(urban_std), hanoi_districts["district_std"].isin(rural_std)],
    ["Urban", "Rural"], default="Unclassified",
)
hanoi_districts = hanoi_districts.to_crs(h3_centroids_sf.crs)

# Spatial join: H3 centroid -> district (within, falling back to nearest)
within = gpd.sjoin(h3_centroids_sf, hanoi_districts[["urban_rural_group", "geometry"]],
                    predicate="within", how="left")
missing = within["urban_rural_group"].isna()
if missing.any():
    nearest = gpd.sjoin_nearest(h3_centroids_sf[missing], hanoi_districts[["urban_rural_group", "geometry"]])
    within.loc[missing, "urban_rural_group"] = nearest["urban_rural_group"].to_numpy()

urban_rural_lookup = within[["h3_id", "urban_rural_group"]].drop_duplicates("h3_id")

access_long_ur = access_long.merge(geom_df[["row_id", "h3_id"]], on="row_id", how="left")
access_long_ur = access_long_ur.merge(urban_rural_lookup, on="h3_id", how="left")

# 8. Plot function - single POI ----
def plot_one_poi(opp_name):
    dat = access_long_sf[access_long_sf["opportunity"] == opp_name]
    label = dat["poi_label"].iloc[0]
    bounds = dat.total_bounds

    cmap = get_cmap()
    norm = Normalize(vmin=0, vmax=1)

    fig, ax = plt.subplots(figsize=(CFG["fig_w_single"], CFG["fig_h_single"]))
    dat.plot(ax=ax, column="display_val", cmap=cmap, norm=norm, edgecolor="none", missing_kwds={"color": "white"})

    if hanoi_boundary is not None:
        hanoi_boundary.plot(ax=ax, facecolor="none", edgecolor=CFG["boundary_colour"],
                             linewidth=CFG["boundary_linewidth"])
    if roads_major is not None:
        roads_major.plot(ax=ax, color=CFG["road_colour"], linewidth=CFG["road_lw"], alpha=CFG["road_alpha"])
    if bus_nodes is not None:
        bus_nodes.plot(ax=ax, color=CFG["bus_stop_colour"], markersize=CFG["bus_stop_size"], alpha=CFG["bus_stop_alpha"])

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    fig.colorbar(sm, ax=ax, label="Relative accessibility", format=PercentFormatter(xmax=1),
                 orientation="horizontal" if CFG["legend_position"] == "bottom" else "vertical",
                 fraction=0.04, pad=0.02)

    ax.text(bounds[0], bounds[3], label, ha="left", va="top",
            fontsize=CFG["label_size_single"], fontweight="bold", color="#1a1a1a")

    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    style_map_bare(ax)
    return fig


# 9. Save individual maps (9 JPEGs) ----
if CFG["save_individual"]:
    opp_list = [g for g in OPP_GROUPS if g in access_long_sf["opportunity"].unique()]
    for opp in opp_list:
        fig = plot_one_poi(opp)
        fig.savefig(MAP_DIR / f"map_rel30_{opp}.jpeg", dpi=CFG["fig_dpi"], bbox_inches="tight", facecolor="white")
        plt.close(fig)

# 10. Save combined 3x3 map ----
if CFG["save_combined"]:
    dat_all = access_long_sf.copy()
    dat_all["poi_label"] = pd.Categorical(dat_all["poi_label"], categories=list(POI_LABELS.keys()), ordered=True)

    cmap = get_cmap()
    norm = Normalize(vmin=0, vmax=1)

    fig, axes = plt.subplots(3, 3, figsize=(CFG["fig_w_combined"], CFG["fig_h_combined"]))
    axes = axes.flatten()

    for ax, label in zip(axes, POI_LABELS.keys()):
        subset = dat_all[dat_all["poi_label"] == label]
        subset.plot(ax=ax, column="display_val", cmap=cmap, norm=norm, edgecolor="none",
                    missing_kwds={"color": "white"})
        if hanoi_boundary is not None:
            hanoi_boundary.plot(ax=ax, facecolor="none", edgecolor=CFG["boundary_colour"],
                                 linewidth=CFG["boundary_linewidth"] * 0.7)
        if roads_major is not None:
            roads_major.plot(ax=ax, color=CFG["road_colour"], linewidth=CFG["road_lw"] * 0.7, alpha=CFG["road_alpha"])
        if bus_nodes is not None:
            bus_nodes.plot(ax=ax, color=CFG["bus_stop_colour"], markersize=CFG["bus_stop_size"] * 0.7,
                            alpha=CFG["bus_stop_alpha"])
        ax.set_title(label, fontsize=CFG["strip_size"], fontweight="bold", loc="left")
        style_map_bare(ax)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    fig.colorbar(sm, ax=list(axes), label="Relative accessibility", format=PercentFormatter(xmax=1),
                 orientation="horizontal", fraction=0.02, pad=0.02)

    fig.savefig(MAP_DIR / "map_rel30_all_3x3.jpeg", dpi=CFG["fig_dpi"], bbox_inches="tight", facecolor="white")
    plt.close(fig)

# =============================================================================
# The rest of the original R script (Excel workbook with 4 sheets: population-
# weighted stats, unweighted stats, hexagon coverage by Urban/Rural, and a
# multi-cutoff 15/30/60-min coverage summary) was already commented out /
# disabled in the source file, so it has not been translated here. Ask if you
# want that Excel report ported to Python as well (pandas + openpyxl).
# =============================================================================
