from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm, Normalize

# 1. Setup ----

# 1.1. Imports

# 1.2. Plot config ----
CFG = {
    # --- Colour palette ---
    "palette_type": "viridis",       # "viridis" | "distiller"
    "palette_count": "viridis",      # palette for count / density maps
    "palette_ratio": "viridis",      # palette for the ratio map (male per 100 female)
    "palette_dir_count": -1,         # -1 = dark colour = high value (recommended)
    "palette_dir_ratio": 1,
    "palette_na": "#e6e6e6",         # colour for NA / missing cells

    # --- Colour scale transform ---
    "count_trans": "log10",          # "log10" | "sqrt" | "identity"
    "density_trans": "log10",

    # --- Base font ---
    "base_font_size": 11,

    # --- Plot title ---
    "title_size": 12,
    "title_weight": "bold",          # "normal" | "bold"

    # --- Facet strip label ---
    "strip_size": 10,
    "strip_weight": "bold",

    # --- Legend ---
    "legend_position": "bottom",     # "bottom" | "right" | "none"
    "legend_title_size": 10,
    "legend_text_size": 10,

    # --- Boundary line ---
    "boundary_colour": "#404040",
    "boundary_linewidth": 0.25,

    # --- Export ---
    "dpi": 320,
}

# 1.3. Paths
project_dir = Path("data/worldpop_hanoi_2018")
h3_dir = project_dir / "h3_res9"
plot_dir = project_dir / "plots"
plot_dir.mkdir(parents=True, exist_ok=True)

boundary_path = "data/boundaries/hanoi_boundary.gpkg"
boundary_layer = None

# Optional: adjust this bbox for a tighter or different inner-Hanoi view
urban_core_bbox = {"xmin": 105.74, "xmax": 105.93, "ymin": 20.96, "ymax": 21.12}

# 2. Helper functions ----

# 2.1. Colour scale helper
def get_cmap_norm(values, cfg, trans="log10", kind="count"):
    palette = cfg["palette_ratio"] if kind == "ratio" else cfg["palette_count"]
    direction = cfg["palette_dir_ratio"] if kind == "ratio" else cfg["palette_dir_count"]

    cmap_name = palette + ("_r" if direction == -1 else "")
    cmap = plt.get_cmap(cmap_name)
    cmap.set_bad(cfg["palette_na"])

    vals = pd.to_numeric(pd.Series(values), errors="coerce")

    if trans == "log10":
        vals = vals.where(vals > 0)
        norm = LogNorm(vmin=vals.min(), vmax=vals.max())
    elif trans == "sqrt":
        norm = Normalize(vmin=np.sqrt(vals.min()), vmax=np.sqrt(vals.max()))
    else:
        norm = Normalize(vmin=vals.min(), vmax=vals.max())

    return cmap, norm


# 2.2. Map theme helper
def style_map_axes(ax, cfg, title=None, subtitle=None):
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    for spine in ax.spines.values():
        spine.set_visible(False)
    if title:
        ax.set_title(title, fontsize=cfg["title_size"], fontweight=cfg["title_weight"])
    if subtitle:
        ax.text(0.5, 1.01, subtitle, transform=ax.transAxes, ha="center",
                 fontsize=cfg["base_font_size"] - 2, color="#666666")


# 2.3. I/O helpers
def read_sf_layer(path, layer=None):
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf.to_crs(4326)


def sum_existing_cols(data, cols):
    cols = [c for c in cols if c in data.columns]
    if len(cols) == 0:
        return pd.Series(np.nan, index=data.index)
    numeric = data[cols].apply(pd.to_numeric, errors="coerce")
    return numeric.sum(axis=1, skipna=True)


# 2.4. Zoom / save helpers
def apply_zoom(ax, bbox=None):
    if bbox is None:
        return
    ax.set_xlim(bbox["xmin"], bbox["xmax"])
    ax.set_ylim(bbox["ymin"], bbox["ymax"])


def save_plot(fig, filename, dpi=None):
    fig.savefig(plot_dir / filename, dpi=dpi or CFG["dpi"], bbox_inches="tight", facecolor="white")
    plt.close(fig)


