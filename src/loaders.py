"""Read-only loaders for the frozen committee package in data/raw/."""
import hashlib

import geopandas as gpd
import pandas as pd

from src import paths

DH_TABLES = {
    "collar": "DhCollar.csv",
    "survey": "DhSurvey.csv",
    "assay": "DhAssay.csv",
    "lithology": "DhLithology.csv",
    "alteration": "DhAlteration.csv",
    "mineralisation": "DhMineralisation.csv",
    "oxide": "DhAlterationOxide.csv",
}


def load_dh(name: str) -> pd.DataFrame:
    return pd.read_csv(paths.DH / DH_TABLES[name], low_memory=False)


def load_rock() -> pd.DataFrame:
    return pd.read_csv(paths.SF / "PTRockSampling.csv", low_memory=False)


def load_soil() -> pd.DataFrame:
    return pd.read_csv(paths.SF / "PTSoilSampling.csv", low_memory=False)


def load_contours() -> gpd.GeoDataFrame:
    """Lidar 5 m contours. Elevation lives in Z_Avg (not String_Num)."""
    gdf = gpd.read_file(paths.TOPO / "ConTour Lidar 5m.TAB", engine="pyogrio")
    if gdf.crs is None:
        gdf = gdf.set_crs(paths.CRS)
    return gdf


def verify_raw() -> list[str]:
    """Return files in data/raw whose SHA-256 differs from RAW_MANIFEST.sha256."""
    bad = []
    for line in paths.RAW_MANIFEST.read_text().splitlines():
        digest, rel = line.split(" *", 1)
        f = paths.RAW / rel
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != digest:
            bad.append(rel)
    return bad
