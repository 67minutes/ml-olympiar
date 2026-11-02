import numpy as np
import pandas as pd
import pytest

from src import desurvey as ds

COLLAR = np.array([1000.0, 2000.0, 500.0])


def test_unit_vectors():
    v = ds.unit_vectors(np.array([-90.0, 0.0, -45.0]), np.array([0.0, 90.0, 180.0]))
    assert np.allclose(v[0], [0, 0, -1])
    assert np.allclose(v[1], [1, 0, 0])
    assert np.allclose(v[2], [0, -np.sqrt(0.5), -np.sqrt(0.5)])


def test_vertical_hole():
    d = np.array([0.0, 50.0, 100.0])
    xyz = ds.min_curvature(d, np.full(3, -90.0), np.zeros(3), COLLAR)
    assert np.allclose(xyz[:, :2], COLLAR[:2])
    assert np.allclose(xyz[:, 2], COLLAR[2] - d)


def test_straight_inclined_hole():
    d = np.array([0.0, 100.0])
    xyz = ds.min_curvature(d, np.full(2, -45.0), np.full(2, 90.0), COLLAR)
    h = 100 * np.sqrt(0.5)
    assert np.allclose(xyz[1], COLLAR + [h, 0, -h])


def test_constant_curvature_arc_matches_circle():
    # dip goes from 0 to -90 in the north-vertical plane over a quarter circle of radius R:
    # start heading north, end heading down; end point is (N = R, Z = -R).
    R = 100.0
    length = np.pi / 2 * R
    d = np.array([0.0, length])
    xyz = ds.min_curvature(d, np.array([0.0, -90.0]), np.array([0.0, 0.0]), COLLAR)
    assert np.allclose(xyz[1], COLLAR + [0, R, -R])
    # interpolation along the arc stays on the circle
    q = np.linspace(0, length, 9)
    p = ds.position_at(d, np.array([0.0, -90.0]), np.array([0.0, 0.0]), xyz, q) - COLLAR
    assert np.allclose(np.hypot(p[:, 1], p[:, 2] + R), R)
    assert np.allclose(R * np.arctan2(p[:, 1], p[:, 2] + R), q)  # arc length


def test_azimuth_wrap_has_no_spin():
    d = np.array([0.0, 100.0])
    a = ds.min_curvature(d, np.full(2, -45.0), np.array([359.0, 1.0]), COLLAR)
    b = ds.min_curvature(d, np.full(2, -45.0), np.array([0.0, 0.0]), COLLAR)
    assert np.linalg.norm(a[1] - b[1]) < 0.1


def test_near_vertical_azimuth_flip_is_small():
    d = np.array([0.0, 100.0])
    xyz = ds.min_curvature(d, np.full(2, -89.9), np.array([0.0, 180.0]), COLLAR)
    assert np.hypot(*(xyz[1, :2] - COLLAR[:2])) < 0.2


def test_position_at_stations_equals_stations():
    d = np.array([0.0, 30.0, 70.0, 120.0])
    dip, az = np.array([-60.0, -58.0, -55.0, -54.0]), np.array([315.0, 318.0, 322.0, 330.0])
    xyz = ds.min_curvature(d, dip, az, COLLAR)
    assert np.allclose(ds.position_at(d, dip, az, xyz, d), xyz)


def test_position_beyond_last_station_rejected():
    d = np.array([0.0, 50.0])
    xyz = ds.min_curvature(d, np.full(2, -60.0), np.zeros(2), COLLAR)
    with pytest.raises(ValueError):
        ds.position_at(d, np.full(2, -60.0), np.zeros(2), xyz, np.array([60.0]))


@pytest.fixture
def tables():
    collar = pd.DataFrame({"SiteID": ["A", "B"], "EndDepth": [150.0, 100.0],
                           "EastUTM": [0.0, 10.0], "NorthUTM": [0.0, 0.0], "RLUTM": [100.0, 90.0]})
    survey = pd.DataFrame({"SiteID": ["A", "A", "B", "B"], "DepthAt": [0.0, 100.0, 0.0, 100.0],
                           "Dip": [-60.0, -58.0, -90.0, -90.0], "AzimUTM": [315.0, 320.0, 0.0, 0.0],
                           "Method": ["CC", "REFLEX", "CC", "REFLEX"]})
    return collar, survey


def test_extrapolate_to_eoh(tables):
    collar, survey = tables
    out = ds.extrapolate_to_eoh(survey, collar)
    assert len(out) == 5
    ex = out[out.Method.eq("EXTRAP")]
    assert ex.SiteID.tolist() == ["A"] and ex.DepthAt.iloc[0] == 150.0
    assert (ex.Dip.iloc[0], ex.AzimUTM.iloc[0]) == (-58.0, 320.0)
    assert out.groupby("SiteID").DepthAt.is_monotonic_increasing.all()


def test_drift_extrapolation(tables):
    collar, survey = tables
    ex = ds.extrapolate_to_eoh(survey, collar, drift=True)
    row = ex[ex.Method.eq("EXTRAP")].iloc[0]
    assert np.isclose(row.Dip, -57.0) and np.isclose(row.AzimUTM, 322.5)


def test_add_interval_xyz(tables):
    collar, survey = tables
    st = ds.desurvey(ds.extrapolate_to_eoh(survey, collar), collar)
    iv = pd.DataFrame({"SiteID": ["B", "A", "A"], "DepthFrom": [0.0, 90.0, 120.0],
                       "DepthTo": [10.0, 110.0, 130.0]})
    out = ds.add_interval_xyz(iv, st)
    assert len(out) == 3 and out.index.equals(iv.index)
    assert np.allclose(out.loc[0, ["X_mid", "Y_mid", "Z_mid"]].astype(float), [10, 0, 85])
    assert out.survey_extrap.tolist() == [False, True, True]
    assert not out.filter(regex="^[XYZ]_").isna().any().any()
