import numpy as np
import pandas as pd
from rasterio.transform import from_origin

from src import coords


def test_flag_elevation():
    dz = pd.Series([0.0, -10.0, 10.5, -29.9, 30.1, np.nan])
    assert coords.flag_elevation(dz).tolist() == [
        "ok", "ok", "dem_uncertain", "dem_uncertain", "elev_error", "no_dem"]


def test_redrape_keeps_original_and_falls_back():
    grid = np.full((10, 10), 400.0)           # flat DEM, cells 10 m, x 0-100, y 0-100
    support = np.full((10, 10), 5.0)
    support[:, 5:] = 50.0
    t = from_origin(0, 100, 10, 10)
    df = pd.DataFrame({"Easting": [20.0, 80.0, 500.0], "Northing": [50.0, 50.0, 50.0],
                       "Elevation": [395.0, 450.0, 380.0]})
    out = coords.redrape(df, grid, support, t)
    assert "Elevation" not in out and out.Elev_orig.tolist() == [395.0, 450.0, 380.0]
    assert out.Z.tolist() == [400.0, 400.0, 380.0]
    assert out.flag_elev.tolist() == ["ok", "elev_error", "no_dem"]
    assert out.flag_dem_weak.tolist() == [False, True, False]
    assert np.isnan(out.Z_dem.iloc[2])


def test_duplicate_xy():
    df = pd.DataFrame({"Easting": [1.0, 1.0, 2.0, 3.0, 3.0, 3.0],
                       "Northing": [5.0, 5.0, 6.0, 7.0, 7.0, 7.0],
                       "collect_date": ["a", "a", "a", "a", "b", "b"],
                       "LabJobNo": ["j", "j", "j", "j", "k", "k"]})
    out = coords.duplicate_xy(df)
    assert out.dupxy_n.tolist() == [2, 2, 1, 3, 3, 3]
    assert out.dupxy_group.isna().tolist() == [False, False, True, False, False, False]
    assert out.dupxy_type.tolist() == ["same_day_same_point"] * 2 + [""] + ["resample"] * 3
