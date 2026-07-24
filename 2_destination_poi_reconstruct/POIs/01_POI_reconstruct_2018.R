# =============================================================================
# RECONSTRUCT HISTORICAL POIs FROM OSM (HÀ NỘI, SNAPSHOT 2018-12-31)
# Standardised 9-group POI framework:
#   - healthcare_2018
#   - education_2018
#   - retail_grocery_2018
#   - parks_public_open_space_2018
#   - sports_facilities_2018
#   - cultural_facilities_2018
#   - religious_sites_2018
#   - local_government_2018   (manual Excel geocoded input)
#   - food_beverage_2018
#   - poi_2018_combined
# =============================================================================

library(ohsome)
library(sf)
library(dplyr)
library(stringr)
library(tidyr)
library(janitor)
library(openxlsx)
library(readxl)

# =============================================================================
# SETTINGS ----
# =============================================================================

SNAPSHOT_DATE <- "2018-12-31"
OUT_DIR       <- "output"
OUT_GPKG      <- file.path(OUT_DIR, "hanoi_POI_2018_reconstructed_standardised_2.gpkg")
OUT_CSV       <- file.path(OUT_DIR, "hanoi_POI_2018_summary_standardised_2.csv")
REVIEW_EXCEL_PATH <- file.path(OUT_DIR, "POI_2018_review_standardised_2.xlsx")

BOUNDARY_PATH <- "/Users/linhlinh/Desktop/accessibility_hanoi/vnm_admin_boundaries/vnm_admin1.geojson"
UBND_EXCEL_PATH <- "/Users/linhlinh/Desktop/accessibility_hanoi/ubnd_hanoi.xlsx"

