# =============================================================================
# poi_viz-5.R
# FULL H3 GRID MAPS FOR ALL POI TYPES — HANOI 2018
# Overlay: bus network (routes + stops)
# Resolution: H3 res-9
# =============================================================================

# =============================================================================
# PATHS ----
# =============================================================================
BOUNDARY_PATH <- "/Volumes/2832083l/02_hanoi_accessibility/accessibility_hn/data/boundaries/hanoi_boundary.gpkg"
POI_GPKG      <- "/Volumes/2832083l/02_hanoi_accessibility/accessibility_hn/output/hanoi_POI_2018_reconstructed_standardised_2.gpkg"
COMBINED_GPKG <- "/Volumes/2832083l/02_hanoi_accessibility/accessibility_hn/hanoi_combined_networks.gpkg"
OUTPUT_FILE   <- "/Volumes/2832083l/02_hanoi_accessibility/accessibility_hn/output/POI_maps_h3_res9_busnetwork.png"

# =============================================================================
# PLOT CONFIG — chỉnh tất cả tham số ở đây
# =============================================================================
CFG <- list(

  # --- H3 ---
  h3_res = 8,

  # --- Layout ---
  layout_ncol = 3,

  # --- Map background & boundary ---
  map_fill          = "grey98",
  boundary_colour   = "grey50",
  boundary_lw       = 0.30,

  # --- Bus stops ---
  bus_stop_colour   = "#084594",
  bus_stop_size     = 0.10,
  bus_stop_alpha    = 0.50,

  # --- H3 grid (empty cells) ---
  empty_col         = "grey85",
  empty_lw          = 0.04,

  # --- H3 grid (filled cells) ---
  filled_border_col = "white",
  filled_lw         = 0.06,
  filled_alpha      = 0.92,

  # --- Panel title ---
  title_size        = 8,
  title_face        = "bold",
  title_hjust       = 0,

  # --- Legend colourbar ---
  legend_position      = "bottom",
  legend_direction     = "horizontal",
  legend_title_size    = 6,
  legend_title_face    = "plain",
  legend_text_size     = 5.0,
  legend_bar_width_mm  = 13,
  legend_bar_height_mm = 1.5,
  legend_n_breaks      = 3,     # số mốc số trên thanh legend (giảm để tránh chồng chữ)

  # --- Panel margin (pt): 0 = no whitespace between panels ---
  plot_margin = 0,

  # --- Patchwork outer margin (pt): space around the full 3x3 grid ---
  outer_margin = 2,

  # --- Overall caption (explains H3 cells, bus stops) ---
  # caption_text = paste0(
  #   "Each hexagon (H3 resolution 9, ~0.105 km\u00b2 per cell) is shaded by the count of POIs falling within it; ",
  #   "darker/lighter shade = higher POI density (see per-panel colour scale). Unshaded (grey-outlined) cells contain no POIs. ",
  #   "Small blue dots are bus stops, indicating the public transport network."
  # ),
  # caption_size      = 7,
  # caption_colour    = "grey30",
  # caption_hjust     = 0,
  # caption_lineheight = 1.05,
  # caption_margin_top = 6,   # pt, space between grid and caption

  # --- Export — khổ A4 dọc (portrait): 8.27 × 11.69 inch ---
  save_width  = 8.27,
  save_height = 11.69,
  save_dpi    = 300
)

# =============================================================================
# PACKAGES ----
# =============================================================================
required_pkgs <- c("sf", "dplyr", "ggplot2", "h3jsr", "patchwork", "viridis")
to_install <- setdiff(required_pkgs, rownames(installed.packages()))
if (length(to_install) > 0) install.packages(to_install)
invisible(lapply(required_pkgs, library, character.only = TRUE))

# =============================================================================
# LOAD DATA ----
# =============================================================================
message("Loading boundary and network layers...")

ha_noi <- st_read(BOUNDARY_PATH, quiet = TRUE) |>
  st_geometry() |> st_as_sf() |>
  st_make_valid() |> st_transform(4326)

# Bus stops only (bus_edges removed — routed lines cause visual artefacts;
# major roads also removed — not needed and st_filter on the full road
# network was the slow step)
bus_nodes <- st_read(COMBINED_GPKG, layer = "bus_nodes", quiet = TRUE) |>
  st_transform(4326)

message("Loading POI layers...")