# 2.5. Map-building functions
def make_single_map(data, fill_var, title, fill_name, bbox=None, trans="log10", figsize=(8, 7)):
    cmap, norm = get_cmap_norm(data[fill_var], CFG, trans=trans, kind="count")

    fig, ax = plt.subplots(figsize=figsize)
    data.plot(ax=ax, column=fill_var, cmap=cmap, norm=norm, edgecolor="none", missing_kwds={"color": CFG["palette_na"]})
    hanoi_boundary.plot(ax=ax, facecolor="none", edgecolor=CFG["boundary_colour"], linewidth=CFG["boundary_linewidth"])

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    fig.colorbar(sm, ax=ax, label=fill_name, orientation="horizontal", fraction=0.04, pad=0.02)

    style_map_axes(ax, CFG, title=title)
    apply_zoom(ax, bbox)
    return fig


def make_ratio_map(data, fill_var, title, fill_name, bbox=None, figsize=(8, 7)):
    cmap, norm = get_cmap_norm(data[fill_var], CFG, trans="identity", kind="ratio")

    fig, ax = plt.subplots(figsize=figsize)
    data.plot(ax=ax, column=fill_var, cmap=cmap, norm=norm, edgecolor="none", missing_kwds={"color": CFG["palette_na"]})
    hanoi_boundary.plot(ax=ax, facecolor="none", edgecolor=CFG["boundary_colour"], linewidth=CFG["boundary_linewidth"])

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    fig.colorbar(sm, ax=ax, label=fill_name, orientation="horizontal", fraction=0.04, pad=0.02)

    style_map_axes(ax, CFG, title=title)
    apply_zoom(ax, bbox)
    return fig


def make_count_map(data, facet_var, title, subtitle=None, bbox=None, ncol=2, figsize_per_panel=(5, 5)):
    groups = list(data[facet_var].dropna().unique())
    nrow = int(np.ceil(len(groups) / ncol))

    # Shared colour scale across all facets (mirrors ggplot2's default fixed scales)
    cmap, norm = get_cmap_norm(data["population"], CFG, trans="log10", kind="count")

    fig, axes = plt.subplots(nrow, ncol, figsize=(figsize_per_panel[0] * ncol, figsize_per_panel[1] * nrow))
    axes = np.atleast_1d(axes).flatten()

    for ax, grp in zip(axes, groups):
        subset = data[data[facet_var] == grp]
        subset.plot(ax=ax, column="population", cmap=cmap, norm=norm, edgecolor="none",
                     missing_kwds={"color": CFG["palette_na"]})
        hanoi_boundary.plot(ax=ax, facecolor="none", edgecolor=CFG["boundary_colour"], linewidth=CFG["boundary_linewidth"])
        style_map_axes(ax, CFG, title=str(grp))
        apply_zoom(ax, bbox)

    for ax in axes[len(groups):]:
        ax.set_visible(False)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    fig.colorbar(sm, ax=list(axes[: len(groups)]), label="Population\n(count, log scale)",
                  orientation="horizontal", fraction=0.03, pad=0.02)

    fig.suptitle(title, fontsize=CFG["title_size"], fontweight=CFG["title_weight"])
    if subtitle:
        fig.text(0.5, 0.965, subtitle, ha="center", fontsize=CFG["base_font_size"] - 2, color="#666666")

    return fig


# 3. Load and prepare data ----

# 3.1. Read boundary and hex layers
hanoi_boundary = read_sf_layer(boundary_path, boundary_layer)
hex_geom = read_sf_layer(h3_dir / "worldpop_hanoi_h3_res9_geometry.gpkg")
hex_total = read_sf_layer(h3_dir / "worldpop_hanoi_h3_res9_total_pop.gpkg")
hex_age_sex = read_sf_layer(h3_dir / "worldpop_hanoi_h3_res9_age_sex_wide.gpkg")

hex_gdf = (
    hex_geom
    .merge(hex_total.drop(columns="geometry"), on="h3_id", how="left")
    .merge(hex_age_sex.drop(columns="geometry"), on="h3_id", how="left")
)

# 3.2. Derived fields
hex_utm = hex_gdf.to_crs(32648)
hex_gdf["area_km2"] = hex_utm.geometry.area / 1e6
hex_gdf["total_density_km2"] = hex_gdf["total_pop"] / hex_gdf["area_km2"]

male_cols = [c for c in hex_gdf.columns if c.startswith("m_")]
female_cols = [c for c in hex_gdf.columns if c.startswith("f_")]
age_sex_cols = male_cols + female_cols

hex_gdf["total_pop"] = pd.to_numeric(hex_gdf["total_pop"], errors="coerce")
hex_gdf[age_sex_cols] = hex_gdf[age_sex_cols].apply(pd.to_numeric, errors="coerce")

