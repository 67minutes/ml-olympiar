"""Step D (ML-6): derived drainage from the lidar DEM with GRASS in QGIS. Plan: LOG.md, 2026-11-03
ML-6 entry.

Runs inside QGIS 4.2 (GRASS provider), e.g. via the QGIS MCP `execute_code`:
    exec(open(r"<repo>/scripts/15_drainage_qgis.py", encoding="utf-8").read())
`r.watershed` (least-cost search through depressions, so no sink fill; MFD) gives accumulation,
drainage direction and basins at the 2 ha threshold; `r.stream.extract` gives the stream network at
1, 2 and 5 ha (2,500 / 5,000 / 12,500 cells of 2 m). Raw outputs go to data/interim/drainage/;
scripts/15b_drainage_post.py builds gis/drainage.gpkg (Strahler order, doubtful flag, 50 m buffer).
"""
from pathlib import Path

import processing

ROOT = Path(r"C:\Users\mauli\Documents\ml-olympiar")
DEM = str(ROOT / "gis" / "lidar_dem.tif")
OUT = ROOT / "data" / "interim" / "drainage"
CELLS = {"1ha": 2500, "2ha": 5000, "5ha": 12500}
MAIN = "2ha"

OUT.mkdir(parents=True, exist_ok=True)
ws = processing.run("grass:r.watershed", {
    "elevation": DEM, "threshold": CELLS[MAIN], "convergence": 5, "-s": False, "-a": True, "-b": True,
    "accumulation": str(OUT / "akumulasi.tif"), "drainage": str(OUT / "arah_aliran.tif"),
    "basin": str(OUT / f"das_{MAIN}.tif"), "GRASS_REGION_CELLSIZE_PARAMETER": 0})
print("r.watershed:", {k: Path(v).name for k, v in ws.items()})
for name, cells in CELLS.items():
    r = processing.run("grass:r.stream.extract", {
        "elevation": DEM, "threshold": cells, "stream_length": 0,
        "stream_raster": str(OUT / f"alur_{name}.tif"), "stream_vector": str(OUT / f"alur_{name}.gpkg"),
        "direction": str(OUT / f"arah_alur_{name}.tif"), "GRASS_REGION_CELLSIZE_PARAMETER": 0,
        "GRASS_OUTPUT_TYPE_PARAMETER": 2})       # lines only
    print(f"r.stream.extract {name} ({cells} cells):", Path(r["stream_vector"]).name)
processing.run("gdal:polygonize", {"INPUT": str(OUT / f"das_{MAIN}.tif"), "BAND": 1, "FIELD": "das_id",
                                   "EIGHT_CONNECTEDNESS": False, "OUTPUT": str(OUT / f"das_{MAIN}.gpkg")})
print("polygonised basins:", f"das_{MAIN}.gpkg")
