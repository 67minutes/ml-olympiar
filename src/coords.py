"""Surface-sample coordinates (Stage 3, AGENTS.md §5.2 and §4.2.6/§4.2.8)."""
import numpy as np
import pandas as pd

from src import dem

UNCERTAIN_M = 10.0   # |Elev - DEM| above this: DEM-uncertain band (Stage 2 human decision)
ERROR_M = 30.0       # above this: confirmed elevation error (stable under TIN and spline)
WEAK_SUPPORT_M = 30.0


def flag_elevation(dz: pd.Series) -> pd.Series:
    a = dz.abs()
    return pd.Series(np.select([a.isna(), a > ERROR_M, a > UNCERTAIN_M],
                               ["no_dem", "elev_error", "dem_uncertain"], "ok"), index=dz.index)


def redrape(df: pd.DataFrame, dem_arr: np.ndarray, support: np.ndarray, transform) -> pd.DataFrame:
    """Z = lidar DEM at the sample; the original elevation is kept as Elev_orig and used
    only where the DEM has no value."""
    df = df.rename(columns={"Elevation": "Elev_orig"}).copy()  # .copy() defragments
    z = dem.sample_bilinear(dem_arr, transform, df.Easting, df.Northing)
    sup = dem.sample_bilinear(support, transform, df.Easting, df.Northing)
    df["Z_dem"] = z
    df["Elev_dz"] = df.Elev_orig - df.Z_dem
    df["Z"] = df.Z_dem.fillna(df.Elev_orig)
    df["flag_elev"] = flag_elevation(df.Elev_dz)
    df["dem_support_m"] = sup
    df["flag_dem_weak"] = sup > WEAK_SUPPORT_M
    return df


def duplicate_xy(df: pd.DataFrame, date: str = "collect_date", job: str = "LabJobNo") -> pd.DataFrame:
    """Group samples that share Easting/Northing (mm). 'resample' = the group spans more
    than one date or lab job (genuine field duplicate); 'same_day_same_point' = possible
    copied coordinate or several samples logged at one GPS fix."""
    df = df.copy()
    key = df.Easting.round(3).astype(str) + "_" + df.Northing.round(3).astype(str)
    n = key.map(key.value_counts())
    dup = n > 1
    gid = pd.Series(pd.factorize(key[dup], sort=True)[0] + 1, index=key[dup].index)
    df["dupxy_group"] = gid.reindex(df.index).astype("Int64")
    df["dupxy_n"] = n
    many = df[dup].groupby(key[dup])[[date, job]].nunique().max(axis=1) > 1
    df["dupxy_type"] = np.where(~dup, "", np.where(key.map(many).fillna(False),
                                                  "resample", "same_day_same_point"))
    return df
