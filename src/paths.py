"""Central paths so scripts never hard-code locations."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
FIGURES = ROOT / "outputs" / "figures"
MAPS = ROOT / "outputs" / "maps"
GIS = ROOT / "gis"
RAW_MANIFEST = ROOT / "RAW_MANIFEST.sha256"

DH = RAW / "RJ_DH_OlympiAR_2026"
SF = RAW / "RJ_SF_OlympiAR_2026"
TOPO = RAW / "RJ_TOPO_OlympiAR_2026"

CRS = "EPSG:32647"  # UTM WGS84 Zone 47N
