from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import momepy
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib_scalebar.scalebar import ScaleBar
from shapely.geometry import LineString, Point

# 1. Setup ----

# 1.1. Imports
# (see above)

# 1.2. Paths
combined_gpkg = "accessibility_hanoi/hanoi_combined_networks.gpkg"
out_city_png = "accessibility_hanoi/hanoi_bus_network_citywide_v5.png"
out_core_png = "accessibility_hanoi/hanoi_bus_network_core_v5.png"
out_panel_png = "accessibility_hanoi/hanoi_bus_network_panel_v5.png"

cache_dir = Path("accessibility_hanoi/osm_cache")
cache_dir.mkdir(parents=True, exist_ok=True)
gpkg_rivers = cache_dir / "hanoi_osm_rivers.gpkg"
gpkg_water = cache_dir / "hanoi_osm_water_poly.gpkg"

# 2. Read and reproject data ----
hanoi = gpd.read_file(combined_gpkg, layer="hanoi_boundary")
roads = gpd.read_file(combined_gpkg, layer="osm_roads")
bus_edges = gpd.read_file(combined_gpkg, layer="bus_edges")
bus_nodes = gpd.read_file(combined_gpkg, layer="bus_nodes")

target_crs = 32648
hanoi = hanoi.to_crs(target_crs)
roads = roads.to_crs(target_crs)
bus_edges = bus_edges.to_crs(target_crs)
bus_nodes = bus_nodes.to_crs(target_crs)

# 3. OSM water layers ----
hanoi_4326 = hanoi.to_crs(4326)
bb = hanoi_4326.total_bounds  # [xmin, ymin, xmax, ymax]

# 3.1. Rivers / canals
if gpkg_rivers.exists():
    print("Loading rivers from cache...")
    rivers = gpd.read_file(gpkg_rivers, layer="rivers").to_crs(target_crs)
else:
    print("Fetching rivers from OSM...")
    rivers = None
    try:
        osm_river = ox.features_from_bbox(
            bbox=(bb[3], bb[1], bb[2], bb[0]),
            tags={"waterway": ["river", "canal"]},
        )
        osm_lines = osm_river[osm_river.geom_type.isin(["LineString", "MultiLineString"])]
        if len(osm_lines) > 0:
            rivers = (
                osm_lines.to_crs(4326)
                .assign(geometry=lambda d: d.geometry.make_valid())
                .pipe(lambda d: gpd.sjoin(d, hanoi_4326[["geometry"]], predicate="intersects"))
            )
            rivers.to_file(gpkg_rivers, layer="rivers", driver="GPKG")
            rivers = rivers.to_crs(target_crs)
    except Exception:
        rivers = None

# 3.2. Water polygons
if gpkg_water.exists():
    print("Loading water polygons from cache...")
    water_poly = gpd.read_file(gpkg_water, layer="water_poly").to_crs(target_crs)
else:
    print("Fetching water polygons from OSM...")
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
                .pipe(lambda d: gpd.sjoin(d, hanoi_4326[["geometry"]], predicate="intersects"))
            )
            water_poly.to_file(gpkg_water, layer="water_poly", driver="GPKG")
            water_poly = water_poly.to_crs(target_crs)
    except Exception:
        water_poly = None

# 3.3. Clip helper
def clip_water(layer, region):
    if layer is None or len(layer) == 0:
        return None
    try:
        result = gpd.clip(layer, region)
    except Exception:
        return None
    return result if len(result) > 0 else None


# 4. Build routable road network ----
print("Building road network graph...")
routable_types = [
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "residential", "unclassified", "service", "living_street",
]
roads_for_routing = (
    roads[roads["highway"].isin(routable_types)]
    [["highway", "geometry"]]
    .explode(index_parts=False)
)
roads_for_routing = roads_for_routing[roads_for_routing.geom_type == "LineString"]
roads_for_routing["geometry"] = roads_for_routing.geometry.make_valid()
roads_for_routing = roads_for_routing[~roads_for_routing.geometry.is_empty]

net_graph = momepy.gdf_to_nx(roads_for_routing, approach="primal", length="length")
net_nodes_sf, net_edges_sf = momepy.nx_to_gdf(net_graph)
print(f"  Network: {net_graph.number_of_nodes()} nodes, {net_graph.number_of_edges()} edges")

