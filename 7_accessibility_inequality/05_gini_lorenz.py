import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 1. Setup ----

# 1.1. Imports
# (see above)

# 1.2. Settings
PROJECT_DIR = Path("accessibility_hanoi")

pop_path = PROJECT_DIR / "data/worldpop_hanoi_2018/h3_res9/worldpop_hanoi_h3_res9_long.csv"
acc_path = PROJECT_DIR / "output/accessibility_r5r/accessibility_wide.csv"
h3_gpkg = PROJECT_DIR / "h3_origins_centroids.gpkg"
h3_layer = "h3_origins_polygons"
out_dir = PROJECT_DIR / "output/equity/horizontal_equity"
out_dir.mkdir(parents=True, exist_ok=True)

# 2. Read data ----
pop_df = pd.read_csv(pop_path, encoding="utf-8")
acc_wide = pd.read_csv(acc_path)

# acc_wide has origin_id (H3 cell ID) + accessibility columns
if "origin_id" in acc_wide.columns and "h3_id" not in acc_wide.columns:
    acc_wide = acc_wide.rename(columns={"origin_id": "h3_id"})

missing_pop = {"h3_id", "population"} - set(pop_df.columns)
if missing_pop:
    raise ValueError(f"Population file missing columns: {', '.join(missing_pop)}")
if "h3_id" not in acc_wide.columns:
    raise ValueError("Accessibility file missing 'h3_id' or 'origin_id'.")

# Aggregate total population by H3
pop_total = pop_df.groupby("h3_id")["population"].sum().reset_index()
pop_total["population"] = pop_total["population"].fillna(0)

# Convert accessibility wide to long
# Column format: <opportunity>_cum<N>m e.g. hospital_cum30m
acc_cols = [c for c in acc_wide.columns if re.match(r"^[a-z][a-z0-9_]*_cum\d+m$", c)]

acc_long = acc_wide[["h3_id"] + acc_cols].melt(
    id_vars="h3_id", value_vars=acc_cols, var_name="metric", value_name="accessibility"
)
acc_long["opportunity"] = acc_long["metric"].str.replace(r"_cum\d+m$", "", regex=True)
acc_long["cutoff_num"] = acc_long["metric"].str.extract(r"cum(\d+)").astype(int)
acc_long["cutoff"] = acc_long["cutoff_num"].astype(str) + " min"
acc_long = acc_long[["h3_id", "opportunity", "cutoff_num", "cutoff", "accessibility"]]

# Join accessibility with population
equity_df = acc_long.merge(pop_total, on="h3_id", how="left")
equity_df["population"] = equity_df["population"].fillna(0)
equity_df["accessibility"] = equity_df["accessibility"].fillna(0)
equity_df = equity_df.dropna(subset=["h3_id", "opportunity", "cutoff_num"])

# 3. Weighted Lorenz curve and weighted Gini ----
def compute_weighted_lorenz_gini(x, w):
    x = np.asarray(x, dtype=float)
    w = np.asarray(w, dtype=float)
    valid = ~np.isnan(x) & ~np.isnan(w)
    x, w = x[valid], w[valid]
    x = np.clip(x, 0, None)
    w = np.clip(w, 0, None)

    if len(x) == 0 or w.sum() == 0:
        return {"gini": np.nan, "lorenz": pd.DataFrame({"cum_pop_share": [0, 1], "cum_access_share": [0, 1]})}

    order = np.argsort(x)
    x, w = x[order], w[order]

    wx = w * x
    total_w, total_wx = w.sum(), wx.sum()

    if total_wx == 0:
        return {"gini": 0.0, "lorenz": pd.DataFrame({"cum_pop_share": [0, 1], "cum_access_share": [0, 0]})}

    cum_w = np.cumsum(w)
    cum_wx = np.cumsum(wx)

    lorenz_df = pd.DataFrame({
        "cum_pop_share": np.concatenate([[0], cum_w / total_w]),
        "cum_access_share": np.concatenate([[0], cum_wx / total_wx]),
    })

    area = np.sum(
        (lorenz_df["cum_access_share"].to_numpy()[:-1] + lorenz_df["cum_access_share"].to_numpy()[1:])
        * np.diff(lorenz_df["cum_pop_share"]) / 2
    )
    gini = 1 - 2 * area

    return {"gini": gini, "lorenz": lorenz_df}


# 4. Compute Gini and Lorenz by opportunity and cutoff ----
group_keys = equity_df[["opportunity", "cutoff_num", "cutoff"]].drop_duplicates().sort_values(
    ["opportunity", "cutoff_num"]
)

gini_results, lorenz_results = [], []
for _, row in group_keys.iterrows():
    dat_i = equity_df[(equity_df["opportunity"] == row["opportunity"]) & (equity_df["cutoff_num"] == row["cutoff_num"])]
    res_i = compute_weighted_lorenz_gini(dat_i["accessibility"], dat_i["population"])

    gini_results.append({
        "opportunity": row["opportunity"], "cutoff_num": row["cutoff_num"], "cutoff": row["cutoff"],
        "weighted_gini": res_i["gini"], "n_h3": len(dat_i),
        "total_population": dat_i["population"].sum(skipna=True),
        "total_accessibility": (dat_i["accessibility"] * dat_i["population"]).sum(skipna=True),
    })

    lorenz_i = res_i["lorenz"].copy()
    lorenz_i["opportunity"] = row["opportunity"]
    lorenz_i["cutoff_num"] = row["cutoff_num"]
    lorenz_i["cutoff"] = row["cutoff"]
    lorenz_results.append(lorenz_i)