healthcare_pts     <- st_read(POI_GPKG, layer = "healthcare_2018",              quiet = TRUE)
education_pts      <- st_read(POI_GPKG, layer = "education_2018",               quiet = TRUE)
retail_grocery_pts <- st_read(POI_GPKG, layer = "retail_grocery_2018",          quiet = TRUE)
park_pts           <- st_read(POI_GPKG, layer = "parks_public_open_space_2018", quiet = TRUE)
sports_pts         <- st_read(POI_GPKG, layer = "sports_facilities_2018",       quiet = TRUE)
cultural_pts       <- st_read(POI_GPKG, layer = "cultural_facilities_2018",     quiet = TRUE)
religious_pts      <- st_read(POI_GPKG, layer = "religious_sites_2018",         quiet = TRUE)
local_gov_pts      <- st_read(POI_GPKG, layer = "local_government_2018",        quiet = TRUE)
food_beverage_pts  <- st_read(POI_GPKG, layer = "food_beverage_2018",           quiet = TRUE)

# =============================================================================
# POI SUMMARY ----
# =============================================================================
poi_summary <- tibble::tibble(
  label = c("Healthcare", "Education", "Retail / Grocery",
            "Parks / Open Space", "Sports Facilities", "Cultural Facilities",
            "Religious Sites", "Local Government", "Food & Beverage"),
  n_poi = c(nrow(healthcare_pts), nrow(education_pts), nrow(retail_grocery_pts),
            nrow(park_pts),       nrow(sports_pts),    nrow(cultural_pts),
            nrow(religious_pts),  nrow(local_gov_pts), nrow(food_beverage_pts))
)
cat("\n========================================\n")
cat("POI COUNT — HANOI 2018 RECONSTRUCTION\n")
cat("========================================\n")
print(poi_summary, n = Inf)
cat(sprintf("TOTAL: %d POIs across 9 categories\n", sum(poi_summary$n_poi)))
cat("========================================\n\n")

# =============================================================================
# BUILD H3 GRID ----
# =============================================================================
message("Building H3 grid (res-", CFG$h3_res, ")...")

boundary_union <- st_as_sf(st_union(ha_noi))
grid_idx       <- unlist(polygon_to_cells(boundary_union, res = CFG$h3_res),
                         use.names = FALSE)
full_grid      <- cell_to_polygon(grid_idx, simple = FALSE) |>
  st_filter(boundary_union, .predicate = st_intersects)

message("  ", nrow(full_grid), " hexagons")

# =============================================================================
# HELPERS ----
# =============================================================================
count_poi_in_grid <- function(poi_sf, grid_sf) {
  pts     <- poi_sf |> st_make_valid() |> st_transform(4326) |>
    st_collection_extract("POINT")
  idx     <- point_to_cell(pts, res = CFG$h3_res)
  cnt_df  <- tibble::tibble(h3_address = idx) |>
    dplyr::count(h3_address, name = "count")
  grid_sf |>
    left_join(cnt_df, by = "h3_address") |>
    mutate(count = coalesce(count, 0L))
}

theme_map_poi <- function(cfg = CFG) {
  theme_void() +
    theme(
      panel.border        = element_rect(colour = "grey80", fill = NA,
                                         linewidth = 0.4),
      legend.position     = cfg$legend_position,
      legend.direction    = cfg$legend_direction,
      legend.title        = element_text(size = cfg$legend_title_size,
                                         face = cfg$legend_title_face),
      legend.text         = element_text(size = cfg$legend_text_size),
      legend.key.width    = unit(cfg$legend_bar_width_mm,  "mm"),
      legend.key.height   = unit(cfg$legend_bar_height_mm, "mm"),
      plot.title          = element_text(face  = cfg$title_face,
                                         size  = cfg$title_size,
                                         hjust = cfg$title_hjust,
                                         margin = margin(b = 1)),
      plot.title.position = "plot",
      # Zero margins — patchwork outer_margin handles outer spacing
      plot.margin         = margin(0, 0, 0, 0)
    )
}

