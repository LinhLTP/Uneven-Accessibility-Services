from pathlib import Path
import zipfile
import geopandas as gpd
import city2graph as c2g

# 1. Setup ----

# 1.1. Imports
# (see above)

# 1.2. Input / output paths
gtfs_dir = Path("accessibility_hanoi/output/hanoi_gtfs_am")
gtfs_zip = gtfs_dir.parent / f"{gtfs_dir.name}.zip"
out_gpkg = gtfs_dir.parent / "hanoi_bus_network_city2graph.gpkg"

# 2. Prepare GTFS zip ----
# City2Graph loads GTFS from a zip file
txt_files = sorted(gtfs_dir.glob("*.txt"))

if not txt_files:
    raise FileNotFoundError(f"No .txt files found in: {gtfs_dir}")

required = {"stops.txt", "stop_times.txt"}
missing = required - {p.name for p in txt_files}
if missing:
    raise FileNotFoundError(f"Missing required files for City2Graph: {sorted(missing)}")

with zipfile.ZipFile(gtfs_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for p in txt_files:
        zf.write(p, arcname=p.name)

print(f"Created GTFS zip: {gtfs_zip}")

# 3. Load GTFS ----
gtfs = c2g.load_gtfs(gtfs_zip)

print("GTFS tables loaded:")
print(sorted(gtfs.keys()))

# 4. Build bus network ----

# 4.1. Build travel summary graph
# Morning time window, based on the service span already checked
nodes_gdf, edges_gdf = c2g.travel_summary_graph(
    gtfs,
    start_time="06:30:00",
    end_time="11:35:00",
    calendar_start="20180101",
    calendar_end="20181231",
    as_nx=False
)

# 4.2. Clean up node / edge tables
# Reset index for easier file writing
nodes_gdf = nodes_gdf.reset_index(drop=True)
edges_gdf = edges_gdf.reset_index()

# Keep only valid geometries
nodes_gdf = nodes_gdf.loc[nodes_gdf.geometry.notna()].copy()
edges_gdf = edges_gdf.loc[edges_gdf.geometry.notna()].copy()

# Ensure CRS is WGS84
if nodes_gdf.crs is None:
    nodes_gdf = nodes_gdf.set_crs(4326, allow_override=True)
else:
    nodes_gdf = nodes_gdf.to_crs(4326)

if edges_gdf.crs is None:
    edges_gdf = edges_gdf.set_crs(4326, allow_override=True)
else:
    edges_gdf = edges_gdf.to_crs(4326)

# 5. Write GeoPackage ----
nodes_gdf.to_file(out_gpkg, layer="bus_nodes", driver="GPKG")
edges_gdf.to_file(out_gpkg, layer="bus_edges", driver="GPKG")

print(f"\nSaved GeoPackage: {out_gpkg}")
print(f"Number of bus nodes: {len(nodes_gdf):,}")
print(f"Number of bus edges: {len(edges_gdf):,}")

print("\nFirst 5 rows of bus edges:")
print(edges_gdf.head())