gini_long = pd.DataFrame(gini_results).sort_values(["opportunity", "cutoff_num"])
lorenz_long = pd.concat(lorenz_results, ignore_index=True).sort_values(["opportunity", "cutoff_num", "cum_pop_share"])

# Wide Gini table
gini_wide = gini_long.pivot(index="opportunity", columns="cutoff", values="weighted_gini").reset_index()
gini_wide = gini_wide.sort_values("opportunity")

# 5. Labels ----
opportunity_labels = {
    "healthcare": "Healthcare", "education": "Education", "retail_grocery": "Retail / Grocery",
    "parks_public_open_space": "Parks & Public Open Space", "sports_facilities": "Sports Facilities",
    "cultural_facilities": "Cultural Facilities", "religious_sites": "Religious Sites",
    "local_government": "Local Government", "food_beverage": "Food & Beverage",
}
cutoff_order = ["15 min", "30 min", "45 min", "60 min", "90 min", "120 min"]

for df in (gini_long, lorenz_long):
    df["opportunity_label"] = df["opportunity"].map(opportunity_labels).fillna(
        df["opportunity"].str.replace("_", " ").str.title()
    )
    df["cutoff"] = pd.Categorical(df["cutoff"], categories=cutoff_order, ordered=True)

gini_wide["opportunity"] = gini_wide["opportunity"].map(opportunity_labels).fillna(
    gini_wide["opportunity"].str.replace("_", " ").str.title()
)

# 6. Save CSV outputs ----
gini_long.to_csv(out_dir / "horizontal_equity_gini_long.csv", index=False, encoding="utf-8")
gini_wide.to_csv(out_dir / "horizontal_equity_gini_wide.csv", index=False, encoding="utf-8")
lorenz_long.to_csv(out_dir / "horizontal_equity_lorenz_points.csv", index=False, encoding="utf-8")

# 7. Export Excel workbook ----
with pd.ExcelWriter(out_dir / "horizontal_equity_gini.xlsx", engine="openpyxl") as writer:
    gini_long.to_excel(writer, sheet_name="gini_long", index=False)
    gini_wide.to_excel(writer, sheet_name="gini_wide", index=False)
    lorenz_long.to_excel(writer, sheet_name="lorenz_points", index=False)

    from openpyxl.styles import Alignment, Border, Font, Side
    bold_bottom = Border(bottom=Side(style="thin"))
    for sheet_name in ["gini_long", "gini_wide", "lorenz_points"]:
        ws = writer.sheets[sheet_name]
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
            cell.border = bold_bottom
        for col_cells in ws.columns:
            length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 10), 50)

# 8. Heatmap plot ----
heatmap_data = gini_long.pivot(index="opportunity_label", columns="cutoff", values="weighted_gini")
heatmap_data = heatmap_data.reindex(columns=cutoff_order)

fig, ax = plt.subplots(figsize=(13, 6))
im = ax.imshow(heatmap_data.to_numpy(), cmap="cividis_r", vmin=0, vmax=1, aspect="auto")
ax.set_xticks(range(len(heatmap_data.columns)))
ax.set_xticklabels(heatmap_data.columns, fontweight="bold")
ax.set_yticks(range(len(heatmap_data.index)))
ax.set_yticklabels(heatmap_data.index, fontweight="bold")
for i in range(heatmap_data.shape[0]):
    for j in range(heatmap_data.shape[1]):
        val = heatmap_data.iloc[i, j]
        if pd.notna(val):
            ax.text(j, i, f"{val:.3f}", ha="center", va="center", fontsize=9.5)
fig.colorbar(im, ax=ax, label="Gini")
ax.set_title("Population-weighted Gini coefficient by opportunity and travel-time cutoff \u2014 Hanoi 2018")
ax.set_xlabel("Travel-time cutoff", fontweight="bold")
ax.set_ylabel("Opportunity type", fontweight="bold")
fig.savefig(out_dir / "horizontal_equity_gini_heatmap.jpeg", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)

# 9. Lorenz plot (with per-panel Gini annotation) ----
opp_labels_order = [opportunity_labels.get(o, o) for o in gini_long["opportunity"].unique()]
gini_labels = gini_long.assign(label=lambda d: d["weighted_gini"].apply(lambda v: f"Gini = {v:.3f}"))

fig, axes = plt.subplots(
    len(opp_labels_order), len(cutoff_order), figsize=(18, 14), sharex=True, sharey=True
)
for i, opp_label in enumerate(opp_labels_order):
    for j, cutoff in enumerate(cutoff_order):
        ax = axes[i, j]
        line = lorenz_long[(lorenz_long["opportunity_label"] == opp_label) & (lorenz_long["cutoff"] == cutoff)]
        ax.plot([0, 1], [0, 1], linestyle="--", linewidth=0.5, color="#808080")
        ax.plot(line["cum_pop_share"], line["cum_access_share"], linewidth=0.9, color="#1a1a1a")

        gl = gini_labels[(gini_labels["opportunity_label"] == opp_label) & (gini_labels["cutoff"] == cutoff)]
        if len(gl) > 0:
            ax.text(0.03, 0.97, gl["label"].iloc[0], transform=ax.transAxes, ha="left", va="top",
                    fontsize=8, fontweight="bold")

        ax.set_aspect("equal")
        if i == 0:
            ax.set_title(cutoff, fontweight="bold")
        if j == 0:
            ax.set_ylabel(opp_label, fontweight="bold", fontsize=9)

fig.suptitle("Population-weighted Lorenz curves of accessibility", fontsize=14)
fig.text(0.5, 0.005, "Cumulative share of population", ha="center")
fig.text(0.005, 0.5, "Cumulative share of accessibility", va="center", rotation="vertical")
fig.savefig(out_dir / "horizontal_equity_lorenz_curves.jpeg", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)
