"""Build the teammate ML findings report (outputs/laporan_ml/): fill number placeholders from the
processed CSVs, embed figures so the HTML is one self-contained local file, and check internal links."""
import base64
import io
import re
from pathlib import Path

from PIL import Image

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
IMG_SRC = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")')


def fmt_id(x, nd: int = 2) -> str:
    """Number in Indonesian style: decimal comma, dot for thousands (0,70; 2.412; 1.350,5)."""
    if isinstance(x, (int,)) or (isinstance(x, float) and nd == 0):
        s = f"{round(x):,}"
    else:
        s = f"{x:,.{nd}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def fill_facts(html: str, facts: dict) -> str:
    """Replace every {{key}} with facts[key]; raise if a key is missing or a value is empty."""
    missing = sorted({k for k in PLACEHOLDER.findall(html) if k not in facts})
    if missing:
        raise KeyError(f"unresolved placeholders: {missing}")
    empty = sorted(k for k in set(PLACEHOLDER.findall(html)) if str(facts[k]).strip() == "")
    if empty:
        raise ValueError(f"empty fact values: {empty}")
    return PLACEHOLDER.sub(lambda m: str(facts[m.group(1)]), html)


def image_data_uri(path: Path, max_px: int = 1800) -> str:
    """PNG as a base64 data URI, longest side capped at max_px (figures are 300 dpi, too big inline)."""
    im = Image.open(path)
    im.load()
    if im.mode not in ("RGB", "RGBA", "L"):
        im = im.convert("RGBA")
    im.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def embed_images(html: str, root: Path, max_px: int = 1800) -> tuple[str, list[str]]:
    """Inline every relative <img src> under root; raise on a missing file. Returns (html, paths)."""
    used, missing = [], []

    def sub(m):
        src = m.group(2)
        if src.startswith("data:"):
            return m.group(0)
        p = root / src
        if not p.is_file():
            missing.append(src)
            return m.group(0)
        used.append(src)
        return m.group(1) + image_data_uri(p, max_px) + m.group(3)

    out = IMG_SRC.sub(sub, html)
    if missing:
        raise FileNotFoundError(f"missing images: {missing}")
    return out, used


def check_links(html: str) -> list[str]:
    """Internal #anchors that have no matching id (empty list = all links resolve)."""
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    hrefs = re.findall(r'href="#([^"]+)"', html)
    return sorted({h for h in hrefs if h not in ids})
