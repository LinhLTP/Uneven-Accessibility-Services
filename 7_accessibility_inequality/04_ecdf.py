# ECDF: population-weighted cumulative distribution of accessibility
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

# 1. Setup ----

# 1.1. Imports

# 1.2. Settings
PROJECT_DIR = Path("accessibility_hanoi")
ACC_LONG_CSV = PROJECT_DIR / "output/accessibility_r5r/accessibility_long.csv"
POP_LONG_CSV = PROJECT_DIR / "data/worldpop_hanoi_2018/h3_res9/worldpop_hanoi_h3_res9_long.csv"
OUT_DIR = PROJECT_DIR / "output/accessibility_r5r/ecdf"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CUTOFFS = [15, 30, 45, 60, 90, 120]
FIG_DPI = 300
FIG_W, FIG_H = 8, 6

# POI display labels (snake_case -> Title Case for plotting)
POI_LABELS = {
    "healthcare": "Healthcare",
    "education": "Education",
    "retail_grocery": "Retail & Grocery",
    "parks_public_open_space": "Parks & Public Open Space",
    "sports_facilities": "Sports Facilities",
    "cultural_facilities": "Cultural Facilities",
    "religious_sites": "Religious Sites",
    "local_government": "Local Government",
    "food_beverage": "Food & Beverage",
}

# Cutoff colour palette (colourblind-safe sequential - dark=short, light=long)
CUTOFF_COLOURS = {
    "15 min": "#0B0405", "30 min": "#1B4F72", "45 min": "#1A7A8A",
    "60 min": "#29A89A", "90 min": "#7ED3A8", "120 min": "#C8EFC8",
}

# Wong palette for 9 POI types (colourblind-safe)
WONG_9 = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#000000", "#999999"]
POI_COLOUR_MAP = {label: WONG_9[i] for i, label in enumerate(POI_LABELS.values())}

# 2. Read data ----

# 2.1. Accessibility long
acc = pd.read_csv(ACC_LONG_CSV).rename(columns={"id": "h3_id"})
acc["h3_id"] = acc["h3_id"].astype(str)
acc["cutoff_label"] = pd.Categorical(
    acc["cutoff"].astype(str) + " min", categories=[f"{c} min" for c in CUTOFFS], ordered=True
)
acc = acc[acc["cutoff"].isin(CUTOFFS)]

# 2.2. Population long
pop = pd.read_csv(POP_LONG_CSV)
pop = pop[pop["variable"] == "total_pop"][["h3_id", "population"]].rename(columns={"population": "pop"})
pop["h3_id"] = pop["h3_id"].astype(str)
pop["pop"] = pop["pop"].clip(lower=0)

# 3. Join accessibility + population ----
dat = acc.merge(pop, on="h3_id", how="left")
dat["pop"] = dat["pop"].fillna(0)

# 4. Weighted ECDF function ----
def weighted_ecdf_df(x_vals, weights, n_points=500):
    x_vals = np.asarray(x_vals, dtype=float)
    weights = np.asarray(weights, dtype=float)
    keep = ~np.isnan(x_vals) & ~np.isnan(weights) & (weights > 0)
    x_vals, weights = x_vals[keep], weights[keep]

    if len(x_vals) == 0:
        return pd.DataFrame({"x": [np.nan], "ecdf_val": [np.nan]})

    total_w = weights.sum()
    x_sorted = np.unique(x_vals)
    ecdf_vals = np.array([weights[x_vals <= v].sum() / total_w for v in x_sorted])

    x_pre = x_sorted[0] - 1
    return pd.DataFrame({"x": np.concatenate([[x_pre], x_sorted]), "ecdf_val": np.concatenate([[0], ecdf_vals])})


# 5. Compute ECDF per POI x cutoff ----
poi_types = sorted(dat["opportunity"].unique())

ecdf_rows = []
for poi in poi_types:
    for co in CUTOFFS:
        sub = dat[(dat["opportunity"] == poi) & (dat["cutoff"] == co)]
        ecdf_df = weighted_ecdf_df(sub["accessibility"], sub["pop"])
        ecdf_df["opportunity"] = poi
        ecdf_df["cutoff"] = co
        ecdf_df["cutoff_label"] = f"{co} min"
        ecdf_rows.append(ecdf_df)
ecdf_all = pd.concat(ecdf_rows, ignore_index=True)
ecdf_all["cutoff_label"] = pd.Categorical(
    ecdf_all["cutoff_label"], categories=[f"{c} min" for c in CUTOFFS], ordered=True
)

# 6. Plot helpers ----
x_max_by_poi = dat.groupby("opportunity")["accessibility"].max()


def make_ecdf_plot(poi_name):
    poi_data = ecdf_all[ecdf_all["opportunity"] == poi_name]
    x_max = x_max_by_poi.get(poi_name, np.nan)
    if pd.isna(x_max) or x_max == 0:
        x_max = 10

    display_label = POI_LABELS.get(poi_name, poi_name.replace("_", " ").title())

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    for cutoff_label in [f"{c} min" for c in CUTOFFS]:
        line = poi_data[poi_data["cutoff_label"] == cutoff_label].sort_values("x")
        if len(line) == 0:
            continue
        ax.step(line["x"], line["ecdf_val"], where="post", linewidth=0.85,
                color=CUTOFF_COLOURS[cutoff_label], label=cutoff_label)

    for y in (0.25, 0.5, 0.75):
        ax.axhline(y, linestyle=":", color="#b3b3b3", linewidth=0.4)

    ax.set_xlim(0, x_max * 1.02)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Number of opportunities reachable")
    ax.set_ylabel("Cumulative share of population")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.set_title(f"Population-weighted ECDF \u2014 {display_label}", fontsize=13, fontweight="bold")
    ax.text(0, 1.06, "Hanoi 2018 \u00b7 Walk + Transit \u00b7 Morning peak \u00b7 H3 res-9",
            transform=ax.transAxes, fontsize=10, color="#666666")
    ax.legend(title="Travel-time\ncutoff", loc="lower right", fontsize=8)
    ax.grid(True, color="#ececec", linewidth=0.4)
    fig.text(0.02, 0.01,
             "Each line = one travel-time cutoff. X-axis: cumulative opportunities reachable.\n"
             "Population weights from WorldPop 2018 (100m grid -> H3 res-9).",
             fontsize=8, color="#8c8c8c")
    return fig


