"""Stage 2: lidar DEM from the 5 m contours (plan: LOG.md, 2026-11-02 Stage 2 entry)."""
import geopandas as gpd
import numpy as np
import rasterio
import shapely
from rasterio.transform import from_origin
from scipy.interpolate import LinearNDInterpolator, RBFInterpolator, RegularGridInterpolator
from scipy.spatial import Delaunay, cKDTree

from src import loaders, paths

NODATA = -9999.0
REAL_CONTOURS = "LEVEL_51"   # the other Attrib2 value marks 1.6 m CAD construction fragments


def load_clean_contours() -> gpd.GeoDataFrame:
    g = loaders.load_contours()
    return g[g["Attrib2"] == REAL_CONTOURS].reset_index(drop=True)


def resample_points(gdf: gpd.GeoDataFrame, spacing: float) -> tuple[np.ndarray, np.ndarray]:
    """Points every `spacing` m along each contour (plus its end). Returns (xy, z) with
    duplicate XY removed, so exact interpolators never see two Z at one location."""
    xy, z = [], []
    for geom, zval in zip(gdf.geometry, gdf["Z_Avg"]):
        d = np.append(np.arange(0, geom.length, spacing), geom.length)
        pts = shapely.get_coordinates(shapely.line_interpolate_point(geom, d))
        xy.append(pts)
        z.append(np.full(len(pts), zval, dtype=float))
    xy, z = np.vstack(xy), np.concatenate(z)
    _, keep = np.unique(np.round(xy, 2), axis=0, return_index=True)
    keep = np.sort(keep)
    return xy[keep], z[keep]


def make_grid(bounds, cell: float):
    """Cell-centre coordinates (rows top-down) and the rasterio transform."""
    x0 = np.floor(bounds[0] / cell) * cell
    y1 = np.ceil(bounds[3] / cell) * cell
    nx = int(np.ceil((bounds[2] - x0) / cell))
    ny = int(np.ceil((y1 - bounds[1]) / cell))
    xs = x0 + cell * (np.arange(nx) + 0.5)
    ys = y1 - cell * (np.arange(ny) + 0.5)
    gx, gy = np.meshgrid(xs, ys)
    return gx, gy, from_origin(x0, y1, cell, cell)


def hull_mask(gdf: gpd.GeoDataFrame, gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    return shapely.contains_xy(gdf.union_all().convex_hull, gx, gy)


def fit_tin(xy: np.ndarray, z: np.ndarray):
    return LinearNDInterpolator(xy, z)


def fit_tps(xy: np.ndarray, z: np.ndarray, smoothing: float, neighbors: int = 64):
    """Local thin-plate spline. Coordinates are centred for conditioning."""
    origin = xy.mean(axis=0)
    rbf = RBFInterpolator(xy - origin, z, neighbors=neighbors,
                          kernel="thin_plate_spline", smoothing=smoothing)
    return lambda q: rbf(np.asarray(q) - origin)


def holdout_split(gdf: gpd.GeoDataFrame):
    """Fit on 10 m contours (Z mod 10 = 0), test on the 5 m ones in between."""
    train = (gdf["Z_Avg"] % 10) == 0
    return gdf[train], gdf[~train]


def cv_scores(pred: np.ndarray, truth: np.ndarray) -> dict:
    err = pred - truth
    ok = np.isfinite(err)
    e = err[ok]
    return dict(n=int(ok.sum()), rmse=float(np.sqrt(np.mean(e ** 2))),
                mae=float(np.mean(np.abs(e))), p95_abs=float(np.percentile(np.abs(e), 95)),
                bias=float(np.mean(e)))


def evaluate_on_grid(model, gx, gy, mask) -> np.ndarray:
    dem = np.full(gx.shape, np.nan)
    dem[mask] = model(np.c_[gx[mask], gy[mask]])
    return dem


def _gradients(dem: np.ndarray, cell: float):
    """Horn (1981) 3x3 gradients; NaN where any neighbour is missing."""
    p = np.pad(dem, 1, constant_values=np.nan)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cell)   # rows run north -> south
    return dzdx, dzdy