HEALTHCARE_NAME_REGEX <- regex(
  paste(
    c(
      "Bệnh viện", "Benh vien", "Hospital",
      "Trạm y tế", "Tram y te",
      "Trung tâm y tế", "Trung tam y te",
      "Phòng khám", "Phong kham",
      "Phòng khám đa khoa", "Phong kham da khoa",
      "Phòng khám chuyên khoa", "Phong kham chuyen khoa",
      "Phòng mạch", "Phong mach",
      "Clinic", "Medical Center", "Medical Centre",
      "Health Center", "Health Centre", "Doctors?", "Nha khoa"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

HEALTHCARE_EXCLUDE_REGEX <- regex(
  paste(c("Nhà thuốc", "Nha thuoc", "Pharmacy", "Drugstore", "Spa", "Beauty", "Thẩm mỹ", "Tham my", "Gym"), collapse = "|"),
  ignore_case = TRUE
)

EDUCATION_NAME_REGEX <- regex(
  paste(
    c(
      "Trường", "truong", "School", "Kindergarten",
      "Mầm non", "Mam non", "Mẫu giáo", "Mau giao",
      "Tiểu học", "Tieu hoc", "Trung học", "THCS", "THPT",
      "Phổ thông", "Pho thong",
      "Đại học", "Dai hoc", "Cao đẳng", "Cao dang", "Trung cấp", "Trung cap",
      "Học viện", "Hoc vien", "Academy", "University", "College", "Institute",
      "Viện", "Vien", "Vocational", "Dạy nghề", "Day nghe",
      "Trung tâm ngoại ngữ", "Trung tam ngoai ngu", "Ngoại ngữ", "Ngoai ngu",
      "Language Center", "Language Centre", "English Center", "English Centre",
      "Trung tâm gia sư", "Trung tam gia su", "Gia sư", "Gia su",
      "Trung tâm kỹ năng", "Trung tam ky nang", "Kỹ năng", "Ky nang",
      "Training Center", "Training Centre", "Luyện thi", "Music School", "Driving School"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

EDUCATION_EXCLUDE_REGEX <- regex(
  paste(c("Thư viện", "Thu vien", "Library", "Bảo tàng", "Bao tang", "Museum"), collapse = "|"),
  ignore_case = TRUE
)

RETAIL_GROCERY_NAME_REGEX <- regex(
  paste(
    c(
      "Siêu thị", "Sieu thi", "Supermarket",
      "Chợ", "Cho", "Market", "Marketplace",
      "Tạp hóa", "Tap hoa", "Tạp hoá",
      "Cửa hàng tạp hóa", "Cua hang tap hoa",
      "Cửa hàng tiện lợi", "Cua hang tien loi", "Convenience Store",
      "Minimart", "Mini Mart", "Grocery", "Greengrocer",
      "Bách hóa", "Bach hoa", "Department Store",
      "Mall", "Shopping Mall", "Trung tâm thương mại", "Trung tam thuong mai", "TTTM",
      "WinMart", "Winmart", "Co\\.opmart", "Coopmart", "Big C", "GO!",
      "AEON", "Lotte Mart", "MM Mega Market", "Circle ?K", "GS ?25",
      "Family ?Mart", "7-?Eleven", "Ministop"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

RETAIL_GROCERY_EXCLUDE_REGEX <- regex(
  paste(c("Cafe", "Café", "Coffee", "Nhà hàng", "Nha hang", "Restaurant", "Bakery", "Pet", "Pharmacy", "Drugstore"), collapse = "|"),
  ignore_case = TRUE
)

PARK_OPEN_SPACE_NAME_REGEX <- regex(
  paste(
    c(
      "Công viên", "Cong vien", "Park",
      "Vườn hoa", "Vuon hoa", "Garden",
      "Quảng trường", "Quang truong", "Square",
      "Phố đi bộ", "Pho di bo", "Pedestrian Street", "Walking Street",
      "Open Space", "Không gian mở", "Khong gian mo", "Recreation Ground"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

PARK_OPEN_SPACE_EXCLUDE_REGEX <- regex(
  paste(c("Water Park", "Công viên nước", "Cong vien nuoc", "Theme Park", "Stadium", "Nhà thi đấu", "Nha thi dau", "Sports Complex", "Cultural Palace"), collapse = "|"),
  ignore_case = TRUE
)

SPORTS_NAME_REGEX <- regex(
  paste(
    c(
      "Nhà thi đấu", "Nha thi dau",
      "Cung thể thao", "Cung the thao",
      "Sân vận động", "San van dong",
      "Trung tâm thể thao", "Trung tam the thao",
      "Khu liên hợp thể thao", "Khu lien hop the thao",
      "Khu tổ hợp thể thao", "Khu to hop the thao",
      "Sports Complex", "Sport Complex", "Sports Center", "Sports Centre",
      "Gymnasium", "Arena", "Stadium",
      "Sân bóng", "San bong", "Bể bơi", "Be boi", "Swimming Pool"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

SPORTS_EXCLUDE_REGEX <- regex(
  paste(c("Water Park", "Theme Park", "Cultural Palace", "Nhà văn hóa", "Nha van hoa", "Community Centre", "Community Center"), collapse = "|"),
  ignore_case = TRUE
)

CULTURAL_NAME_REGEX <- regex(
  paste(
    c(
      "Cung văn hóa", "Cung van hoa",
      "Nhà văn hóa", "Nha van hoa",
      "Trung tâm văn hóa nghệ thuật", "Trung tam van hoa nghe thuat",
      "Trung tâm văn hóa", "Trung tam van hoa",
      "Cultural Palace", "Arts Center", "Arts Centre", "Art Center", "Art Centre",
      "Cultural Center", "Cultural Centre", "Community Center", "Community Centre",
      "Theatre", "Theater", "Rạp", "Rap", "Cinema",
      "Rạp chiếu phim", "Rap chieu phim",
      "Bảo tàng", "Bao tang", "Museum",
      "Thư viện", "Thu vien", "Library"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

CULTURAL_EXCLUDE_REGEX <- regex(
  paste(c("Stadium", "Sports Complex", "Sports Centre", "Nhà thi đấu", "Nha thi dau", "Sân vận động", "San van dong"), collapse = "|"),
  ignore_case = TRUE
)

RELIGIOUS_NAME_REGEX <- regex(
  paste(
    c(
      "Nhà thờ", "Nha tho", "Giáo xứ", "Giao xu", "Giáo họ", "Giao ho", "Giáo hạt", "Giao hat",
      "Church", "Chapel", "Cathedral", "Parish",
      "Chùa", "Chua", "Đền", "Den", "Đình", "Dinh", "Miếu", "Mieu",
      "Tu viện", "Tu vien", "Tịnh xá", "Tinh xa", "Pagoda", "Temple", "Monastery", "Shrine"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

FOOD_BEVERAGE_NAME_REGEX <- regex(
  paste(
    c(
      "Nhà hàng", "Nha hang", "Quán ăn", "Quan an", "Restaurant", "Eatery", "Bistro", "Diner",
      "Fast Food", "Food Court",
      "Cà phê", "Ca phe", "Cafe", "Café", "Coffee",
      "Trà sữa", "Tra sua", "Tea",
      "Bar", "Pub", "Bakery",
      "Phở", "Pho", "Bún", "Bun", "Cháo", "Chao", "Bánh mì", "Banh mi",
      "Xôi", "Xoi", "Cơm", "Com", "Lẩu", "Lau", "Nướng", "Nuong",
      "Hải sản", "Hai san", "BBQ", "Buffet", "Pizza", "Burger",
      "KFC", "Lotteria", "McDonald", "Jollibee", "Subway"
    ),
    collapse = "|"
  ),
  ignore_case = TRUE
)

FOOD_BEVERAGE_EXCLUDE_REGEX <- regex(
  paste(c("Siêu thị", "Sieu thi", "Chợ", "Cho", "Market", "Marketplace", "Tạp hóa", "Tap hoa", "Convenience Store", "Supermarket"), collapse = "|"),
  ignore_case = TRUE
)

# =============================================================================
# PART 0: BOUNDARY HÀ NỘI ----
# =============================================================================

vnm1 <- st_read(BOUNDARY_PATH, quiet = TRUE)

ha_noi <- vnm1 %>%
  filter(adm1_name == "Ha Noi") %>%
  st_make_valid() %>%
  st_transform(4326)

cat("Boundary Hà Nội OK:", nrow(ha_noi), "polygon(s)\n")

# =============================================================================
# HELPER FUNCTIONS ----
# =============================================================================

rm_zm_safe <- function(x) {
  if (is.null(x) || nrow(x) == 0) return(NULL)
  st_zm(x, drop = TRUE, what = "ZM")
}

ensure_cols <- function(x, cols) {
  for (nm in cols) {
    if (!(nm %in% names(x))) x[[nm]] <- NA_character_
  }
  x
}

make_points_safely <- function(x) {
  if (is.null(x) || nrow(x) == 0) return(NULL)

  gt <- unique(as.character(st_geometry_type(x, by_geometry = TRUE)))
  if (all(gt %in% c("POINT", "MULTIPOINT"))) {
    return(x)
  }

  suppressWarnings(st_point_on_surface(x))
}

clip_to_boundary <- function(poi_sf, boundary_sf) {
  if (is.null(poi_sf) || nrow(poi_sf) == 0) return(poi_sf)
  poi_sf[st_within(poi_sf, boundary_sf, sparse = FALSE)[, 1], ]
}

std_name <- function(x) {
  x <- tolower(x)
  x <- iconv(x, from = "", to = "ASCII//TRANSLIT")
  x <- gsub("[^a-z0-9 ]", " ", x)
  x <- gsub("\\s+", " ", x)
  trimws(x)
}

coerce_non_geom_to_character <- function(x) {
  if (is.null(x) || nrow(x) == 0) return(x)
  geom_col <- attr(x, "sf_column")
  non_geom <- setdiff(names(x), geom_col)
  for (nm in non_geom) {
    x[[nm]] <- as.character(x[[nm]])
  }
  x
}

bind_sf_rows_safe <- function(x_list) {
  x_list <- Filter(Negate(is.null), x_list)
  if (length(x_list) == 0) return(NULL)

  geom_cols <- unique(vapply(x_list, function(x) attr(x, "sf_column"), character(1)))
  if (length(geom_cols) != 1) {
    stop("Các sf object có geometry column không đồng nhất, không thể bind an toàn.")
  }
  geom_col <- geom_cols[1]

  all_names <- Reduce(union, lapply(x_list, names))
  non_geom_all <- setdiff(all_names, geom_col)

  x_list <- lapply(x_list, function(x) {
    missing_cols <- setdiff(non_geom_all, names(x))
    for (nm in missing_cols) {
      x[[nm]] <- NA_character_
    }
    x <- x[, c(non_geom_all, geom_col)]
    x <- coerce_non_geom_to_character(x)
    x
  })

  dplyr::bind_rows(x_list)
}

fetch_ohsome_snapshot <- function(boundary_sf, filter_string, snapshot_date,
                                  poi_type_label, geometry_type = "geometry") {

  q <- switch(
    geometry_type,
    centroid = ohsome_elements_centroid(
      boundary = boundary_sf,
      filter = filter_string,
      time = snapshot_date,
      properties = c("tags", "metadata"),
      clipGeometry = TRUE
    ),
    geometry = ohsome_elements_geometry(
      boundary = boundary_sf,
      filter = filter_string,
      time = snapshot_date,
      properties = c("tags", "metadata"),
      clipGeometry = TRUE
    ),
    stop("geometry_type phải là 'centroid' hoặc 'geometry'")
  )

  x <- ohsome_post(q)

  if (is.null(x) || nrow(x) == 0) {
    cat("  -> 0 records for", poi_type_label, "\n")
    return(NULL)
  }

  x %>%
    janitor::clean_names() %>%
    mutate(
      poi_type = poi_type_label,
      snapshot_date = snapshot_date
    )
}

standardise_osm_output <- function(x) {
  if (is.null(x) || nrow(x) == 0) return(NULL)

  x %>%
    ensure_cols(c(
      "osm_id", "osm_type", "version", "last_edit",
      "name", "name_en", "name_vi", "official_name", "short_name",
      "amenity", "shop", "brand", "branch",
      "building", "office", "government", "admin_level",
      "religion", "denomination", "healthcare",
      "healthcare_speciality", "operator", "operator_type",
      "education", "leisure", "landuse", "highway", "place", "tourism",
      "website", "phone", "email", "opening_hours", "wheelchair", "wikidata", "wikipedia",
      "addr_housenumber", "addr_street", "addr_district"
    )) %>%
    rename(
      `name:en` = name_en,
      `name:vi` = name_vi,
      `healthcare:speciality` = healthcare_speciality,
      `operator:type` = operator_type,
      `addr:housenumber` = addr_housenumber,
      `addr:street` = addr_street,
      `addr:district` = addr_district
    )
}

build_match_text <- function(df) {
  str_squish(str_c(
    tidyr::replace_na(df$name, ""),
    tidyr::replace_na(df$`name:en`, ""),
    tidyr::replace_na(df$`name:vi`, ""),
    tidyr::replace_na(df$official_name, ""),
    tidyr::replace_na(df$short_name, ""),
    tidyr::replace_na(df$brand, ""),
    tidyr::replace_na(df$branch, ""),
    tidyr::replace_na(df$operator, ""),
    tidyr::replace_na(df$`operator:type`, ""),
    tidyr::replace_na(df$`addr:street`, ""),
    tidyr::replace_na(df$`addr:district`, ""),
    sep = " | "
  ))
}

clean_and_dedup <- function(x, boundary_sf, crs_proj = 32648, dist_m = 30) {
  if (is.null(x) || nrow(x) == 0) return(NULL)

  x <- x %>%
    rm_zm_safe() %>%
    st_make_valid() %>%
    clip_to_boundary(boundary_sf)

  if (nrow(x) == 0) return(x)

  if ("osm_id" %in% names(x)) {
    x <- x %>% distinct(osm_id, .keep_all = TRUE)
  }

  x <- x %>% mutate(name_std = std_name(name))

  x_proj <- st_transform(x, crs_proj)
  coords <- st_coordinates(make_points_safely(x_proj))

  x_proj <- x_proj %>%
    mutate(
      x_coord = coords[, 1],
      y_coord = coords[, 2]
    ) %>%
    arrange(name_std, x_coord, y_coord)

  keep <- rep(TRUE, nrow(x_proj))

  for (i in seq_len(nrow(x_proj))) {
    if (!keep[i]) next
    same_name <- which(
      seq_len(nrow(x_proj)) > i &
        x_proj$name_std == x_proj$name_std[i] &
        !is.na(x_proj$name_std) & x_proj$name_std != ""
    )
    if (length(same_name) == 0) next

    d <- sqrt((x_proj$x_coord[same_name] - x_proj$x_coord[i])^2 +
                (x_proj$y_coord[same_name] - x_proj$y_coord[i])^2)
    keep[same_name[d <= dist_m]] <- FALSE
  }

  x_proj %>%
    filter(keep) %>%
    select(-name_std, -x_coord, -y_coord) %>%
    st_transform(4326)
}

sf_to_df_for_review <- function(sf_obj) {
  if (is.null(sf_obj) || nrow(sf_obj) == 0) return(NULL)
  coords <- st_coordinates(sf_obj)
  sf_obj %>%
    st_drop_geometry() %>%
    mutate(
      longitude = coords[, 1],
      latitude = coords[, 2],
      .before = 1
    )
}

read_reviewed_sheet <- function(wb_path, sheet_nm, crs = 4326) {
  df <- openxlsx::read.xlsx(wb_path, sheet = sheet_nm)
  if (nrow(df) == 0) return(NULL)
  df <- df %>% filter(!is.na(name) & str_trim(as.character(name)) != "")
  sf::st_as_sf(df, coords = c("longitude", "latitude"), crs = crs, remove = FALSE)
}

load_local_government_manual <- function(path_excel, boundary_sf, snapshot_date) {
  ubnd_raw <- read_excel(path_excel)

  stopifnot(all(c("Đơn vị", "Cấp", "Địa chỉ", "Location") %in% names(ubnd_raw)))

  ubnd_parsed <- ubnd_raw %>%
    mutate(
      lat = as.numeric(trimws(str_extract(Location, "^[^,]+"))),
      lon = as.numeric(trimws(str_extract(Location, "[^,]+$")))
    ) %>%
    filter(!is.na(lat) & !is.na(lon))

  ubnd_parsed %>%
    st_as_sf(coords = c("lon", "lat"), crs = 4326, remove = FALSE) %>%
    rename(
      name = `Đơn vị`,
      admin_level = `Cấp`,
      addr_full = `Địa chỉ`,
      latitude = lat,
      longitude = lon
    ) %>%
    mutate(
      osm_id = NA_character_,
      osm_type = NA_character_,
      version = NA_character_,
      last_edit = NA_character_,
      `name:en` = NA_character_,
      `name:vi` = NA_character_,
      official_name = NA_character_,
      short_name = NA_character_,
      amenity = "townhall",
      shop = NA_character_,
      brand = NA_character_,
      branch = NA_character_,
      office = "government",
      government = "administrative",
      building = NA_character_,
      admin_level = as.character(admin_level),
      religion = NA_character_,
      denomination = NA_character_,
      healthcare = NA_character_,
      `healthcare:speciality` = NA_character_,
      operator = NA_character_,
      `operator:type` = NA_character_,
      education = NA_character_,
      leisure = NA_character_,
      landuse = NA_character_,
      highway = NA_character_,
      place = NA_character_,
      tourism = NA_character_,
      `addr:housenumber` = NA_character_,
      `addr:street` = NA_character_,
      `addr:district` = NA_character_,
      phone = NA_character_,
      email = NA_character_,
      website = NA_character_,
      opening_hours = NA_character_,
      wheelchair = NA_character_,
      wikidata = NA_character_,
      wikipedia = NA_character_,
      poi_type = "Local Government",
      snapshot_date = snapshot_date,
      data_source = "manual_excel"
    ) %>%
    clip_to_boundary(boundary_sf) %>%
    select(
      osm_id, osm_type, version, last_edit,
      name, `name:en`, `name:vi`, official_name, short_name,
      amenity, shop, brand, branch,
      building, office, government, admin_level,
      religion, denomination, healthcare, `healthcare:speciality`,
      operator, `operator:type`, education,
      leisure, landuse, highway, place, tourism,
      `addr:housenumber`, `addr:street`, `addr:district`, addr_full,
      latitude, longitude,
      phone, email, website, opening_hours,
      wheelchair, wikidata, wikipedia,
      poi_type, snapshot_date, data_source, geometry
    )
}

# =============================================================================
# PART 1: RECONSTRUCT OSM-BASED POIs ----
# =============================================================================

cat("Downloading reconstructed 2018 POIs from OSM history via ohsome...\n")
cat("Snapshot date:", SNAPSHOT_DATE, "\n")

# 1a. HEALTHCARE --------------------------------------------------------------
cat("Downloading healthcare POIs (2018)...\n")

healthcare_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "amenity=hospital",
    "or amenity=clinic",
    "or amenity=doctors",
    "or healthcare=hospital",
    "or healthcare=clinic",
    "or healthcare=doctor"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Healthcare",
  geometry_type = "geometry"
)

if (is.null(healthcare_raw) || nrow(healthcare_raw) == 0) {
  stop("Không tải được healthcare POIs từ snapshot 2018.")
}

healthcare_pts <- healthcare_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(match_text = build_match_text(pick(everything()))) %>%
  filter(
    amenity %in% c("hospital", "clinic", "doctors") |
      healthcare %in% c("hospital", "clinic", "doctor") |
      (str_detect(match_text, HEALTHCARE_NAME_REGEX) & !str_detect(match_text, HEALTHCARE_EXCLUDE_REGEX))
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    amenity, healthcare, `healthcare:speciality`,
    `operator:type`, operator, religion, denomination,
    `addr:housenumber`, `addr:street`, `addr:district`,
    phone, email, website, opening_hours,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(healthcare_pts), "healthcare POIs in reconstructed 2018 layer\n")

# 1b. EDUCATION ---------------------------------------------------------------
cat("Downloading education POIs (2018)...\n")

education_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "amenity=university",
    "or amenity=college",
    "or amenity=school",
    "or amenity=kindergarten",
    "or amenity=language_school",
    "or amenity=music_school",
    "or amenity=driving_school",
    "or building=university",
    "or building=college",
    "or building=school",
    "or office=educational_institution"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Education",
  geometry_type = "geometry"
)

if (is.null(education_raw) || nrow(education_raw) == 0) {
  stop("Không tải được education POIs từ snapshot 2018.")
}

education_pts <- education_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(match_text = build_match_text(cur_data_all())) %>%
  filter(
    amenity %in% c("university", "college", "school", "kindergarten", "language_school", "music_school", "driving_school") |
      building %in% c("university", "college", "school") |
      office %in% c("educational_institution") |
      (str_detect(match_text, EDUCATION_NAME_REGEX) & !str_detect(match_text, EDUCATION_EXCLUDE_REGEX))
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    amenity, building, office, education,
    `operator:type`, operator,
    `addr:housenumber`, `addr:street`, `addr:district`,
    website, phone, email,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(education_pts), "education POIs in reconstructed 2018 layer\n")

# 1c. RETAIL GROCERY ----------------------------------------------------------
cat("Downloading retail grocery POIs (2018)...\n")

retail_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "shop=supermarket",
    "or shop=convenience",
    "or shop=general",
    "or shop=greengrocer",
    "or shop=kiosk",
    "or shop=department_store",
    "or shop=mall",
    "or amenity=marketplace"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Retail Grocery",
  geometry_type = "geometry"
)

if (is.null(retail_raw) || nrow(retail_raw) == 0) {
  stop("Không tải được retail grocery POIs từ snapshot 2018.")
}

retail_grocery_pts <- retail_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(match_text = build_match_text(cur_data_all())) %>%
  filter(
    amenity %in% c("marketplace") |
      shop %in% c("supermarket", "convenience", "general", "greengrocer", "kiosk", "department_store", "mall") |
      (str_detect(match_text, RETAIL_GROCERY_NAME_REGEX) & !str_detect(match_text, RETAIL_GROCERY_EXCLUDE_REGEX))
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    brand, branch, shop, amenity,
    `addr:housenumber`, `addr:street`, `addr:district`,
    opening_hours, website, phone,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(retail_grocery_pts), "retail grocery POIs in reconstructed 2018 layer\n")

# 1d. PARKS / PUBLIC OPEN SPACE ----------------------------------------------
cat("Downloading parks/public open space POIs (2018)...\n")

parks_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "leisure=park",
    "or leisure=garden",
    "or leisure=playground",
    "or landuse=recreation_ground",
    "or highway=pedestrian",
    "or place=square"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Parks/Public Open Space",
  geometry_type = "geometry"
)

if (is.null(parks_raw) || nrow(parks_raw) == 0) {
  stop("Không tải được parks/public open space POIs từ snapshot 2018.")
}

parks_public_open_space_pts <- parks_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(match_text = build_match_text(cur_data_all())) %>%
  filter(
    ((leisure %in% c("park", "garden", "playground") |
        landuse %in% c("recreation_ground") |
        highway %in% c("pedestrian") |
        place %in% c("square")) |
       str_detect(match_text, PARK_OPEN_SPACE_NAME_REGEX)) &
      !str_detect(match_text, PARK_OPEN_SPACE_EXCLUDE_REGEX) &
      !(leisure %in% c("water_park") | tourism %in% c("theme_park") | building %in% c("stadium", "sports_hall"))
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    leisure, landuse, highway, place,
    `operator:type`, operator,
    `addr:street`, `addr:district`,
    opening_hours, wheelchair, wikidata, wikipedia,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(parks_public_open_space_pts), "parks/public open space POIs in reconstructed 2018 layer\n")

# 1e. SPORTS FACILITIES -------------------------------------------------------
cat("Downloading sports facilities POIs (2018)...\n")

sports_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "leisure=stadium",
    "or leisure=sports_centre",
    "or leisure=pitch",
    "or leisure=track",
    "or leisure=swimming_pool",
    "or building=stadium",
    "or building=sports_hall"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Sports Facilities",
  geometry_type = "geometry"
)

if (is.null(sports_raw) || nrow(sports_raw) == 0) {
  stop("Không tải được sports facilities POIs từ snapshot 2018.")
}

sports_facilities_pts <- sports_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(match_text = build_match_text(cur_data_all())) %>%
  filter(
    leisure %in% c("stadium", "sports_centre", "pitch", "track", "swimming_pool") |
      building %in% c("stadium", "sports_hall") |
      (str_detect(match_text, SPORTS_NAME_REGEX) & !str_detect(match_text, SPORTS_EXCLUDE_REGEX))
  ) %>%
  mutate(
    sports_group = case_when(
      leisure %in% c("stadium") | building %in% c("stadium") |
        str_detect(match_text, regex("Sân vận động|San van dong|Stadium|Arena", ignore_case = TRUE)) ~ "stadium_arena",
      leisure %in% c("sports_centre") | building %in% c("sports_hall") |
        str_detect(match_text, regex("Nhà thi đấu|Nha thi dau|Sports Center|Sports Centre|Sports Complex|Sport Complex|Gymnasium|Cung thể thao|Cung the thao", ignore_case = TRUE)) ~ "sports_centre_hall",
      leisure %in% c("pitch", "track", "swimming_pool") |
        str_detect(match_text, regex("Sân bóng|San bong|Bể bơi|Be boi|Swimming Pool", ignore_case = TRUE)) ~ "pitch_track_pool",
      TRUE ~ "other_sports_facility"
    )
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    amenity, leisure, building,
    `operator:type`, operator,
    `addr:housenumber`, `addr:street`, `addr:district`,
    phone, email, website, opening_hours,
    sports_group,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(sports_facilities_pts), "sports facilities POIs in reconstructed 2018 layer\n")

# 1f. CULTURAL FACILITIES -----------------------------------------------------
cat("Downloading cultural facilities POIs (2018)...\n")

cultural_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "amenity=arts_centre",
    "or amenity=community_centre",
    "or amenity=theatre",
    "or amenity=cinema",
    "or amenity=library",
    "or tourism=museum"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Cultural Facilities",
  geometry_type = "geometry"
)

if (is.null(cultural_raw) || nrow(cultural_raw) == 0) {
  stop("Không tải được cultural facilities POIs từ snapshot 2018.")
}

cultural_facilities_pts <- cultural_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(match_text = build_match_text(cur_data_all())) %>%
  filter(
    amenity %in% c("arts_centre", "community_centre", "theatre", "cinema", "library") |
      tourism %in% c("museum") |
      (str_detect(match_text, CULTURAL_NAME_REGEX) & !str_detect(match_text, CULTURAL_EXCLUDE_REGEX))
  ) %>%
  mutate(
    cultural_group = case_when(
      amenity == "cinema" | str_detect(match_text, regex("Cinema|Rạp|Rap", ignore_case = TRUE)) ~ "cinema",
      tourism == "museum" | str_detect(match_text, regex("Bảo tàng|Bao tang|Museum", ignore_case = TRUE)) ~ "museum",
      amenity == "library" | str_detect(match_text, regex("Thư viện|Thu vien|Library", ignore_case = TRUE)) ~ "library",
      amenity %in% c("arts_centre", "theatre") |
        str_detect(match_text, regex("Arts Center|Arts Centre|Theatre|Theater|Trung tâm văn hóa nghệ thuật|Trung tam van hoa nghe thuat", ignore_case = TRUE)) ~ "arts_theatre",
      TRUE ~ "community_cultural"
    )
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    amenity, tourism,
    `operator:type`, operator,
    `addr:housenumber`, `addr:street`, `addr:district`,
    phone, email, website, opening_hours,
    cultural_group,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(cultural_facilities_pts), "cultural facilities POIs in reconstructed 2018 layer\n")

# 1g. RELIGIOUS SITES ---------------------------------------------------------
cat("Downloading religious sites POIs (2018)...\n")

religious_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "amenity=place_of_worship",
    "or building=church",
    "or building=chapel",
    "or building=cathedral",
    "or building=temple",
    "or building=monastery",
    "or building=shrine",
    "or building=mosque",
    "or building=synagogue",
    "or historic=wayside_shrine",
    "or historic=temple"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Religious Sites",
  geometry_type = "geometry"
)

if (is.null(religious_raw) || nrow(religious_raw) == 0) {
  stop("Không tải được religious sites POIs từ snapshot 2018.")
}

religious_sites_pts <- religious_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(
    match_text = build_match_text(cur_data_all()),
    religion_group = case_when(
      building %in% c("cathedral", "church", "chapel") ~ "church",
      !is.na(religion) & religion %in% c("christian", "catholic") ~ "church",
      building %in% c("temple", "monastery", "shrine") ~ "temple_pagoda_shrine",
      !is.na(religion) & religion == "buddhist" ~ "temple_pagoda_shrine",
      str_detect(match_text, regex("Nhà thờ|Nha tho|Giáo xứ|Giao xu|Church|Chapel|Cathedral|Parish", ignore_case = TRUE)) ~ "church",
      str_detect(match_text, regex("Chùa|Chua|Đền|Den|Đình|Dinh|Miếu|Mieu|Tu viện|Tu vien|Tịnh xá|Tinh xa|Pagoda|Temple|Monastery|Shrine", ignore_case = TRUE)) ~ "temple_pagoda_shrine",
      TRUE ~ "other_religious"
    )
  ) %>%
  filter(
    amenity == "place_of_worship" |
      building %in% c("church", "chapel", "cathedral", "temple", "monastery", "shrine", "mosque", "synagogue") |
      str_detect(match_text, RELIGIOUS_NAME_REGEX)
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    amenity, building, religion, denomination,
    religion_group,
    `addr:housenumber`, `addr:street`, `addr:district`,
    opening_hours, website, wikidata, wikipedia,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(religious_sites_pts), "religious sites POIs in reconstructed 2018 layer\n")

# 1h. FOOD & BEVERAGE ---------------------------------------------------------
cat("Downloading food & beverage POIs (2018)...\n")

food_raw <- fetch_ohsome_snapshot(
  boundary_sf = ha_noi,
  filter_string = paste(
    "amenity=restaurant",
    "or amenity=fast_food",
    "or amenity=food_court",
    "or amenity=cafe",
    "or amenity=bar",
    "or amenity=pub",
    "or shop=bakery"
  ),
  snapshot_date = SNAPSHOT_DATE,
  poi_type_label = "Food & Beverage",
  geometry_type = "geometry"
)

if (is.null(food_raw) || nrow(food_raw) == 0) {
  stop("Không tải được food & beverage POIs từ snapshot 2018.")
}

food_beverage_pts <- food_raw %>%
  standardise_osm_output() %>%
  make_points_safely() %>%
  mutate(match_text = build_match_text(cur_data_all())) %>%
  filter(
    amenity %in% c("restaurant", "fast_food", "food_court", "cafe", "bar", "pub") |
      shop == "bakery" |
      (str_detect(match_text, FOOD_BEVERAGE_NAME_REGEX) & !str_detect(match_text, FOOD_BEVERAGE_EXCLUDE_REGEX))
  ) %>%
  mutate(
    food_group = case_when(
      amenity == "fast_food" |
        str_detect(match_text, regex("KFC|Lotteria|McDonald|Jollibee|Burger|Subway|Pizza|Fast Food", ignore_case = TRUE)) ~ "fast_food",
      amenity == "food_court" ~ "food_court",
      shop == "bakery" |
        str_detect(match_text, regex("Bánh mì|Banh mi|Bakery", ignore_case = TRUE)) ~ "bakery",
      amenity %in% c("cafe", "bar", "pub") |
        str_detect(match_text, regex("Cà phê|Ca phe|Coffee|Cafe|Café|Bar|Pub|Trà sữa|Tra sua", ignore_case = TRUE)) ~ "cafe_bar_pub",
      TRUE ~ "restaurant"
    )
  ) %>%
  select(-match_text) %>%
  clean_and_dedup(ha_noi) %>%
  filter(!is.na(name) & str_trim(name) != "") %>%
  select(
    osm_id, osm_type, version, last_edit,
    name, `name:en`, `name:vi`, official_name, short_name,
    amenity, shop, brand,
    food_group,
    `addr:housenumber`, `addr:street`, `addr:district`,
    opening_hours, website, phone,
    poi_type, snapshot_date, geometry
  )

cat("  ->", nrow(food_beverage_pts), "food & beverage POIs in reconstructed 2018 layer\n")

# =============================================================================
# PART 2A: LOCAL GOVERNMENT FROM MANUAL EXCEL ----
# Final output uses the geocoded manual Excel file instead of OSM auto-query.
# =============================================================================

cat("Loading local government / UBND from manual Excel...\n")
local_government_pts <- load_local_government_manual(UBND_EXCEL_PATH, ha_noi, SNAPSHOT_DATE)
cat("  ->", nrow(local_government_pts), "local government POIs loaded from manual Excel\n")

# =============================================================================
# PART 2B: EXPORT EXCEL FOR MANUAL REVIEW ----
# =============================================================================

wb <- createWorkbook()

poi_list_for_export <- list(
  healthcare = healthcare_pts,
  education = education_pts,
  retail_grocery = retail_grocery_pts,
  parks_public_open_space = parks_public_open_space_pts,
  sports_facilities = sports_facilities_pts,
  cultural_facilities = cultural_facilities_pts,
  religious_sites = religious_sites_pts,
  local_government = local_government_pts,
  food_beverage = food_beverage_pts
)

for (sheet_nm in names(poi_list_for_export)) {
  df_sheet <- sf_to_df_for_review(poi_list_for_export[[sheet_nm]])
  if (is.null(df_sheet)) next

  addWorksheet(wb, sheetName = sheet_nm)
  writeData(wb, sheet = sheet_nm, x = df_sheet, startRow = 1, withFilter = TRUE)

  header_style <- createStyle(
    fontColour = "#FFFFFF", fgFill = "#2F5496",
    halign = "CENTER", textDecoration = "Bold",
    border = "Bottom"
  )
  addStyle(wb, sheet = sheet_nm, style = header_style,
           rows = 1, cols = 1:ncol(df_sheet), gridExpand = TRUE)
  freezePane(wb, sheet = sheet_nm, firstRow = TRUE)
  setColWidths(wb, sheet = sheet_nm, cols = 1:ncol(df_sheet), widths = "auto")
}

saveWorkbook(wb, REVIEW_EXCEL_PATH, overwrite = TRUE)
cat("\nFile Excel để rà soát đã xuất tại:\n ", REVIEW_EXCEL_PATH, "\n")

# =============================================================================
# PART 2C: IMPORT REVIEWED SHEETS ----
# =============================================================================

cat("Importing reviewed POI sheets...\n")

healthcare_pts              <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "healthcare")
education_pts               <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "education")
retail_grocery_pts          <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "retail_grocery")
parks_public_open_space_pts <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "parks_public_open_space")
sports_facilities_pts       <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "sports_facilities")
cultural_facilities_pts     <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "cultural_facilities")
religious_sites_pts         <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "religious_sites")
local_government_pts        <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "local_government")
food_beverage_pts           <- read_reviewed_sheet(REVIEW_EXCEL_PATH, "food_beverage")

cat("Import xong. Số lượng POI sau rà soát:\n")
cat("  healthcare:               ", nrow(healthcare_pts), "\n")
cat("  education:                ", nrow(education_pts), "\n")
cat("  retail_grocery:           ", nrow(retail_grocery_pts), "\n")
cat("  parks_public_open_space:  ", nrow(parks_public_open_space_pts), "\n")
cat("  sports_facilities:        ", nrow(sports_facilities_pts), "\n")
cat("  cultural_facilities:      ", nrow(cultural_facilities_pts), "\n")
cat("  religious_sites:          ", nrow(religious_sites_pts), "\n")
cat("  local_government:         ", nrow(local_government_pts), "\n")
cat("  food_beverage:            ", nrow(food_beverage_pts), "\n")

# =============================================================================
# PART 3: COMBINED LAYER + SUMMARY ----
# =============================================================================

poi_2018_combined <- bind_sf_rows_safe(list(
  healthcare_pts,
  education_pts,
  retail_grocery_pts,
  parks_public_open_space_pts,
  sports_facilities_pts,
  cultural_facilities_pts,
  religious_sites_pts,
  local_government_pts,
  food_beverage_pts
)) %>%
  st_as_sf()

summary_df <- tibble::tibble(
  poi_type = c(
    "Healthcare",
    "Education",
    "Retail Grocery",
    "Parks/Public Open Space",
    "Sports Facilities",
    "Cultural Facilities",
    "Religious Sites",
    "Local Government",
    "Food & Beverage"
  ),
  n_poi = c(
    nrow(healthcare_pts),
    nrow(education_pts),
    nrow(retail_grocery_pts),
    nrow(parks_public_open_space_pts),
    nrow(sports_facilities_pts),
    nrow(cultural_facilities_pts),
    nrow(religious_sites_pts),
    nrow(local_government_pts),
    nrow(food_beverage_pts)
  ),
  snapshot_date = SNAPSHOT_DATE
)

cat("\n========================================\n")
cat("SUMMARY: RECONSTRUCTED POI 2018\n")
cat("========================================\n")
print(summary_df)

# =============================================================================
# PART 4: EXPORT ----
# =============================================================================

dir.create(OUT_DIR, showWarnings = FALSE)
if (file.exists(OUT_GPKG)) file.remove(OUT_GPKG)

st_write(healthcare_pts,              OUT_GPKG, layer = "healthcare_2018",              delete_layer = TRUE, quiet = TRUE)
st_write(education_pts,               OUT_GPKG, layer = "education_2018",               delete_layer = TRUE, quiet = TRUE)
st_write(retail_grocery_pts,          OUT_GPKG, layer = "retail_grocery_2018",          delete_layer = TRUE, quiet = TRUE)
st_write(parks_public_open_space_pts, OUT_GPKG, layer = "parks_public_open_space_2018", delete_layer = TRUE, quiet = TRUE)
st_write(sports_facilities_pts,       OUT_GPKG, layer = "sports_facilities_2018",       delete_layer = TRUE, quiet = TRUE)
st_write(cultural_facilities_pts,     OUT_GPKG, layer = "cultural_facilities_2018",     delete_layer = TRUE, quiet = TRUE)
st_write(religious_sites_pts,         OUT_GPKG, layer = "religious_sites_2018",         delete_layer = TRUE, quiet = TRUE)
st_write(local_government_pts,        OUT_GPKG, layer = "local_government_2018",        delete_layer = TRUE, quiet = TRUE)
st_write(food_beverage_pts,           OUT_GPKG, layer = "food_beverage_2018",           delete_layer = TRUE, quiet = TRUE)
st_write(poi_2018_combined,           OUT_GPKG, layer = "poi_2018_combined",            delete_layer = TRUE, quiet = TRUE)

write.csv(summary_df, OUT_CSV, row.names = FALSE)

cat("\nExported to:\n")
cat("  -", OUT_GPKG, "\n")
cat("  -", OUT_CSV, "\n")
cat("\nAvailable layers:\n")
print(st_layers(OUT_GPKG)$name)

# =============================================================================
# PART 5: IMPORT EXAMPLE ----
# =============================================================================

gpkg_path <- file.path(OUT_DIR, "hanoi_POI_2018_reconstructed_standardised_2.gpkg")
st_layers(gpkg_path)
gdf <- st_read(gpkg_path, layer = "cultural_facilities_2018")
print(gdf)
plot(st_geometry(gdf))