# 7. Save individual ECDF plots ----
for poi in poi_types:
    fig = make_ecdf_plot(poi)
    fname = "ecdf_" + re.sub(r"[^a-z0-9]+", "_", poi.lower()) + ".jpeg"
    fig.savefig(OUT_DIR / fname, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)

# 8. Save combined facet ECDF plot ----
ecdf_all_facet = ecdf_all.copy()
ecdf_all_facet["poi_label"] = pd.Categorical(
    ecdf_all_facet["opportunity"].map(POI_LABELS), categories=list(POI_LABELS.values()), ordered=True
)

fig, axes = plt.subplots(3, 3, figsize=(15, 13))
axes = axes.flatten()
for ax, label in zip(axes, POI_LABELS.values()):
    subset = ecdf_all_facet[ecdf_all_facet["poi_label"] == label]
    for cutoff_label in [f"{c} min" for c in CUTOFFS]:
        line = subset[subset["cutoff_label"] == cutoff_label].sort_values("x")
        if len(line) == 0:
            continue
        ax.step(line["x"], line["ecdf_val"], where="post", linewidth=0.7,
                color=CUTOFF_COLOURS[cutoff_label], label=cutoff_label)
    for y in (0.25, 0.5, 0.75):
        ax.axhline(y, linestyle=":", color="#bfbfbf", linewidth=0.3)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.set_title(label, fontsize=8.5, fontweight="bold")
    ax.grid(True, color="#ececec", linewidth=0.3)

handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, title="Travel-time\ncutoff", loc="center right", fontsize=8)
fig.suptitle("Population-weighted ECDF of cumulative accessibility \u2014 Hanoi 2018", fontsize=12, fontweight="bold")
fig.text(0.5, 0.965, "Walk + Transit \u00b7 Morning peak \u00b7 H3 res-9 \u00b7 WorldPop 2018 weights",
         ha="center", fontsize=9, color="#666666")
fig.text(0.02, 0.01, "Each line = one travel-time cutoff. X-axis free-scaled per POI type.",
         fontsize=7.5, color="#8c8c8c")
fig.savefig(OUT_DIR / "ecdf_all_poi.jpeg", dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
plt.close(fig)

# 9. Summary table: population share with zero accessibility ----
dat_valid = dat[dat["accessibility"].notna()]
zero_share = (
    dat_valid.groupby(["opportunity", "cutoff"])
    .apply(lambda g: pd.Series({
        "total_pop": g["pop"].sum(),
        "pop_zero_acc": g.loc[g["accessibility"] == 0, "pop"].sum(),
        "median_acc": np.average(g["accessibility"], weights=g["pop"] + 1e-9),
    }))
    .reset_index()
)
zero_share["pct_zero"] = (100 * zero_share["pop_zero_acc"] / zero_share["total_pop"]).round(1)
zero_share = zero_share.sort_values(["opportunity", "cutoff"])
zero_share.to_csv(OUT_DIR / "ecdf_zero_access_summary.csv", index=False)

# 10. Save cutoff-facet POI-line ECDF plot ----
ecdf_cutoff_facet = ecdf_all.copy()
ecdf_cutoff_facet["poi_label"] = pd.Categorical(
    ecdf_cutoff_facet["opportunity"].map(POI_LABELS), categories=list(POI_LABELS.values()), ordered=True
)

fig, axes = plt.subplots(2, 3, figsize=(14, 9))
axes = axes.flatten()
for ax, cutoff_label in zip(axes, [f"{c} min" for c in CUTOFFS]):
    subset = ecdf_cutoff_facet[ecdf_cutoff_facet["cutoff_label"] == cutoff_label]
    for label in POI_LABELS.values():
        line = subset[subset["poi_label"] == label].sort_values("x")
        if len(line) == 0:
            continue
        ax.step(line["x"], line["ecdf_val"], where="post", linewidth=0.75,
                color=POI_COLOUR_MAP[label], label=label)
    for y in (0.25, 0.5, 0.75):
        ax.axhline(y, linestyle=":", color="#b8b8b8", linewidth=0.3)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.set_title(cutoff_label, fontsize=10, fontweight="bold")
    ax.grid(True, color="#ececec", linewidth=0.35)

for ax in axes[len(CUTOFFS):]:
    ax.set_visible(False)

handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, title="POI type", loc="center right", fontsize=8.5)
fig.suptitle("Population-weighted ECDF by travel-time cutoff \u2014 Hanoi 2018", fontsize=13, fontweight="bold")
fig.text(0.5, 0.965, "Walk + Transit \u00b7 Morning peak \u00b7 H3 res-9 \u00b7 WorldPop 2018 weights",
         ha="center", fontsize=9.5, color="#666666")
fig.text(0.02, 0.01, "Each line = one POI type. X-axis free-scaled per panel.", fontsize=8, color="#8c8c8c")
fig.savefig(OUT_DIR / "ecdf_by_cutoff_poi_lines.jpeg", dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
plt.close(fig)