def slope_deg(dem: np.ndarray, cell: float) -> np.ndarray:
    dzdx, dzdy = _gradients(dem, cell)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def hillshade(dem: np.ndarray, cell: float, azimuth: float = 315, altitude: float = 45) -> np.ndarray:
    dzdx, dzdy = _gradients(dem, cell)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(dzdy, -dzdx)
    zen = np.radians(90 - altitude)
    az = np.radians((360 - azimuth + 90) % 360)
    hs = np.cos(zen) * np.cos(slope) + np.sin(zen) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1) * 255


def support_distance(xy: np.ndarray, gx, gy, mask) -> np.ndarray:
    dist = np.full(gx.shape, np.nan)
    dist[mask] = cKDTree(xy).query(np.c_[gx[mask], gy[mask]])[0]
    return dist


def sample_bilinear(dem: np.ndarray, transform, x, y) -> np.ndarray:
    """Bilinear DEM value at points; NaN outside the grid or next to nodata."""
    cell = transform.a
    xs = transform.c + cell * (np.arange(dem.shape[1]) + 0.5)
    ys = transform.f - cell * (np.arange(dem.shape[0]) + 0.5)
    f = RegularGridInterpolator((ys[::-1], xs), dem[::-1], bounds_error=False, fill_value=np.nan)
    return f(np.c_[np.asarray(y, float), np.asarray(x, float)])


def write_geotiff(path, arr: np.ndarray, transform) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.where(np.isfinite(arr), arr, NODATA).astype("float32")
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype="float32", crs=paths.CRS, transform=transform,
                       nodata=NODATA, compress="deflate") as dst:
        dst.write(data, 1)


def block_folds(xy: np.ndarray, block: float, folds: int) -> np.ndarray:
    """Spatial-block fold id per point: square blocks of `block` m, spread over folds
    so that neighbouring blocks land in different folds."""
    bx = np.floor(xy[:, 0] / block).astype(int)
    by = np.floor(xy[:, 1] / block).astype(int)
    return (bx * 2 + by * 3) % folds


def _bracket(qxy: np.ndarray, xy: np.ndarray, z: np.ndarray, interval: float):
    """Physically allowed range at query points: the Z range of the enclosing Delaunay
    triangle's corners (the contour points framing the point), widened by one contour
    interval, because a missing contour can hide at most one interval. NaN outside the
    triangulation."""
    tri = Delaunay(xy)
    simplex = tri.find_simplex(qxy)
    corners = z[tri.simplices[simplex]]
    lo = np.where(simplex >= 0, corners.min(axis=1) - interval, np.nan)
    hi = np.where(simplex >= 0, corners.max(axis=1) + interval, np.nan)
    return lo, hi


def bracket_clip(pred: np.ndarray, qxy: np.ndarray, xy: np.ndarray, z: np.ndarray,
                 min_support: float = 10.0, interval: float = 5.0):
    """Clip predictions more than `min_support` m from any contour point to their
    bracket (see `_bracket`). Returns (clipped, was_clipped)."""
    pred = np.asarray(pred, float)
    far = cKDTree(xy).query(qxy)[0] > min_support
    lo, hi = _bracket(qxy, xy, z, interval)
    clipped = np.where(far & np.isfinite(lo), np.clip(pred, lo, hi), pred)
    return clipped, far & (clipped != pred)


def gap_overshoot(dem_arr: np.ndarray, support: np.ndarray, xy: np.ndarray, z: np.ndarray,
                  gx, gy, min_support: float = 10.0, interval: float = 5.0) -> np.ndarray:
    """Cells more than `min_support` m from a contour whose value lies outside the bracket
    (see `_bracket`). A TIN and a bracket-clipped surface score zero by construction."""
    gap = np.isfinite(dem_arr) & (support > min_support)
    lo, hi = _bracket(np.c_[gx[gap], gy[gap]], xy, z, interval)
    v = dem_arr[gap]
    flag = np.zeros(dem_arr.shape, bool)
    flag[gap] = (v > hi) | (v < lo)
    return flag