plot_poi_h3 <- function(grid_sf, title_text, legend_name,
                        palette = "viridis", cfg = CFG) {
  ggplot() +

    # 1. Map background
    geom_sf(data = ha_noi,
            fill = cfg$map_fill, colour = cfg$boundary_colour,
            linewidth = cfg$boundary_lw) +

    # 2. Bus stops
    geom_sf(data = bus_nodes,
            colour = cfg$bus_stop_colour,
            size   = cfg$bus_stop_size,
            alpha  = cfg$bus_stop_alpha,
            show.legend = FALSE) +

    # 3. Empty H3 grid
    geom_sf(data = grid_sf,
            fill = NA, colour = cfg$empty_col,
            linewidth = cfg$empty_lw) +

    # 4. Filled H3 cells (POI present)
    geom_sf(data = filter(grid_sf, count > 0),
            aes(fill = count),
            colour    = cfg$filled_border_col,
            linewidth = cfg$filled_lw,
            alpha     = cfg$filled_alpha) +

    scale_fill_viridis_c(
      option = palette,
      name   = legend_name,
      trans  = "sqrt",
      breaks = scales::breaks_pretty(n = cfg$legend_n_breaks),
      labels = scales::label_number(accuracy = 1),
      guide  = guide_colourbar(
        title.position = "top",
        barwidth  = unit(cfg$legend_bar_width_mm,  "mm"),
        barheight = unit(cfg$legend_bar_height_mm, "mm")
      )
    ) +

    coord_sf(expand = FALSE, clip = "on") +
    labs(title = title_text) +
    theme_map_poi(cfg)
}

# =============================================================================
# COUNT POI PER HEXAGON ----
# =============================================================================
message("Counting POI per hexagon...")

hex_healthcare    <- count_poi_in_grid(healthcare_pts,     full_grid)
hex_education     <- count_poi_in_grid(education_pts,      full_grid)
hex_retail        <- count_poi_in_grid(retail_grocery_pts, full_grid)
hex_park          <- count_poi_in_grid(park_pts,           full_grid)
hex_sports        <- count_poi_in_grid(sports_pts,         full_grid)
hex_cultural      <- count_poi_in_grid(cultural_pts,       full_grid)
hex_religious     <- count_poi_in_grid(religious_pts,      full_grid)
hex_local_gov     <- count_poi_in_grid(local_gov_pts,      full_grid)
hex_food_beverage <- count_poi_in_grid(food_beverage_pts,  full_grid)

# =============================================================================
# INDIVIDUAL MAPS ----
# =============================================================================
message("Plotting...")

map_healthcare    <- plot_poi_h3(hex_healthcare,    "Healthcare",          "No. of facilities", "viridis")
map_education     <- plot_poi_h3(hex_education,     "Education",           "No. of facilities", "mako")
map_retail        <- plot_poi_h3(hex_retail,        "Retail / Grocery",    "No. of facilities", "inferno")
map_park          <- plot_poi_h3(hex_park,          "Parks / Open Space",  "No. of facilities", "cividis")
map_sports        <- plot_poi_h3(hex_sports,        "Sports Facilities",   "No. of facilities", "plasma")
map_cultural      <- plot_poi_h3(hex_cultural,      "Cultural Facilities", "No. of facilities", "rocket")
map_religious     <- plot_poi_h3(hex_religious,     "Religious Sites",     "No. of facilities", "turbo")
map_local_gov     <- plot_poi_h3(hex_local_gov,     "Local Government",    "No. of offices",    "magma")
map_food_beverage <- plot_poi_h3(hex_food_beverage, "Food & Beverage",     "No. of facilities", "viridis")

# =============================================================================
# COMBINE & EXPORT ----
# =============================================================================
combined <- wrap_plots(
  map_healthcare, map_education,    map_retail,
  map_park,       map_sports,       map_cultural,
  map_religious,  map_local_gov,    map_food_beverage,
  ncol  = CFG$layout_ncol,
  byrow = TRUE
) +
  plot_layout(guides = "keep") &
  theme(
    # Collect legends bottom, strip all outer whitespace from patchwork
    plot.margin = margin(0, 0, 0, 0)
  )

# Wrap in plot_annotation to apply a single tight outer margin
# + an overall caption explaining how POIs are represented in the H3 cells
combined <- combined +
  plot_annotation(
    caption = CFG$caption_text,
    theme = theme(
      plot.margin  = margin(CFG$outer_margin, CFG$outer_margin,
                             CFG$outer_margin, CFG$outer_margin),
      plot.caption = element_text(
        size       = CFG$caption_size,
        colour     = CFG$caption_colour,
        hjust      = CFG$caption_hjust,
        lineheight = CFG$caption_lineheight,
        margin     = margin(t = CFG$caption_margin_top)
      ),
      plot.caption.position = "plot",
      plot.background        = element_rect(fill = "white", colour = NA)
    )
  )

print(combined)

ggsave(
  filename = OUTPUT_FILE,
  plot     = combined,
  width    = CFG$save_width,
  height   = CFG$save_height,
  dpi      = CFG$save_dpi,
  bg       = "white"
)