# 5. Snap bus edges to network ----
print("Snapping to network...")


def endpoints(geom):
    coords = list(geom.coords)
    return Point(coords[0]), Point(coords[-1])


ends = bus_edges.geometry.apply(endpoints)
from_pts = gpd.GeoDataFrame(geometry=[e[0] for e in ends], crs=target_crs)
to_pts = gpd.GeoDataFrame(geometry=[e[1] for e in ends], crs=target_crs)

from_snap = gpd.sjoin_nearest(from_pts, net_nodes_sf.reset_index(), how="left")
to_snap = gpd.sjoin_nearest(to_pts, net_nodes_sf.reset_index(), how="left")

edge_coords = pd.DataFrame({
    "edge_id": range(len(bus_edges)),
    "from_net": from_snap["index"].to_numpy(),
    "to_net": to_snap["index"].to_numpy(),
})

# 6. Batch shortest-path routing ----
MAX_EDGES_TO_ROUTE = 2000
route_subset = edge_coords[edge_coords["from_net"] != edge_coords["to_net"]]
if len(route_subset) > MAX_EDGES_TO_ROUTE:
    route_subset = route_subset.sample(n=MAX_EDGES_TO_ROUTE, random_state=42)
print(f"Routing {len(route_subset)} connections...")

node_list = list(net_graph.nodes)
routed_lines = []
for i, row in enumerate(route_subset.itertuples(), start=1):
    try:
        path_nodes = nx.shortest_path(
            net_graph, source=node_list[row.from_net], target=node_list[row.to_net], weight="length"
        )
        if len(path_nodes) >= 2:
            routed_lines.append(LineString(path_nodes))
    except (nx.NetworkXNoPath, Exception):
        pass
    if i % 200 == 0:
        print(f"  ... {i}/{len(route_subset)}")

bus_routes_osm = gpd.GeoDataFrame(geometry=routed_lines, crs=target_crs)
print(f"  Routed: {len(routed_lines)} paths")

# 7. Urban core detection ----
# 5 km buffer around the peak stop-density cell
xmin, ymin, xmax, ymax = hanoi.total_bounds
cellsize = 500
cols = np.arange(xmin, xmax + cellsize, cellsize)
rows = np.arange(ymin, ymax + cellsize, cellsize)
grid_cells = [
    LineString([(x, y), (x + cellsize, y), (x + cellsize, y + cellsize), (x, y + cellsize), (x, y)]).convex_hull
    for x in cols[:-1] for y in rows[:-1]
]
grid_500m = gpd.GeoDataFrame({"grid_id": range(len(grid_cells))}, geometry=grid_cells, crs=target_crs)

stop_join = gpd.sjoin(grid_500m, bus_nodes[["geometry"]], how="left", predicate="intersects")
stop_counts = stop_join.groupby("grid_id").size().rename("n_stops")
grid_500m = grid_500m.join(stop_counts, on="grid_id")
grid_500m["n_stops"] = grid_500m["n_stops"].fillna(0).astype(int)

peak_cell = grid_500m.loc[[grid_500m["n_stops"].idxmax()]]
peak_centroid = peak_cell.geometry.centroid
urban_core = gpd.clip(gpd.GeoDataFrame(geometry=peak_centroid.buffer(5000), crs=target_crs), hanoi)
core_bbox = urban_core.total_bounds

# 8. Subset layers ----
major_types = ["motorway", "trunk", "primary", "secondary", "tertiary"]

if "highway" in roads.columns:
    roads_major = roads[roads["highway"].isin(major_types)]
    roads_minor = roads[~roads["highway"].isin(major_types)]
else:
    roads_major = roads
    roads_minor = roads.iloc[0:0]

roads_core = gpd.clip(roads, urban_core)
if "highway" in roads_core.columns:
    roads_core_major = roads_core[roads_core["highway"].isin(major_types)]
    roads_core_minor = roads_core[~roads_core["highway"].isin(major_types)]
else:
    roads_core_major = roads_core
    roads_core_minor = roads_core.iloc[0:0]

bus_routes_city = gpd.clip(bus_routes_osm, hanoi)
bus_nodes_core = gpd.clip(bus_nodes, urban_core)

