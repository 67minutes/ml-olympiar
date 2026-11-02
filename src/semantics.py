"""Stage 1 semantics: give every assay value a correct meaning.

A value is either a measurement, "not analysed" (NaN), or "below detection" (censored).
Original columns keep their raw values (except surface 0 -> NaN); everything else is
added as new flag or `_ml` columns.
"""
import re

import numpy as np
import pandas as pd

ANALYTE_RE = re.compile(r"(PPM|PPB|PCT|kgH2SO4/ton)$")
# Unit-suffixed columns that are not analytes, or that duplicate another analyte.
NOT_ANALYTES = {"SizingPCT", "SIZINGPCT", "AuPPB"}

MIN_FLOOR_COUNT = 3     # a floor must repeat at least this many times...
MIN_FLOOR_FRAC = 0.02   # ...and cover at least this share of the job's values
MIN_NEAR_COUNT = 3      # values needed in [2f, 4f] for the DL vs DL/2 gap test
MIN_DL_SHARE = 0.10     # a DL sets the harmonised DL only if its jobs hold this share
MAX_CENS_FRAC = 0.50    # above this share censored, an element is not ML-usable
MIN_COVERAGE = 0.50     # below this share analysed, an element is not ML-usable
STANDARD_DLS = np.array([m * 10.0 ** k for m in (1, 2, 2.5, 5) for k in range(-4, 4)])


def analyte_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if (ANALYTE_RE.search(c) or c == "NAGpH") and c not in NOT_ANALYTES]


