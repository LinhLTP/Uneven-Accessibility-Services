import geopandas as gpd
import matplotlib.pyplot as plt

# 1. Setup ----

# 1.1. Imports

# 1.2. Input paths
vnm0_path = "accessibility_hanoi/vnm_admin_boundaries/vnm_admin0.geojson"
vnm1_path = "accessibility_hanoi/vnm_admin_boundaries/vnm_admin1.geojson"

# 2. Read and prepare boundaries ----

# 2.1. Read files
vnm0 = gpd.read_file(vnm0_path)
vnm1 = gpd.read_file(vnm1_path)

# 2.2. Filter Hanoi
ha_noi = vnm1[vnm1["adm1_name"] == "Ha Noi"]

# 2.3. Reproject to WGS84
vnm0 = vnm0.to_crs(4326)
ha_noi = ha_noi.to_crs(4326)

# 3. Maps ----

# 3.1. Map 1: Hanoi only
fig1, ax1 = plt.subplots(figsize=(8, 8))
ha_noi.plot(ax=ax1, facecolor="#cccccc", edgecolor="black", linewidth=0.4)
ax1.set_title("Hanoi administrative boundary", fontsize=13)
ax1.text(
    0.5, 1.02, "Source: vnm_admin1.geojson",
    transform=ax1.transAxes, ha="center", fontsize=9, color="#666666",
)
ax1.set_xticks([])
ax1.set_yticks([])
plt.show()

# 3.2. Map 2: Vietnam outline with Hanoi highlighted
fig2, ax2 = plt.subplots(figsize=(8, 8))
vnm0.plot(ax=ax2, facecolor="#f2f2f2", edgecolor="#b3b3b3", linewidth=0.2)
ha_noi.plot(ax=ax2, facecolor="red", edgecolor="black", linewidth=0.4)
ax2.set_title("Hanoi's location within Vietnam's administrative boundaries", fontsize=13)
ax2.text(
    0.5, 1.02, "Source: vnm_admin0.geojson and vnm_admin1.geojson",
    transform=ax2.transAxes, ha="center", fontsize=9, color="#666666",
)
ax2.set_xticks([])
ax2.set_yticks([])
plt.show()

# 3.3. Map 3: Hanoi only (simplified)
ha_noi = vnm1[vnm1["adm1_name"] == "Ha Noi"].to_crs(4326)

fig3, ax3 = plt.subplots(figsize=(8, 8))
ha_noi.plot(ax=ax3, facecolor="#cccccc", edgecolor="black", linewidth=0.4)
ax3.set_title("Hanoi administrative boundary", fontsize=13)
ax3.set_xticks([])
ax3.set_yticks([])
plt.show()

# Data sources:
# https://data.humdata.org/dataset/cod-ab-vnm
# https://sapnhap.bando.com.vn