hex_gdf["male_total"] = sum_existing_cols(hex_gdf, male_cols)
hex_gdf["female_total"] = sum_existing_cols(hex_gdf, female_cols)
hex_gdf["male_per_100_female"] = np.where(
    hex_gdf["female_total"] > 0, 100 * hex_gdf["male_total"] / hex_gdf["female_total"], np.nan
)

age_groups = {
    "children_0_14": ["0_12m", "1_4", "5_9", "10_14"],
    "youth_15_24": ["15_19", "20_24"],
    "adults_25_64": ["25_29", "30_34", "35_39", "40_44", "45_49", "50_54", "55_59", "60_64"],
    "older_65_plus": ["65_69", "70_74", "75_79", "80_plus"],
}

for grp, bands in age_groups.items():
    male_grp_cols = [f"m_{b}" for b in bands]
    female_grp_cols = [f"f_{b}" for b in bands]
    hex_gdf[f"{grp}_male"] = sum_existing_cols(hex_gdf, male_grp_cols)
    hex_gdf[f"{grp}_female"] = sum_existing_cols(hex_gdf, female_grp_cols)
    hex_gdf[grp] = sum_existing_cols(hex_gdf, male_grp_cols + female_grp_cols)

# 3.3. Long-format tables for faceted maps
sex_long = hex_gdf[["h3_id", "geometry", "male_total", "female_total"]].melt(
    id_vars=["h3_id", "geometry"], value_vars=["male_total", "female_total"],
    var_name="group", value_name="population",
)
sex_long["group"] = sex_long["group"].map({"male_total": "Male population", "female_total": "Female population"})
sex_long = gpd.GeoDataFrame(sex_long, geometry="geometry", crs=hex_gdf.crs)

age_group_labels = {
    "children_0_14": "Children (0-14)",
    "youth_15_24": "Youth (15-24)",
    "adults_25_64": "Adults (25-64)",
    "older_65_plus": "Older adults (65+)",
}
age_long = hex_gdf[["h3_id", "geometry"] + list(age_groups.keys())].melt(
    id_vars=["h3_id", "geometry"], value_vars=list(age_groups.keys()),
    var_name="group", value_name="population",
)
age_long["group"] = pd.Categorical(
    age_long["group"].map(age_group_labels),
    categories=list(age_group_labels.values()), ordered=True,
)
age_long = gpd.GeoDataFrame(age_long, geometry="geometry", crs=hex_gdf.crs)

age_sex_rows = []
for grp, label in age_group_labels.items():
    age_sex_rows.append(pd.DataFrame({
        "h3_id": hex_gdf["h3_id"], "sex": "Female", "group": label,
        "population": hex_gdf[f"{grp}_female"],
    }))
    age_sex_rows.append(pd.DataFrame({
        "h3_id": hex_gdf["h3_id"], "sex": "Male", "group": label,
        "population": hex_gdf[f"{grp}_male"],
    }))
age_sex_long = pd.concat(age_sex_rows, ignore_index=True).merge(
    hex_gdf[["h3_id", "geometry"]], on="h3_id", how="left"
)
age_sex_long = gpd.GeoDataFrame(age_sex_long, geometry="geometry", crs=hex_gdf.crs)

# 3.4. Summary table export
summary_table = pd.DataFrame({
    "total_pop_sum": [hex_gdf["total_pop"].sum(skipna=True)],
    "male_total_sum": [hex_gdf["male_total"].sum(skipna=True)],
    "female_total_sum": [hex_gdf["female_total"].sum(skipna=True)],
    "children_0_14_sum": [hex_gdf["children_0_14"].sum(skipna=True)],
    "youth_15_24_sum": [hex_gdf["youth_15_24"].sum(skipna=True)],
    "adults_25_64_sum": [hex_gdf["adults_25_64"].sum(skipna=True)],
    "older_65_plus_sum": [hex_gdf["older_65_plus"].sum(skipna=True)],
})
summary_table.to_csv(plot_dir / "worldpop_hanoi_map_summary.csv", index=False)

# 4. Build maps ----

# 4.1. Total population maps
p_total = make_single_map(
    hex_gdf, "total_pop",
    title="Hanoi WorldPop 2018 total population by H3 resolution 9",
    fill_name="Population\n(count, log scale)", trans="log10",
)
p_total_zoom = make_single_map(
    hex_gdf, "total_pop",
    title="Hanoi WorldPop 2018 total population by H3 resolution 9: inner-city zoom",
    fill_name="Population\n(count, log scale)", bbox=urban_core_bbox, trans="log10",
)

