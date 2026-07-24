import re
from itertools import product
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.mask import mask

# 1. Setup ----

# 1.1. Imports

# 1.2. Paths and config
project_dir = Path("data/worldpop_hanoi_2018")
raw_dir = project_dir / "raw"
clip_dir = project_dir / "clipped"
summary_dir = project_dir / "summary"

for p in (project_dir, raw_dir, clip_dir, summary_dir):
    p.mkdir(parents=True, exist_ok=True)

boundary_path = "data/boundaries/hanoi_boundary.gpkg"
boundary_layer = None

download_total_pop = True
download_age_sex = True

sexes = ["f", "m"]
age_codes = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]

pop_url = "https://data.worldpop.org/GIS/Population/Global_2000_2020/2018/VNM/vnm_ppp_2018.tif"
age_sex_base_url = "https://data.worldpop.org/GIS/AgeSex_structures/Global_2000_2020/2018/VNM"

# 2. Helper functions ----

# 2.1. Boundary reader
def read_boundary(path, layer=None):
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf.to_crs(4326)


# 2.2. Safe download
def safe_download(url, destfile):
    destfile = Path(destfile)
    if not destfile.exists():
        with requests.get(url, stream=True, timeout=1200) as r:
            r.raise_for_status()
            with open(destfile, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    return destfile


# 2.3. Clip one raster to the Hanoi boundary
def clip_one_raster(infile, boundary_geom, out_dir):
    infile = Path(infile)
    with rasterio.open(infile) as src:
        out_image, out_transform = mask(src, boundary_geom, crop=True)
        out_meta = src.meta.copy()

    out_meta.update({
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
        "compress": "DEFLATE",
    })

    outfile = out_dir / f"{infile.stem}_hanoi.tif"
    with rasterio.open(outfile, "w", **out_meta) as dst:
        dst.write(out_image)

    nodata = out_meta.get("nodata")
    band = out_image[0].astype("float64")
    if nodata is not None:
        band[band == nodata] = np.nan
    total_val = float(np.nansum(band))

    return {
        "source_file": infile.name,
        "clipped_file": outfile.name,
        "total_population": total_val,
        "clipped_path": str(outfile.resolve()),
    }


# 2.4. WorldPop age-band labelling and filename parsing
def age_label(age_code):
    if age_code == 0:
        return "0_12m"
    if age_code == 1:
        return "1_4"
    if age_code == 80:
        return "80_plus"
    return f"{age_code}_{age_code + 4}"


def parse_worldpop_name(x):
    nm = Path(x).stem

    if nm == "vnm_ppp_2018_hanoi":
        return {"variable": "total_pop", "sex": "both", "age_code": np.nan, "age_group": "total"}

    m = re.match(r"^vnm_(f|m)_(\d+)_2018_hanoi$", nm)
    if not m:
        return {"variable": "unknown", "sex": None, "age_code": np.nan, "age_group": None}

    age_code = int(m.group(2))
    sex = "female" if m.group(1) == "f" else "male"
    return {"variable": "age_sex", "sex": sex, "age_code": age_code, "age_group": age_label(age_code)}


# 3. Download raw rasters ----
hanoi = read_boundary(boundary_path, boundary_layer)
boundary_geom = [hanoi.geometry.union_all()]

files_to_download = []

if download_total_pop:
    files_to_download.append(pop_url)

if download_age_sex:
    for sex, age_code in product(sexes, age_codes):
        files_to_download.append(f"{age_sex_base_url}/vnm_{sex}_{age_code}_2018.tif")

raw_files = [safe_download(url, raw_dir / Path(url).name) for url in files_to_download]

# 4. Clip rasters to Hanoi boundary ----
clip_records = [clip_one_raster(f, boundary_geom, clip_dir) for f in raw_files]
clip_summary = pd.DataFrame(clip_records)

parsed = pd.DataFrame([parse_worldpop_name(f) for f in clip_summary["clipped_file"]])
clip_summary = pd.concat([clip_summary, parsed], axis=1).sort_values(
    ["variable", "sex", "age_code"]
)

# 5. Export summary ----
clip_summary.to_csv(summary_dir / "worldpop_hanoi_2018_clip_summary.csv", index=False)
