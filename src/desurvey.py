"""Drillhole desurvey by minimum curvature (Stage 3, AGENTS.md §5.2).

Conventions: Dip is negative downward, AzimUTM is a grid azimuth (degrees clockwise from
UTM grid north), so X = East, Y = North, Z = RL (up). Directions are handled as unit
vectors, so the 0/360 wrap and the azimuth swings of near-vertical holes need no special
case.
"""
import numpy as np
import pandas as pd

EXTRAP = "EXTRAP"


def unit_vectors(dip: np.ndarray, azim: np.ndarray) -> np.ndarray:
    d, a = np.radians(dip), np.radians(azim)
    return np.c_[np.cos(d) * np.sin(a), np.cos(d) * np.cos(a), np.sin(d)]


def _ratio_factor(beta: np.ndarray) -> np.ndarray:
    """Minimum-curvature ratio factor 2/b * tan(b/2); 1 for a straight segment."""
    small = beta < 1e-9
    b = np.where(small, 1.0, beta)
    return np.where(small, 1.0, 2 / b * np.tan(b / 2))


def _dogleg(t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
    return np.arccos(np.clip(np.sum(t1 * t2, axis=-1), -1, 1))


def min_curvature(depth: np.ndarray, dip: np.ndarray, azim: np.ndarray,
                  collar: np.ndarray) -> np.ndarray:
    """XYZ of every survey station; station 0 must be at depth 0 (the collar)."""
    assert depth[0] == 0 and np.all(np.diff(depth) > 0), "stations must start at 0 and increase"
    t = unit_vectors(dip, azim)
    t1, t2 = t[:-1], t[1:]
    step = np.diff(depth)[:, None] / 2 * (t1 + t2) * _ratio_factor(_dogleg(t1, t2))[:, None]
    return np.vstack([collar, collar + np.cumsum(step, axis=0)])


def position_at(depth: np.ndarray, dip: np.ndarray, azim: np.ndarray, xyz: np.ndarray,
                query: np.ndarray) -> np.ndarray:
    """Exact minimum-curvature position at any depth between the first and last station:
    the direction is slerped along the circular arc of its segment."""
    query = np.asarray(query, float)
    if np.any(query < depth[0]) or np.any(query > depth[-1] + 1e-9):
        raise ValueError("query depth outside the surveyed range; extrapolate first")
    t = unit_vectors(dip, azim)
    i = np.clip(np.searchsorted(depth, query, side="right") - 1, 0, len(depth) - 2)
    t1, t2 = t[i], t[i + 1]
    md = query - depth[i]
    f = md / (depth[i + 1] - depth[i])
    beta = _dogleg(t1, t2)
    small = beta < 1e-9
    sb = np.where(small, 1.0, np.sin(beta))
    w1 = np.where(small, 1 - f, np.sin((1 - f) * beta) / sb)
    w2 = np.where(small, f, np.sin(f * beta) / sb)
    tq = w1[:, None] * t1 + w2[:, None] * t2
    return xyz[i] + md[:, None] / 2 * (t1 + tq) * _ratio_factor(f * beta)[:, None]


def _wrapped_diff(a: pd.Series) -> pd.Series:
    return (a.diff() + 180) % 360 - 180


def extrapolate_to_eoh(survey: pd.DataFrame, collar: pd.DataFrame,
                       drift: bool = False) -> pd.DataFrame:
    """Append an EXTRAP station at EndDepth for holes whose last station stops short.
    Default: constant tangent (last measured Dip/Az). drift=True continues the hole's mean
    measured dip and azimuth change per metre instead (used only as an uncertainty check)."""
    survey = survey.sort_values(["SiteID", "DepthAt"])
    eoh = collar.set_index("SiteID")["EndDepth"]
    rows = []
    for site, g in survey.groupby("SiteID"):
        last = g.iloc[-1]
        gap = eoh[site] - last.DepthAt
        if gap <= 0:
            continue
        dip, az = last.Dip, last.AzimUTM
        if drift and len(g) > 1:
            span = last.DepthAt - g.DepthAt.iloc[0]
            dip = max(dip + (last.Dip - g.Dip.iloc[0]) / span * gap, -90.0)
            az = (az + _wrapped_diff(g.AzimUTM).sum() / span * gap) % 360
        rows.append({"SiteID": site, "DepthAt": eoh[site], "Dip": dip, "AzimUTM": az,
                     "Method": EXTRAP})
    out = pd.concat([survey, pd.DataFrame(rows)], ignore_index=True)
    out["survey_extrap"] = out["Method"].eq(EXTRAP)
    return out.sort_values(["SiteID", "DepthAt"], ignore_index=True)


def desurvey(survey: pd.DataFrame, collar: pd.DataFrame) -> pd.DataFrame:
    """Add X, Y, Z to every station (survey already extrapolated to EOH)."""
    c = collar.set_index("SiteID")
    parts = []
    for site, g in survey.groupby("SiteID", sort=False):
        g = g.sort_values("DepthAt").copy()
        start = c.loc[site, ["EastUTM", "NorthUTM", "RLUTM"]].to_numpy(float)
        g[["X", "Y", "Z"]] = min_curvature(g.DepthAt.to_numpy(float), g.Dip.to_numpy(float),
                                           g.AzimUTM.to_numpy(float), start)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def hole_positions(stations: pd.DataFrame, site: str, query) -> np.ndarray:
    g = stations[stations.SiteID.eq(site)]
    return position_at(g.DepthAt.to_numpy(float), g.Dip.to_numpy(float),
                       g.AzimUTM.to_numpy(float), g[["X", "Y", "Z"]].to_numpy(float), query)


def add_interval_xyz(df: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """X/Y/Z at DepthFrom, midpoint and DepthTo, plus survey_extrap (interval reaches
    below the last measured station). Row order and index are preserved."""
    df = df.copy()
    cols = [f"{a}_{p}" for p in ("from", "mid", "to") for a in "XYZ"]
    out = pd.DataFrame(np.nan, index=df.index, columns=cols)
    measured = stations[~stations.survey_extrap].groupby("SiteID").DepthAt.max()
    for site, g in df.groupby("SiteID"):
        for p, d in (("from", g.DepthFrom), ("mid", (g.DepthFrom + g.DepthTo) / 2),
                     ("to", g.DepthTo)):
            out.loc[g.index, [f"X_{p}", f"Y_{p}", f"Z_{p}"]] = hole_positions(stations, site, d)
    df[cols] = out
    df["survey_extrap"] = df.DepthTo > df.SiteID.map(measured)
    return df