water_poly_city = clip_water(water_poly, hanoi)
rivers_city = clip_water(rivers, hanoi)
water_poly_core = clip_water(water_poly, urban_core)
rivers_core = clip_water(rivers, urban_core)

# 9. Map styling ----

# 9.1. Colours
col_boundary = "grey50"
col_road = "grey60"       # single road colour for legend
col_bus_stop = "#084594"
col_zoom_box = "#E69F00"
col_water_fill = "#AED6E8"
col_water_bdr = "#7BB8D0"
col_river = "#4A90C4"

# 9.2. Legend elements
# Simplified legend - 3 entries only:
# Bus stop (dot) | Water/Lake (filled square) | Road network (line)
legend_elements = [
    Line2D([0], [0], marker="o", color="w", label="Bus stop",
           markerfacecolor=col_bus_stop, markeredgecolor=col_bus_stop, markersize=6),
    Line2D([0], [0], marker="s", color="w", label="Water / Lake",
           markerfacecolor=col_water_fill, markeredgecolor=col_water_bdr, markersize=10),
    Line2D([0], [0], color=col_road, linewidth=1.5, label="Road network"),
]

# 9.3. North arrow / scale bar helpers
def add_north_arrow(ax):
    ax.annotate(
        "N", xy=(0.95, 0.10), xytext=(0.95, 0.03), xycoords="axes fraction",
        ha="center", fontsize=8, fontweight="bold",
        arrowprops=dict(facecolor="black", width=3, headwidth=8, headlength=8),
    )


def add_scale_bar(ax):
    ax.add_artist(ScaleBar(1, units="m", location="lower left"))


# 10. Citywide plot ----
hanoi_bbox = hanoi.total_bounds

fig_city, ax_city = plt.subplots(figsize=(8, 11))

hanoi.plot(ax=ax_city, facecolor="#fafafa", edgecolor=col_boundary, linewidth=0.30)

if water_poly_city is not None:
    water_poly_city.plot(ax=ax_city, facecolor=col_water_fill, edgecolor=col_water_bdr, linewidth=0.10, alpha=0.90)
if rivers_city is not None:
    rivers_city.plot(ax=ax_city, color=col_river, linewidth=0.40, alpha=0.80)

roads_minor.plot(ax=ax_city, color="#d1d1d1", linewidth=0.07, alpha=0.55)
roads_major.plot(ax=ax_city, color="#8c8c8c", linewidth=0.22, alpha=0.85)

bus_routes_city.plot(ax=ax_city, color="#2171B5", linewidth=0.20, alpha=0.40)
bus_nodes.plot(ax=ax_city, color=col_bus_stop, markersize=0.30, alpha=0.70)

ax_city.add_patch(
    plt.Rectangle(
        (core_bbox[0], core_bbox[1]), core_bbox[2] - core_bbox[0], core_bbox[3] - core_bbox[1],
        fill=False, edgecolor=col_zoom_box, linewidth=0.8,
    )
)

add_scale_bar(ax_city)
add_north_arrow(ax_city)

ax_city.set_xlim(hanoi_bbox[0], hanoi_bbox[2])
ax_city.set_ylim(hanoi_bbox[1], hanoi_bbox[3])
ax_city.set_axis_off()
ax_city.legend(handles=legend_elements, loc="lower left", frameon=True, fontsize=9,
               facecolor="white", edgecolor="#cccccc")

# 11. Urban core plot ----
fig_core, ax_core = plt.subplots(figsize=(8, 8))

hanoi.plot(ax=ax_core, facecolor="#fdfdfd", edgecolor=col_boundary, linewidth=0.20)

if water_poly_core is not None:
    water_poly_core.plot(ax=ax_core, facecolor=col_water_fill, edgecolor=col_water_bdr, linewidth=0.15, alpha=0.90)
if rivers_core is not None:
    rivers_core.plot(ax=ax_core, color=col_river, linewidth=0.60, alpha=0.85)

roads_core_minor.plot(ax=ax_core, color="#d1d1d1", linewidth=0.12, alpha=0.55)
roads_core_major.plot(ax=ax_core, color="#8c8c8c", linewidth=0.30, alpha=0.90)

