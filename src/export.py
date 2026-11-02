"""Deliverables (Stage 7): validation audit trail, QAQC tables and ioGAS hand-off CSVs."""
import re
from pathlib import Path

import numpy as np
import pandas as pd

FLAG_COLUMNS = ["dataset", "record_id", "site_id", "depth_from", "depth_to", "check_id", "issue", "value",
                "severity", "action", "agents_ref", "note"]
SPECIAL_NAMES = {
    "SCIS_PCT": "S_sulfida_SCIS_pct",
    "S2_SPCT": "S_sulfida_S2_pct",
    "S_PCT": "S_total_pct",
    "NAGpH": "NAG_pH",
    "NAGpH4.5_kgH2SO4/ton": "NAG_pH45_kgH2SO4_t",
    "NAGpH7.0_kgH2SO4/ton": "NAG_pH70_kgH2SO4_t",
}
ELEMENT_RE = re.compile(r"^([A-Z][a-z]?(?:CN)?)(PPM|PCT)$")
EPS = 1e-6


def iogas_name(col: str) -> str:
    """`AuPPM_ml` -> `Au_ppm`: element_unit headers so ioGAS can guess the alias."""
    base = col.removesuffix("_ml")
    if base in SPECIAL_NAMES:
        return SPECIAL_NAMES[base]
    m = ELEMENT_RE.match(base)
    if not m:
        raise KeyError(f"not an analyte column: {col}")
    return f"{m.group(1)}_{m.group(2).lower()}"


def to_yn(s: pd.Series) -> pd.Series:
    """Booleans (also 'True'/'False' text read back from CSV) -> 'Y'/'N', missing -> ''."""
    m = s.astype(object).map(lambda v: "" if pd.isna(v) else {True: "Y", False: "N", "True": "Y",
                                                              "False": "N"}.get(v, "?"))
    if m.eq("?").any():
        raise ValueError(f"non-boolean values: {sorted(s[m.eq('?')].astype(str).unique())[:5]}")
    return m


def long_flags(df: pd.DataFrame, mask, *, dataset: str, check_id: str, issue: str, severity: str,
               action: str, agents_ref: str, value=None, note: str = "") -> pd.DataFrame:
    """One validation_flags row per True in `mask`."""
    mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
    d = df[mask]
    rec = "SampleID" if "SampleID" in d else "SiteID"
    out = pd.DataFrame({
        "dataset": dataset,
        "record_id": d[rec].astype(str),
        "site_id": d["SiteID"] if "SiteID" in d else "",
        "depth_from": d["DepthFrom"] if "DepthFrom" in d else np.nan,
        "depth_to": d["DepthTo"] if "DepthTo" in d else np.nan,
        "check_id": check_id, "issue": issue,
        "value": (value[mask].astype(str) if isinstance(value, pd.Series) else ("" if value is None else str(value))),
        "severity": severity, "action": action, "agents_ref": agents_ref, "note": note,
    }, index=d.index)
    return out[FLAG_COLUMNS].reset_index(drop=True)


def interval_checks(df: pd.DataFrame, collar: pd.DataFrame) -> dict:
    """AGENTS §4.1 clean checks on one downhole interval table."""
    d = df.sort_values(["SiteID", "DepthFrom"])
    nxt = d.groupby("SiteID").DepthFrom.shift(-1)
    eoh = d.SiteID.map(collar.set_index("SiteID").EndDepth)
    return {"overlaps": int((nxt < d.DepthTo - EPS).sum()),
            "gaps": int((nxt > d.DepthTo + EPS).sum()),
            "nonpositive_length": int((d.DepthTo - d.DepthFrom <= EPS).sum()),
            "past_eoh": int((d.DepthTo > eoh + EPS).sum())}


def group_cv(df: pd.DataFrame, group: str, cols: list[str]) -> pd.DataFrame:
    """Per group and column: n, mean, SD (n-1) and CV% (field-duplicate precision)."""
    rows = []
    for g, d in df.groupby(group):
        for c in cols:
            v = d[c].dropna()
            if len(v) < 2:
                continue
            sd = v.std(ddof=1)
            rows.append({group: g, "element": c, "n": len(v), "mean": v.mean(), "sd": sd,
                         "cv_pct": 100 * sd / v.mean()})
    return pd.DataFrame(rows)


def merge_ml(df: pd.DataFrame, key: list[str], ml_dir: Path, target: str) -> pd.DataFrame:
    """Left-join `ML_*` columns from every `<target>__*.csv` in ml_dir (one file per ML
    task and target table, keyed like the target)."""
    out = df
    for f in sorted(Path(ml_dir).glob(f"{target}__*.csv")) if Path(ml_dir).exists() else []:
        m = pd.read_csv(f, low_memory=False)
        if not set(key) <= set(m.columns):
            raise ValueError(f"{f.name}: missing key columns {key}")
        extra = [c for c in m.columns if c not in key]
        if any(not c.startswith("ML_") for c in extra):
            raise ValueError(f"{f.name}: only ML_* columns may be merged, got {extra}")
        if m.duplicated(key).any():
            raise ValueError(f"{f.name}: duplicate keys")
        out = out.merge(m, on=key, how="left", validate="one_to_one")
    assert len(out) == len(df)
    return out
