# =============================================================================
# poi_04_global_morans_I.R
# Kiểm định Global Moran's I cho 9 loại POI tại Hà Nội, H3 resolution 9
# Output: 2 bảng kết quả — (1) POI count, (2) Binary presence (0/1)
# =============================================================================

# ── CFG ───────────────────────────────────────────────────────────────────────
CFG <- list(
  # Đầu vào
  boundary_path = "data/boundaries/hanoi_boundary.gpkg",
  poi_gpkg      = "output/hanoi_POI_2018_reconstructed_standardised_2.gpkg",

  # Đầu ra
  out_dir       = "output/moran_poi",

  # H3
  h3_res        = 9,

  # Spatial weights
  queen         = TRUE,
  style         = "W",
  zero_policy   = TRUE,

  # Monte Carlo
  nsim          = 999,
  seed          = 2025
)
# ─────────────────────────────────────────────────────────────────────────────

required_pkgs <- c(
  "sf", "h3jsr", "spdep", "dplyr", "purrr",
  "tibble", "readr", "openxlsx"
)
to_install <- setdiff(required_pkgs, rownames(installed.packages()))
if (length(to_install) > 0) install.packages(to_install)
invisible(lapply(required_pkgs, library, character.only = TRUE))

dir.create(CFG$out_dir, recursive = TRUE, showWarnings = FALSE)

# =============================================================================
# 1. ĐỊNH NGHĨA 9 POI LAYERS
# =============================================================================
POI_LAYERS <- tibble::tibble(
  key   = c("healthcare", "education", "retail_grocery",
            "parks", "sports", "cultural",
            "religious", "local_gov", "food_beverage"),
  layer = c("healthcare_2018", "education_2018", "retail_grocery_2018",
            "parks_public_open_space_2018", "sports_facilities_2018",
            "cultural_facilities_2018", "religious_sites_2018",
            "local_government_2018", "food_beverage_2018"),
  label = c("Healthcare", "Education", "Retail / Grocery",
            "Parks / Open Space", "Sports Facilities", "Cultural Facilities",
            "Religious Sites", "Local Government", "Food & Beverage")
)

# =============================================================================
# 2. XÂY DỰNG H3 GRID & SPATIAL WEIGHTS (một lần dùng chung)
# =============================================================================
message("[1/4] Xây dựng H3 grid và spatial weights ...")

boundary <- sf::st_read(CFG$boundary_path, quiet = TRUE) |>
  sf::st_geometry() |>
  sf::st_as_sf() |>
  sf::st_make_valid() |>
  sf::st_transform(4326)

boundary_union <- sf::st_as_sf(sf::st_union(boundary))

grid_idx <- h3jsr::polygon_to_cells(boundary_union, res = CFG$h3_res)
grid_idx <- unlist(grid_idx, use.names = FALSE)

# UTM 48N cho poly2nb
grid_sf <- h3jsr::cell_to_polygon(grid_idx, simple = FALSE) |>
  sf::st_filter(boundary_union, .predicate = sf::st_intersects) |>
  sf::st_transform(32648)

nb <- spdep::poly2nb(grid_sf, queen = CFG$queen)
lw <- spdep::nb2listw(nb, style = CFG$style, zero.policy = CFG$zero_policy)

message(sprintf("  Số hexagon: %d  |  Avg neighbours: %.2f",
                nrow(grid_sf), mean(spdep::card(nb))))

# WGS84 version dùng cho h3_address join
grid_sf_wgs <- h3jsr::cell_to_polygon(grid_idx, simple = FALSE) |>
  sf::st_filter(boundary_union, .predicate = sf::st_intersects)

# =============================================================================
# 3. HÀM HELPER: đếm POI → Moran's I (count + binary) cho 1 layer
# =============================================================================
run_moran_poi <- function(key, layer, label, grid_sf_wgs, lw, cfg) {

  message(sprintf("  Xử lý: %s", label))

  pts <- sf::st_read(cfg$poi_gpkg, layer = layer, quiet = TRUE) |>
    sf::st_make_valid() |>
    sf::st_transform(4326) |>
    sf::st_collection_extract("POINT")

  poi_idx  <- h3jsr::point_to_cell(pts, res = cfg$h3_res)
  count_df <- tibble::tibble(h3_address = poi_idx) |>
    dplyr::count(h3_address, name = "count")

  grid_count <- grid_sf_wgs |>
    dplyr::left_join(count_df, by = "h3_address") |>
    dplyr::mutate(count = dplyr::coalesce(count, 0L))

  x     <- as.numeric(grid_count$count)   # count
  x_bin <- as.numeric(x > 0)              # binary presence

  # --- Hàm chạy analytical + MC cho 1 vector ---
  run_tests <- function(v) {
    set.seed(cfg$seed)
    mt <- spdep::moran.test(v, listw = lw,
                            zero.policy = cfg$zero_policy, na.action = na.omit)
    set.seed(cfg$seed)
    mc <- spdep::moran.mc(v, listw = lw, nsim = cfg$nsim,
                          zero.policy = cfg$zero_policy, na.action = na.omit)
    list(mt = mt, mc = mc)
  }

  r_count <- run_tests(x)
  r_bin   <- run_tests(x_bin)

  fmt_row <- function(r, n_nonzero, pct_nz) {
    mt <- r$mt; mc <- r$mc
    tibble::tibble(
      label          = label,
      n_poi          = nrow(pts),
      n_hex_nonzero  = n_nonzero,
      pct_nonzero    = pct_nz,
      morans_I       = round(as.numeric(mt$estimate["Moran I statistic"]), 6),
      expectation    = round(as.numeric(mt$estimate["Expectation"]),       6),
      variance       = round(as.numeric(mt$estimate["Variance"]),          8),
      z_score        = round(mt$statistic,                                 4),
      p_analytical   = mt$p.value,
      p_mc           = mc$p.value,
      interpretation = dplyr::case_when(
        mt$estimate["Moran I statistic"] > 0 & mt$p.value < 0.05 ~ "Clustering",
        mt$estimate["Moran I statistic"] < 0 & mt$p.value < 0.05 ~ "Dispersion",
        TRUE ~ "Random"
      )
    )
  }

  list(
    count  = fmt_row(r_count, sum(x > 0),     round(100 * mean(x > 0),     1)),
    binary = fmt_row(r_bin,   sum(x_bin > 0), round(100 * mean(x_bin > 0), 1))
  )
}

# =============================================================================
# 4. CHẠY CHO TẤT CẢ 9 LOẠI POI
# =============================================================================
message("[2/4] Kiểm định Moran's I (count + binary) cho 9 loại POI ...")

all_results <- purrr::pmap(
  list(POI_LAYERS$key, POI_LAYERS$layer, POI_LAYERS$label),
  run_moran_poi,
  grid_sf_wgs = grid_sf_wgs,
  lw          = lw,
  cfg         = CFG
)

results_count  <- purrr::map_dfr(all_results, "count")
results_binary <- purrr::map_dfr(all_results, "binary")

# =============================================================================
# 5. LƯU CSV
# =============================================================================
message("[3/4] Lưu CSV ...")
readr::write_csv(results_count,
  file.path(CFG$out_dir, "global_morans_I_poi_count.csv"))
readr::write_csv(results_binary,
  file.path(CFG$out_dir, "global_morans_I_poi_binary.csv"))