bus_nodes_core.plot(ax=ax_core, color=col_bus_stop, markersize=0.80, alpha=0.90)

urban_core.boundary.plot(ax=ax_core, color=col_zoom_box, linewidth=0.50, linestyle="dashed")

add_scale_bar(ax_core)
add_north_arrow(ax_core)

ax_core.set_xlim(core_bbox[0], core_bbox[2])
ax_core.set_ylim(core_bbox[1], core_bbox[3])
ax_core.set_axis_off()
for spine in ax_core.spines.values():
    spine.set_visible(True)
    spine.set_edgecolor(col_zoom_box)
    spine.set_linewidth(1.0)

# 12. Two-panel composite ----
fig_panel, (ax_panel_city, ax_panel_core) = plt.subplots(1, 2, figsize=(16, 9))

hanoi.plot(ax=ax_panel_city, facecolor="#fafafa", edgecolor=col_boundary, linewidth=0.30)
if water_poly_city is not None:
    water_poly_city.plot(ax=ax_panel_city, facecolor=col_water_fill, edgecolor=col_water_bdr, linewidth=0.10, alpha=0.90)
if rivers_city is not None:
    rivers_city.plot(ax=ax_panel_city, color=col_river, linewidth=0.40, alpha=0.80)
roads_minor.plot(ax=ax_panel_city, color="#d1d1d1", linewidth=0.07, alpha=0.55)
roads_major.plot(ax=ax_panel_city, color="#8c8c8c", linewidth=0.22, alpha=0.85)
bus_routes_city.plot(ax=ax_panel_city, color="#2171B5", linewidth=0.20, alpha=0.40)
bus_nodes.plot(ax=ax_panel_city, color=col_bus_stop, markersize=0.30, alpha=0.70)
ax_panel_city.add_patch(
    plt.Rectangle(
        (core_bbox[0], core_bbox[1]), core_bbox[2] - core_bbox[0], core_bbox[3] - core_bbox[1],
        fill=False, edgecolor=col_zoom_box, linewidth=0.8,
    )
)
ax_panel_city.set_xlim(hanoi_bbox[0], hanoi_bbox[2])
ax_panel_city.set_ylim(hanoi_bbox[1], hanoi_bbox[3])
ax_panel_city.set_axis_off()

hanoi.plot(ax=ax_panel_core, facecolor="#fdfdfd", edgecolor=col_boundary, linewidth=0.20)
if water_poly_core is not None:
    water_poly_core.plot(ax=ax_panel_core, facecolor=col_water_fill, edgecolor=col_water_bdr, linewidth=0.15, alpha=0.90)
if rivers_core is not None:
    rivers_core.plot(ax=ax_panel_core, color=col_river, linewidth=0.60, alpha=0.85)
roads_core_minor.plot(ax=ax_panel_core, color="#d1d1d1", linewidth=0.12, alpha=0.55)
roads_core_major.plot(ax=ax_panel_core, color="#8c8c8c", linewidth=0.30, alpha=0.90)
bus_nodes_core.plot(ax=ax_panel_core, color=col_bus_stop, markersize=0.80, alpha=0.90)
urban_core.boundary.plot(ax=ax_panel_core, color=col_zoom_box, linewidth=0.50, linestyle="dashed")
ax_panel_core.set_xlim(core_bbox[0], core_bbox[2])
ax_panel_core.set_ylim(core_bbox[1], core_bbox[3])
ax_panel_core.set_axis_off()

fig_panel.legend(handles=legend_elements, loc="lower center", ncol=3, frameon=True,
                  facecolor="white", edgecolor="#cccccc", fontsize=9,
                  bbox_to_anchor=(0.5, -0.02))

# Roads & water: OpenStreetMap | Bus network: GTFS timetable
# Routes computed via networkx shortest paths

# 13. Save outputs ----
fig_city.savefig(out_city_png, dpi=300, bbox_inches="tight", facecolor="white")
fig_core.savefig(out_core_png, dpi=300, bbox_inches="tight", facecolor="white")
fig_panel.savefig(out_panel_png, dpi=300, bbox_inches="tight", facecolor="white")

print(f"Done!\n  {out_city_png}\n  {out_core_png}\n  {out_panel_png}")
plt.show()
