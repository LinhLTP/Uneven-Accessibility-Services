import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path

# 1. Setup ----

# 1.1. Imports

# 1.2. Input files
vnm0_path = "accessibility_hanoi/vnm_admin_boundaries/vnm_admin0.geojson"
vnm1_path = "accessibility_hanoi/vnm_admin_boundaries/vnm_admin1.geojson"

# 1.3. Output paths
output_dir = Path("data/boundaries")
boundary_out = output_dir / "hanoi_boundary.gpkg"

# 2. Read and extract Hanoi boundary ----

# 2.1. Read files
vnm0 = gpd.read_file(vnm0_path)
vnm1 = gpd.read_file(vnm1_path)

# 2.2. Extract Hanoi from ADM1
ha_noi = (
    vnm1[vnm1["adm1_name"] == "Ha Noi"]
    .assign(geometry=lambda d: d.geometry.make_valid())
    .to_crs(4326)
)

# Also transform Vietnam outline for plotting
vnm0 = vnm0.to_crs(4326)

# 2.3. Quick check
print(ha_noi[["adm1_name", "adm1_name1", "adm1_type_en", "adm1_type_vi"]])
print(ha_noi.crs)
print(ha_noi.total_bounds)

# 3. Export boundary ----
output_dir.mkdir(parents=True, exist_ok=True)

ha_noi.to_file(boundary_out, layer="hanoi_boundary", driver="GPKG")

print(f"Saved Hanoi boundary to:\n {boundary_out.resolve()}")

# 4. Maps ----

# 4.1. Map 1: Hanoi only
fig1, ax1 = plt.subplots(figsize=(8, 8))
ha_noi.plot(ax=ax1, facecolor="#cccccc", edgecolor="black", linewidth=0.4)
ax1.set_title("Hanoi administrative boundary", fontsize=13)
ax1.set_xlabel("")
ax1.set_ylabel("")
ax1.set_xticks([])
ax1.set_yticks([])
ax1.grid(True, color="grey", linewidth=0.2, alpha=0.3)
ax1.text(
    0.5, 1.02, "Source: vnm_admin1.geojson",
    transform=ax1.transAxes, ha="center", fontsize=9, color="#666666",
)
plt.show()

# 4.2. Map 2: Vietnam outline with Hanoi highlighted
fig2, ax2 = plt.subplots(figsize=(8, 8))
vnm0.plot(ax=ax2, facecolor="#f2f2f2", edgecolor="#b3b3b3", linewidth=0.2)
ha_noi.plot(ax=ax2, facecolor="red", edgecolor="black", linewidth=0.4)
ax2.set_title("Hanoi's location within Vietnam's administrative boundaries", fontsize=13)
ax2.set_xlabel("")
ax2.set_ylabel("")
ax2.set_xticks([])
ax2.set_yticks([])
ax2.text(
    0.5, 1.02, "Source: vnm_admin0.geojson and vnm_admin1.geojson",
    transform=ax2.transAxes, ha="center", fontsize=9, color="#666666",
)
plt.show()