def zeros_to_nan(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Surface convention: 0 means 'not analysed'. Returns (new df, zeros per column)."""
    out = df.copy()
    zeros = (out[cols] == 0).sum()
    out[cols] = out[cols].mask(out[cols] == 0)
    return out, zeros


def is_standard(v: float) -> bool:
    return bool(np.isclose(v, STANDARD_DLS, rtol=1e-6).any())


def resolution(values: pd.Series) -> float:
    """Reporting step of a set of values: 10^-k for the fewest decimals k that fit."""
    for k in range(7):
        x = values.to_numpy() * 10 ** k
        if np.allclose(x, np.round(x), atol=1e-6):
            return 10.0 ** -k
    return 1e-7


def dl_or_half(v: pd.Series, f: float) -> tuple[str, str]:
    """Is the stored floor f the DL itself, or an already substituted DL/2?

    Labs never report values between DL/2 and DL. If a value exists strictly between
    f and 2f, f is the DL. If that band is empty while values sit just above it in
    [2f, 4f], f is DL/2. Otherwise fall back on the value pattern (2.5 x 10^k -> DL/2).
    Returns (decision, method).
    """
    above = v[v > f]
    if len(above):
        r = resolution(above)
        first = np.floor(f / r + 1 + 1e-9) * r          # next representable value above f
        if first < 2 * f - 1e-9:                        # the band (f, 2f) can hold values
            if ((v > f) & (v < 2 * f - 1e-9)).any():
                return "DL", "gap"
            if ((v >= 2 * f - 1e-9) & (v <= 4 * f)).sum() >= MIN_NEAR_COUNT:
                return "DL/2", "gap"
    mantissa = f / 10.0 ** np.floor(np.log10(f))
    return ("DL/2" if np.isclose(mantissa, 2.5) else "DL"), "pattern"


def detect_floors(df: pd.DataFrame, cols: list[str], job: str = "LabJobNo") -> pd.DataFrame:
    """Per column x lab job: the minimum value, how often it occurs, whether it is a
    censoring floor (repeats and is a standard lab value), and if so whether the stored
    floor is the DL or DL/2. `true_dl` is the detection limit itself."""
    rows = []
    for c in cols:
        v = df[[job, c]].dropna()
        for j, g in v.groupby(job):
            x = g[c]
            floor = x.min()
            n_at = int((x == floor).sum())
            repeats = n_at >= MIN_FLOOR_COUNT and n_at / len(x) >= MIN_FLOOR_FRAC
            is_dl = repeats and is_standard(floor)
            decision, method = dl_or_half(x, floor) if is_dl else ("", "")
            rows.append(dict(column=c, job=j, n=len(x), floor=floor, n_at_floor=n_at,
                             repeats=repeats, standard_value=is_standard(floor),
                             is_censoring_floor=is_dl,
                             n_between_f_2f=int(((x > floor) & (x < 2 * floor - 1e-9)).sum()),
                             n_in_2f_4f=int(((x >= 2 * floor - 1e-9) & (x <= 4 * floor)).sum()),
                             floor_is=decision, method=method,
                             true_dl=(2 * floor if decision == "DL/2" else floor) if is_dl else np.nan))
    return pd.DataFrame(rows, columns=["column", "job", "n", "floor", "n_at_floor", "repeats",
                                       "standard_value", "is_censoring_floor", "n_between_f_2f",
                                       "n_in_2f_4f", "floor_is", "method", "true_dl"])


def flag_censored(df: pd.DataFrame, floors: pd.DataFrame, job: str = "LabJobNo") -> pd.DataFrame:
    """Add `<col>_cens`: value <= its own job's censoring floor. NA where value is NaN."""
    out = df.copy()
    dl = floors[floors.is_censoring_floor]
    for c in floors.column.unique():
        thr = out[job].map(dl[dl.column == c].set_index("job").floor)
        cens = (out[c] <= thr).fillna(False).astype("boolean")
        out[f"{c}_cens"] = cens.mask(out[c].isna())
    return out


def harmonised_dl(floors: pd.DataFrame, n_analysed: pd.Series,
                  min_share: float = MIN_DL_SHARE) -> pd.Series:
    """Highest true DL whose jobs together hold >= min_share of a column's analysed
    values (NaN if none does)."""
    out = {}
    for c, g in floors.groupby("column", sort=False):
        share = g[g.is_censoring_floor].groupby("true_dl").n.sum() / n_analysed[c]
        ok = share[share >= min_share]
        out[c] = ok.index.max() if len(ok) else np.nan
    return pd.Series(out, dtype=float)


def harmonise(df: pd.DataFrame, floors: pd.DataFrame, dl: pd.Series,
              job: str = "LabJobNo") -> pd.DataFrame:
    """Add `<col>_ml`, `<col>_cens_h` and `<col>_dl_coarse`.

    Values <= harmonised DL -> DL/2. In jobs whose own true DL is coarser than the
    harmonised DL (or when there is none), values at the job floor -> own DL/2.
    Because DLs are true DLs, a floor that already was DL/2 is never halved again.
    """
    out = df.copy()
    fl = floors[floors.is_censoring_floor]
    for c, d in dl.items():
        jf = fl[fl.column == c].set_index("job")
        own_floor = out[job].map(jf.floor)
        own_dl = out[job].map(jf.true_dl)
        coarse = own_dl > d if not np.isnan(d) else own_dl.notna()
        at_coarse = coarse & (out[c] <= own_floor)
        below_h = out[c] <= d if not np.isnan(d) else pd.Series(False, index=out.index)
        ml = out[c].where(~below_h, d / 2)
        ml = ml.where(~at_coarse, own_dl / 2)
        out[f"{c}_ml"] = ml
        isna = out[c].isna()
        out[f"{c}_cens_h"] = (below_h | at_coarse).astype("boolean").mask(isna)
        out[f"{c}_dl_coarse"] = at_coarse.astype("boolean").mask(isna)
    return out


def add_s_method(df: pd.DataFrame) -> pd.DataFrame:
    """Which sulfide-S method a row carries. SCIS and S2 never co-occur (asserted)."""
    scis, s2 = df["SCIS_PCT"].notna(), df["S2_SPCT"].notna()
    assert not (scis & s2).any(), "a row has both SCIS_PCT and S2_SPCT"
    out = df.copy()
    out["S_method"] = np.select([scis, s2], ["SCIS", "S2"], "none")
    return out


def add_cn_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """CN-soluble / total ratios (uncensored pairs only) and CN > 1.1 x total flags
    (all analysed pairs; this is a precision indicator, not a deletion criterion)."""
    out = df.copy()
    for el in ["Au", "Ag", "Cu"]:
        cn, tot = f"{el}CNPPM", f"{el}PPM"
        if cn not in out or tot not in out:
            continue
        pair = out[cn].notna() & out[tot].notna()
        uncens = pair.copy()
        for c in (cn, tot):
            if f"{c}_cens" in out:
                uncens &= ~out[f"{c}_cens"].fillna(False).astype(bool)
        out[f"{el}CN_ratio"] = (out[cn] / out[tot]).where(uncens)
        if el in ("Au", "Ag"):
            flag = (out[cn] > 1.1 * out[tot]).astype("boolean")
            out[f"flag_{el}CN_gt_total"] = flag.mask(~pair)
    return out


def parse_dates(s: pd.Series, fmt: str | None = None, dayfirst: bool = False) -> pd.Series:
    if fmt:
        return pd.to_datetime(s.astype("Int64").astype(str), format=fmt, errors="coerce")
    return pd.to_datetime(s, dayfirst=dayfirst, errors="coerce")


def element_summary(out: pd.DataFrame, cols: list[str], zeros: pd.Series,
                    dl: pd.Series, sensitivity: dict[float, pd.Series]) -> pd.DataFrame:
    """Per column: coverage, harmonised DL, % censored, ML usability, and % censored
    under alternative DL-share thresholds (`sensitivity` = {share: % censored})."""
    rows = []
    n = len(out)
    for c in cols:
        analysed = int(out[c].notna().sum())
        cov = analysed / n
        row = dict(column=c, n_rows=n, n_analysed=analysed, pct_analysed=round(100 * cov, 1),
                   zeros_to_nan=int(zeros.get(c, 0)), harmonised_dl=dl.get(c, np.nan))
        if analysed:
            frac_h = out[f"{c}_cens_h"].sum() / analysed
            row.update(pct_cens_own_job=round(100 * out[f"{c}_cens"].sum() / analysed, 1),
                       pct_cens_harmonised=round(100 * frac_h, 1),
                       n_dl_coarse=int(out[f"{c}_dl_coarse"].sum()),
                       ml_usable=bool(cov >= MIN_COVERAGE and frac_h <= MAX_CENS_FRAC))
        else:
            row.update(ml_usable=False)
        for share, pct in sensitivity.items():
            row[f"pct_cens_at_{int(share * 100)}pct"] = pct.get(c, np.nan)
        rows.append(row)
    return pd.DataFrame(rows)
