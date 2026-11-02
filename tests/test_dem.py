import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

from src import dem


@pytest.fixture
def plane_contours():
    # z = 300 + 0.1 * x: vertical contour lines every 50 m in x (5 m interval)
    lines = [LineString([(x, 0), (x, 200)]) for x in range(0, 201, 50)]
    return gpd.GeoDataFrame({"Z_Avg": [300 + 0.1 * x for x in range(0, 201, 50)]},
                            geometry=lines, crs="EPSG:32647")


def test_resample_spacing_and_no_duplicates(plane_contours):
    xy, z = dem.resample_points(plane_contours, 10)
    assert len(xy) == 5 * 21
    assert len(np.unique(np.round(xy, 2), axis=0)) == len(xy)
    assert set(z) == {300.0, 305.0, 310.0, 315.0, 320.0}


def test_tin_exact_on_plane(plane_contours):
    xy, z = dem.resample_points(plane_contours, 10)
    gx, gy, _ = dem.make_grid((0, 0, 200, 200), 5)
    m = dem.hull_mask(plane_contours, gx, gy)
    out = dem.evaluate_on_grid(dem.fit_tin(xy, z), gx, gy, m)
    assert np.allclose(out[m], 300 + 0.1 * gx[m], atol=1e-6)


def test_tps_close_on_plane(plane_contours):
    xy, z = dem.resample_points(plane_contours, 10)
    model = dem.fit_tps(xy, z, smoothing=0.0, neighbors=32)
    q = np.array([[25.0, 100.0], [125.0, 50.0]])
    assert np.allclose(model(q), 300 + 0.1 * q[:, 0], atol=0.05)


def test_holdout_split(plane_contours):
    train, test = dem.holdout_split(plane_contours)
    assert (train.Z_Avg % 10 == 0).all() and (test.Z_Avg % 10 == 5).all()
    assert len(train) + len(test) == len(plane_contours)


def test_make_grid_and_sampling():
    gx, gy, t = dem.make_grid((0, 0, 10, 10), 2)
    assert gx.shape == (5, 5) and gx[0, 0] == 1 and gy[0, 0] == 9
    surf = 2 * gx + 3 * gy
    v = dem.sample_bilinear(surf, t, [4.0, 100.0], [6.0, 5.0])
    assert np.isclose(v[0], 2 * 4 + 3 * 6) and np.isnan(v[1])


def test_hillshade_and_slope():
    flat = np.full((6, 6), 400.0)
    hs = dem.hillshade(flat, 2)
    assert np.allclose(hs[1:-1, 1:-1], 255 * np.cos(np.radians(45)))
    gx, _, _ = dem.make_grid((0, 0, 12, 12), 2)
    ramp = gx * 1.0                        # 45 degree slope, rising east
    assert np.allclose(dem.slope_deg(ramp, 2)[1:-1, 1:-1], 45)
    # sun from NW at 45 deg: west-facing 45 deg slope = 0.5 + 0.5 cos45 (brighter than flat),
    # east-facing = 0.5 - 0.5 cos45 (darker)
    c45 = np.cos(np.radians(45))
    assert np.isclose(dem.hillshade(ramp, 2)[2, 2], 255 * (0.5 + 0.5 * c45))
    assert np.isclose(dem.hillshade(-ramp, 2)[2, 2], 255 * (0.5 - 0.5 * c45))


def test_block_folds_separate_neighbours():
    xy = np.array([[50, 50], [150, 50], [50, 150], [150, 150], [55, 60]], float)
    f = dem.block_folds(xy, 100, 5)
    assert f[0] == f[4]                              # same block, same fold
    assert len({f[0], f[1], f[2]}) == 3              # edge neighbours differ


def test_gap_overshoot_flags_bubble():
    gx, gy, _ = dem.make_grid((0, 0, 100, 100), 10)
    xy = np.array([[0, 0], [100, 0], [0, 100], [100, 100]], float)
    z = np.array([400, 400, 405, 405], float)
    surf = np.full(gx.shape, 402.0)
    surf[5, 5] = 420.0                               # a bubble 15 m above every contour
    surf[5, 6] = 409.0                               # within one interval: allowed
    support = np.full(gx.shape, 50.0)
    flag = dem.gap_overshoot(surf, support, xy, z, gx, gy)
    assert flag[5, 5] and flag.sum() == 1


def test_tin_never_overshoots(plane_contours):
    xy, z = dem.resample_points(plane_contours, 10)
    gx, gy, _ = dem.make_grid((0, 0, 200, 200), 5)
    m = dem.hull_mask(plane_contours, gx, gy)
    out = dem.evaluate_on_grid(dem.fit_tin(xy, z), gx, gy, m)
    assert not dem.gap_overshoot(out, np.full(gx.shape, 50.0), xy, z, gx, gy).any()


def test_bracket_clip_removes_overshoot_only_far_from_contours():
    xy = np.array([[0, 0], [100, 0], [0, 100], [100, 100]], float)
    z = np.array([400, 400, 405, 405], float)
    q = np.array([[50, 50], [50, 40], [1, 1]], float)
    pred = np.array([420.0, 408.0, 430.0])          # bubble, allowed, next to a contour point
    out, was = dem.bracket_clip(pred, q, xy, z)
    assert out.tolist() == [410.0, 408.0, 430.0]    # clipped to max 405 + 5; near point untouched
    assert was.tolist() == [True, False, False]