# 4.2. Density maps
p_density = make_single_map(
    hex_gdf, "total_density_km2",
    title="Hanoi WorldPop 2018 population density by H3 resolution 9",
    fill_name="Population density\n(per km\u00b2, log scale)", trans="log10",
)
p_density_zoom = make_single_map(
    hex_gdf, "total_density_km2",
    title="Hanoi WorldPop 2018 population density by H3 resolution 9: inner-city zoom",
    fill_name="Population density\n(per km\u00b2, log scale)", bbox=urban_core_bbox, trans="log10",
)

# 4.3. Sex maps
p_sex = make_count_map(
    sex_long, "group",
    title="Hanoi WorldPop 2018 male and female population by H3 resolution 9",
    subtitle="Shared legend across both facets",
)
p_sex_zoom = make_count_map(
    sex_long, "group",
    title="Hanoi WorldPop 2018 male and female population by H3 resolution 9: inner-city zoom",
    subtitle="Shared legend across both facets", bbox=urban_core_bbox,
)

# 4.4. Age maps
p_age = make_count_map(
    age_long, "group",
    title="Hanoi WorldPop 2018 grouped age population by H3 resolution 9",
    subtitle="Age groups are aggregated from WorldPop age-sex bands", ncol=2,
)
p_age_zoom = make_count_map(
    age_long, "group",
    title="Hanoi WorldPop 2018 grouped age population by H3 resolution 9: inner-city zoom",
    subtitle="Age groups are aggregated from WorldPop age-sex bands", bbox=urban_core_bbox, ncol=2,
)

# 4.5. Ratio maps
p_ratio = make_ratio_map(
    hex_gdf, "male_per_100_female",
    title="Hanoi WorldPop 2018 male population per 100 female by H3 resolution 9",
    fill_name="Male per\n100 female",
)
p_ratio_zoom = make_ratio_map(
    hex_gdf, "male_per_100_female",
    title="Hanoi WorldPop 2018 male population per 100 female by H3 resolution 9: inner-city zoom",
    fill_name="Male per\n100 female", bbox=urban_core_bbox,
)

# 4.6. Age-by-sex grid
sex_age_groups = list(age_sex_long.groupby(["sex", "group"], observed=True).groups.keys())
cmap_grid, norm_grid = get_cmap_norm(age_sex_long["population"], CFG, trans="log10", kind="count")

fig_grid, axes_grid = plt.subplots(
    int(np.ceil(len(sex_age_groups) / 2)), 2,
    figsize=(12, 3.5 * int(np.ceil(len(sex_age_groups) / 2))),
)
axes_grid = np.atleast_1d(axes_grid).flatten()

for ax, (sex, grp) in zip(axes_grid, sex_age_groups):
    subset = age_sex_long[(age_sex_long["sex"] == sex) & (age_sex_long["group"] == grp)]
    subset.plot(ax=ax, column="population", cmap=cmap_grid, norm=norm_grid, edgecolor="none",
                 missing_kwds={"color": CFG["palette_na"]})
    hanoi_boundary.plot(ax=ax, facecolor="none", edgecolor="#404040", linewidth=0.2)
    style_map_axes(ax, CFG, title=f"{sex}: {grp}")

for ax in axes_grid[len(sex_age_groups):]:
    ax.set_visible(False)

sm_grid = plt.cm.ScalarMappable(cmap=cmap_grid, norm=norm_grid)
fig_grid.colorbar(sm_grid, ax=list(axes_grid[: len(sex_age_groups)]), label="Population\n(count, log scale)",
                    orientation="horizontal", fraction=0.02, pad=0.02)
p_age_sex_grid = fig_grid

# 5. Save outputs ----
save_plot(p_total, "map_hanoi_h3_total_population.png")
save_plot(p_total_zoom, "map_hanoi_h3_total_population_zoom.png")
save_plot(p_density, "map_hanoi_h3_population_density.png")
save_plot(p_density_zoom, "map_hanoi_h3_population_density_zoom.png")
save_plot(p_sex, "map_hanoi_h3_male_female_population.png")
save_plot(p_sex_zoom, "map_hanoi_h3_male_female_population_zoom.png")
save_plot(p_age, "map_hanoi_h3_grouped_age_population.png")
save_plot(p_age_zoom, "map_hanoi_h3_grouped_age_population_zoom.png")
save_plot(p_ratio, "map_hanoi_h3_male_per_100_female.png")
save_plot(p_ratio_zoom, "map_hanoi_h3_male_per_100_female_zoom.png")
save_plot(p_age_sex_grid, "map_hanoi_h3_age_by_sex_grid.png")
