"""Stage 7: deliverables (AGENTS.md §5 "flag, don't delete", §1 deliverables 1-2).
Plan: LOG.md, 2026-11-03 Stage 7 entry.

Collects every flag from Stages 1-6 into data/processed/validation_flags.csv (one row per
record x issue) and validation_summary.csv (one row per check, with the AGENTS §4.1 clean
checks recomputed on the raw tables); writes qaqc_precision.csv, the lab-era figure and
the ioGAS-ready CSVs in data/processed/iogas/. Rerun after each ML stage: it merges
any data/processed/ml/<target>__*.csv `ML_*` columns into the ioGAS files.
Run: uv run python scripts/07_export.py
"""
import re

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from src import export, loaders, paths, semantics

OUT = paths.PROCESSED
IOGAS = OUT / "iogas"
ML_DIR = OUT / "ml"
OX_ID = {"Oxide": "Oksida", "Transition": "Transisi", "Sulphide": "Sulfida"}
NEAR_VERTICAL_DIP = -85.0
AZ_SWING_DEG = 20.0
LONG_SAMPLE_M = 2.0
LOG_TABLES = ["assay", "lithology", "alteration", "mineralisation", "oxide"]
# every flag-type column in the source tables, and where it is reported (inventory guard)
HANDLED = {
    "flag_elev": "S1", "Elev_dz": "S1", "dupxy_type": "S2", "dupxy_group": "S2", "dupxy_n": "S2",
    "is_RJ": "S3", "flag_AuCN_gt_total": "S5/D6", "flag_AgCN_gt_total": "S5/D6",
    "dem_support_m": "Q8", "flag_dem_weak": "Q8", "flag_collar_pad": "D1", "RL_dz": "D1",
    "survey_gap_m": "D2", "eoh_extrap_uncert_m": "D2", "eoh_mincurv_vs_tangential_m": "Q9",
    "eoh_mincurv_vs_balanced_m": "Q9", "no_sample": "D4", "survey_extrap": "D5", "S_method": "D8",
    "flag_ox_conflict": "D9", "ox_state_source": "D10", "min_logged": "D11", "min_missing": "D11",
    "lith_missing": "D12", "lith_mixed": "D12", "alt_missing": "D12", "alt_mixed": "D12",
    "ox_missing": "D12", "ox_mixed": "D12", "min_mixed": "D12", "comp_ok": "Q5", "comp_shared_src": "Q5",
    "S_method_c": "Q5", "comp_cov_m": "Q5", "comp_len": "Q5", "comp_nsrc": "Q5", "comp_src_maxlen": "Q5",
}
FLAG_RE = re.compile(r"^(flag_|dupxy|survey_|no_sample|comp_|.*_missing$|.*_mixed$|min_logged|S_method|"
                     r"ox_state_source|eoh_|RL_dz|Elev_dz|dem_support|is_RJ)")


# --- validation flags -------------------------------------------------------------

def surface_flags(rock: pd.DataFrame, soil: pd.DataFrame) -> list[pd.DataFrame]:
    out = []
    sev = {"elev_error": "error", "dem_uncertain": "warning", "no_dem": "info"}
    act = {"elev_error": "fixed", "dem_uncertain": "fixed", "no_dem": "flagged"}
    for name, d in (("rock", rock), ("soil", soil)):
        for k in sev:
            out.append(export.long_flags(
                d, d.flag_elev.eq(k), dataset=name, check_id="S1", issue=f"elevation vs lidar: {k}",
                severity=sev[k], action=act[k], agents_ref="§4.2.8", value=d.Elev_dz.round(1),
                note="Z re-draped on lidar DEM; Elev_orig kept" if k != "no_dem" else "outside DEM; Z = Elev_orig"))
        for k, sv, note in (("resample", "info", "genuine re-sample (3 dates/jobs): field-duplicate precision"),
                            ("same_day_same_point", "warning",
                             "same date and job: several samples at one GPS fix or copied coordinate")):
            out.append(export.long_flags(d, d.dupxy_type.eq(k), dataset=name, check_id="S2",
                                         issue=f"duplicate XY: {k}", severity=sv, action="flagged",
                                         agents_ref="§4.2.6", value=d.dupxy_group, note=note))
        out.append(export.long_flags(d, ~d.is_RJ.astype(bool), dataset=name, check_id="S3",
                                     issue="sample outside Ramba Joring prospect", severity="info",
                                     action="flagged", agents_ref="§3", value=d.Prospect,
                                     note="kept; RJ analyses filter on prospek_RJ"))
        out += coarse_dl_flags(d, name, "S4")
        out += cn_flags(d, name, "S5")
    return out


def coarse_dl_flags(d: pd.DataFrame, name: str, cid: str) -> list[pd.DataFrame]:
    out = []
    for c in [c for c in d.columns if c.endswith("_dl_coarse")]:
        m = d[c].astype(str).eq("True")
        if m.any():
            out.append(export.long_flags(d, m, dataset=name, check_id=cid,
                                         issue="value at a detection limit coarser than the harmonised DL",
                                         severity="info", action="flagged", agents_ref="§4.2.7",
                                         value=pd.Series(c.removesuffix("_dl_coarse"), index=d.index),
                                         note="_ml set to harmonised DL/2; censored"))
    return out


def cn_flags(d: pd.DataFrame, name: str, cid: str) -> list[pd.DataFrame]:
    out = []
    for el in ("Au", "Ag"):
        f = f"flag_{el}CN_gt_total"
        if f in d:
            out.append(export.long_flags(
                d, d[f].astype(str).eq("True"), dataset=name, check_id=cid,
                issue=f"{el}CN > 1.1 x total {el}", severity="info", action="flagged", agents_ref="§4.2.4",
                value=(d[f"{el}CNPPM"] / d[f"{el}PPM"]).round(2),
                note="aliquot heterogeneity (nugget): precision indicator, not deleted"))
    return out


def drillhole_flags(collar, survey, assay, ox, mineral) -> tuple[list[pd.DataFrame], pd.DataFrame]:
    out = [export.long_flags(collar, collar.flag_collar_pad.astype(bool), dataset="collar", check_id="D1",
                             issue="collar RL below lidar (pad cut)", severity="warning", action="flagged",
                             agents_ref="§4.1", value=collar.RL_dz.round(1), note="RL not changed")]
    for big, sev in ((True, "warning"), (False, "info")):
        gap = (collar.survey_gap_m >= 1.0) if big else collar.survey_gap_m.between(0, 1.0, inclusive="neither")
        out.append(export.long_flags(
            collar, gap, dataset="collar", check_id="D2",
            issue="downhole survey stops before EOH" + ("" if big else " (< 1 m)"),
            severity=sev, action="fixed", agents_ref="§4.2.11",
            value=collar.survey_gap_m.round(1).astype(str) + " m gap; EOH uncertainty "
            + collar.eoh_extrap_uncert_m.round(2).astype(str) + " m",
            note="last station extrapolated to EOH; intervals below flagged survey_extrap"))
    sv = survey[~survey.survey_extrap.astype(bool)].sort_values(["SiteID", "DepthAt"]).copy()
    daz = sv.groupby("SiteID").AzimUTM.diff().abs()
    sv["daz"] = np.minimum(daz, 360 - daz)
    swing = (sv.daz > AZ_SWING_DEG) & (sv.Dip <= NEAR_VERTICAL_DIP)
    assert not ((sv.daz > AZ_SWING_DEG) & (sv.Dip > NEAR_VERTICAL_DIP)).any(), "azimuth swing in a non-vertical hole"
    sv["DepthFrom"] = sv["DepthTo"] = sv.DepthAt
    out.append(export.long_flags(
        sv, swing, dataset="survey", check_id="D3", issue="azimuth swing at near-vertical dip",
        severity="info", action="none", agents_ref="§4.2.12", value=sv.daz.round(1),
        note="azimuth is ill-defined near vertical: instrument behaviour, not corrected"))
    out.append(export.long_flags(assay, assay.no_sample.astype(bool), dataset="assay", check_id="D4",
                                 issue="interval not sampled (NS-SEL)", severity="info",
                                 action="excluded_in_analysis", agents_ref="§4.2.2", note="no assay values"))
    out.append(export.long_flags(assay, assay.survey_extrap.astype(bool), dataset="assay", check_id="D5",
                                 issue="interval below last measured survey station", severity="info",
                                 action="flagged", agents_ref="§4.2.11", note="XYZ from extrapolated survey"))
    out += cn_flags(assay, "assay", "D6")
    out += coarse_dl_flags(assay, "assay", "D7")
    holes = hole_table(collar, assay, ox)
    out.append(export.long_flags(holes, holes.S_issue.ne(""), dataset="assay", check_id="D8",
                                 issue="sulfur method", severity="warning", action="flagged",
                                 agents_ref="§4.2.10", value=holes.S_issue,
                                 note="SCIS and S2 never in the same row; never mixed silently"))
    ox = ox.assign(value=ox.ox_state.astype(str) + " at " + ox.WRAltOxidPcnt.astype(str) + "% oxidised")
    out.append(export.long_flags(ox, ox.flag_ox_conflict.astype(bool), dataset="oxide", check_id="D9",
                                 issue="oxidation label conflicts with logged % oxidised", severity="warning",
                                 action="flagged", agents_ref="Stage 4", value=ox.value,
                                 note="label kept as logged"))
    out.append(export.long_flags(holes, holes.ox_derived.ne(""), dataset="oxide", check_id="D10",
                                 issue="no oxidation label logged in this hole", severity="warning",
                                 action="fixed", agents_ref="Stage 4", value=holes.ox_derived,
                                 note="ox_state_derived from % oxidised (LOHO-tested); not used as ML labels"))
    out.append(export.long_flags(mineral, mineral.DomMin1_h.eq("um"), dataset="mineralisation",
                                 check_id="D11", issue="no mineral logged (um)", severity="info",
                                 action="flagged", agents_ref="Stage 5", note="mineral flags NA, not False"))
    out.append(export.long_flags(assay, assay.min_missing.astype(bool), dataset="assay", check_id="D11",
                                 issue="mineralisation log does not cover this interval", severity="info",
                                 action="flagged", agents_ref="Stage 5", note="mineral flags NA"))
    for p, key in (("lith", "Lith_group"), ("alt", "AltFacies"), ("ox", "ox_state"), ("min", "DomMin1_h")):
        out.append(export.long_flags(assay, assay[f"{p}_mixed"].astype(bool), dataset="assay", check_id="D12",
                                     issue=f"assay spans more than one logged {key}", severity="info",
                                     action="flagged", agents_ref="Stage 5",
                                     note="label taken at the midpoint"))
    L = assay.DepthTo - assay.DepthFrom
    out.append(export.long_flags(assay, (L > LONG_SAMPLE_M) & ~assay.no_sample.astype(bool), dataset="assay",
                                 check_id="D13", issue=f"sampled interval longer than {LONG_SAMPLE_M:g} m",
                                 severity="info", action="flagged", agents_ref="§4.2.13", value=L.round(2),
                                 note="split across 1 m composites (comp_shared_src)"))
    out.append(export.long_flags(holes, holes.SiteID.notna(), dataset="assay", check_id="D14",
                                 issue="lab year of the hole (era and location confounded)", severity="info",
                                 action="none", agents_ref="§4.2.14", value=holes.era,
                                 note="each hole assayed in one year: lab bias cannot be separated from location"))
    return out, holes


def hole_table(collar, assay, ox) -> pd.DataFrame:
    h = collar[["SiteID"]].copy()
    meth = assay[~assay.no_sample.astype(bool)].groupby("SiteID").S_method.value_counts().unstack(fill_value=0)
    def s_issue(site):
        m = meth.loc[site]
        if m.get("SCIS", 0) == 0 and m.get("S2", 0) == 0:
            return "no sulfur analysed"
        return "; ".join(f"{k} {int(m[k])}" for k in ("S2", "none") if m.get(k, 0) > 0 and k == "S2") \
            if m.get("S2", 0) > 0 else ""
    h["S_issue"] = h.SiteID.map(s_issue)
    der = ox[ox.ox_state.isna()].groupby("SiteID").ox_state_derived.value_counts().unstack(fill_value=0)
    h["ox_derived"] = h.SiteID.map(lambda s: ", ".join(f"{k} {int(v)}" for k, v in der.loc[s].items())
                                   if s in der.index else "")
    yr = assay.groupby("SiteID").year.agg(lambda y: "/".join(str(int(v)) for v in sorted(y.dropna().unique())))
    med = assay[~assay.no_sample.astype(bool)].groupby("SiteID").AuPPM.median()
    h["lab_year"] = h.SiteID.map(yr)
    h["era"] = "year " + h.lab_year + "; median Au " + h.SiteID.map(med).round(3).astype(str) + " ppm"
    return h


# --- summary ----------------------------------------------------------------------

CHECKS = {  # check_id: (dataset, description, rule, action, output columns)
    "S1": ("rock/soil", "Surface elevation vs lidar DEM", "|Elev - DEM| > 10 m warning, > 30 m error",
           "fixed (re-drape), original kept", "Z, Elev_orig, Elev_dz, flag_elev"),
    "S2": ("rock/soil", "Samples sharing XY", "same Easting/Northing (mm)", "flagged",
           "dupxy_group, dupxy_type"),
    "S3": ("rock/soil", "Samples outside Ramba Joring", "Prospect != Ramba Joring", "flagged", "prospek_RJ"),
    "S4": ("rock/soil", "Values at a coarse detection limit", "floor > harmonised DL", "flagged, censored",
           "<el>_cens"),
    "S5": ("rock/soil", "CN-soluble > 1.1 x total", "AuCN or AgCN > 1.1 x total", "flagged",
           "flag_AuCN_gt_total"),
    "D1": ("collar", "Collar RL vs lidar", "RL below DEM by > 5 m (pad cut)", "flagged", "flag_collar_pad"),
    "D2": ("collar", "Survey stops before EOH", "last station < EndDepth", "fixed (extrapolated), flagged",
           "survey_gap_m, survey_extrap"),
    "D3": ("survey", "Azimuth swings in near-vertical holes",
           f"azimuth change > {AZ_SWING_DEG:g} deg at dip <= {NEAR_VERTICAL_DIP:g}", "explained, not corrected", ""),
    "D4": ("assay", "Intervals not sampled", "SampleType NS-SEL", "excluded in analysis", "NS_SEL"),
    "D5": ("assay", "Intervals below last survey station", "DepthTo > last measured station", "flagged",
           "survey_extrap"),
    "D6": ("assay", "CN-soluble > 1.1 x total", "AuCN or AgCN > 1.1 x total", "flagged (precision)",
           "flag_AuCN_gt_total, flag_AgCN_gt_total"),
    "D7": ("assay", "Values at a coarse detection limit", "floor > harmonised DL", "flagged, censored",
           "<el>_cens"),
    "D8": ("assay", "Sulfur method per hole", "S2 used or no sulfur", "flagged; methods kept apart",
           "S_metode"),
    "D9": ("oxide", "Oxidation label vs % oxidised", "Sulphide >= 90% or Oxide = 0%", "flagged",
           "flag_ox_conflict"),
    "D10": ("oxide", "Hole without oxidation label", "no logged label", "derived column added",
            "Status_Oksidasi_turunan"),
    "D11": ("mineralisation", "Mineralisation not logged", "um interval or no interval", "flagged",
            "min_logged"),
    "D12": ("assay", "Assay spans several logged units", "> 1 distinct label", "flagged", "*_mixed"),
    "D13": ("assay", "Long sampled intervals", f"> {LONG_SAMPLE_M:g} m", "flagged", ""),
    "D14": ("assay", "Lab year by hole", "one lab year per hole", "explained", "Tahun_lab"),
}


def summary(flags: pd.DataFrame, n_records: dict, extra: list[dict]) -> pd.DataFrame:
    rows = []
    for cid, (ds, desc, rule, action, cols) in CHECKS.items():
        f = flags[flags.check_id.eq(cid)]
        info = f.severity.eq("info").all() if len(f) else False
        rows.append({"check_id": cid, "dataset": ds, "description": desc, "rule": rule,
                     "n_records": n_records[cid], "n_flagged": len(f),
                     "result": "pass" if len(f) == 0 else ("info" if info else "flagged"),
                     "action": action, "output_columns": cols,
                     "detail": "; ".join(f"{k} {v}" for k, v in f.issue.value_counts().items()),
                     "agents_ref": f.agents_ref.iloc[0] if len(f) else ""})
    return pd.DataFrame(rows + extra)


def clean_checks(raw: dict, raw_rock, raw_soil) -> tuple[list[dict], bool]:
    rows, ok = [], True
    collar = raw["collar"]
    for t in LOG_TABLES:
        c = export.interval_checks(raw[t], collar)
        ok &= not any(c.values())
        rows.append({"check_id": "C1", "dataset": t, "description": "Interval integrity (raw table)",
                     "rule": "no overlaps, gaps, zero/negative lengths or depths past EndDepth",
                     "n_records": len(raw[t]), "n_flagged": sum(c.values()),
                     "result": "pass" if not any(c.values()) else "flagged", "action": "none",
                     "detail": ", ".join(f"{k} {v}" for k, v in c.items()), "agents_ref": "§4.1"})
    for name, d in (("assay", raw["assay"]), ("rock", raw_rock), ("soil", raw_soil)):
        n = int(d.SampleID.duplicated().sum())
        ok &= n == 0
        rows.append({"check_id": "C2", "dataset": name, "description": "Duplicate SampleID", "rule": "unique",
                     "n_records": len(d), "n_flagged": n, "result": "pass" if n == 0 else "flagged",
                     "action": "none", "agents_ref": "§4.1"})
    first = raw["survey"].sort_values("DepthAt").groupby("SiteID").first()
    cc = collar.set_index("SiteID")
    bad = int(((cc.Dip - first.Dip).abs().gt(EPS_DEG) | (cc.AzimUTM - first.AzimUTM).abs().gt(EPS_DEG)).sum())
    ok &= bad == 0
    rows.append({"check_id": "C3", "dataset": "collar", "description": "Collar dip/azimuth = first survey station",
                 "rule": "equal", "n_records": len(cc), "n_flagged": bad, "result": "pass" if bad == 0 else "flagged",
                 "action": "none", "agents_ref": "§4.1"})
    return rows, ok


EPS_DEG = 1e-6


def dataset_rows(raw_assay, raw_rock, raw_soil, es, dictionary, comp, rock, soil) -> list[dict]:
    rows = []
    rep = [c for c in raw_assay.columns if "Rpt" in c or "Split" in c]
    qc_types = raw_assay.SampleType.str.contains("STD|BLK|BLANK|DUP|CRM", case=False, na=False).sum()
    rows.append({"check_id": "Q1", "dataset": "assay/rock/soil", "description": "QAQC samples in the database",
                 "rule": "standards, blanks, duplicates, repeats", "n_records": len(raw_assay),
                 "n_flagged": int(qc_types), "result": "flagged",
                 "detail": f"no standard, blank or duplicate samples (SampleType "
                           f"{sorted(raw_assay.SampleType.unique())}); repeat/split columns {rep} all empty: "
                           f"{all(raw_assay[c].isna().all() for c in rep)}. Lab accuracy and precision "
                           f"cannot be measured directly",
                 "action": "internal checks used instead (S2, D6, qaqc_precision.csv)", "agents_ref": "§4.2.3"})
    for name, d in (("rock", raw_rock), ("soil", raw_soil)):
        cols = semantics.analyte_columns(d)
        z = int(d[cols].eq(0).sum().sum())
        rows.append({"check_id": "Q2", "dataset": name, "description": "Zero = not analysed",
                     "rule": "assay value exactly 0", "n_records": int(d[cols].size), "n_flagged": z,
                     "result": "flagged", "action": "fixed: 0 -> blank (not analysed)", "agents_ref": "§4.2.1"})
    for r in es[es.n_analysed > 0].itertuples():
        rows.append({"check_id": "Q3", "dataset": r.dataset, "description": f"Censoring: {r.column}",
                     "rule": "harmonised DL, values below set to DL/2", "n_records": int(r.n_analysed),
                     "n_flagged": int(round(r.n_analysed * (r.pct_cens_harmonised or 0) / 100))
                     if pd.notna(r.pct_cens_harmonised) else 0,
                     "result": "info",
                     "detail": f"harmonised DL {r.harmonised_dl}; {r.pct_cens_harmonised}% censored; "
                               f"ML-usable {r.ml_usable}",
                     "action": "harmonised; <el>_cens flag", "agents_ref": "§4.2.7"})
    src = dictionary.drop_duplicates(["vocabulary", "code"]).source.value_counts().to_dict()
    merged = int(dictionary.raw_variants.str.contains("/").sum())
    rows.append({"check_id": "Q4", "dataset": "logs/rock", "description": "Inconsistent codes",
                 "rule": "case variants; codes undefined in the resume", "n_records": len(dictionary),
                 "n_flagged": int(src.get("VERIFY", 0)), "result": "flagged",
                 "detail": f"{merged} case variants merged; sources {src}",
                 "action": "harmonised (_h columns); see code_dictionary.csv", "agents_ref": "§4.2.9"})
    rows.append({"check_id": "Q5", "dataset": "composites", "description": "1 m composites usable",
                 "rule": "sampled length >= 0.5 m", "n_records": len(comp),
                 "n_flagged": int((~comp.comp_ok.astype(bool)).sum()), "result": "info",
                 "detail": f"comp_shared_src {int(comp.comp_shared_src.astype(bool).sum())} "
                           f"(value repeated from a sample > 1 m)",
                 "action": "comp_ok used by ML", "agents_ref": "§4.2.13"})
    rows.append({"check_id": "Q6", "dataset": "rock", "description": "Field-duplicate precision",
                 "rule": "CV% within duplicate-XY groups", "n_records": int(rock.dupxy_group.notna().sum()),
                 "n_flagged": 0, "result": "info", "detail": "see qaqc_precision.csv",
                 "action": "reported", "agents_ref": "§4.2.6"})
    rows.append({"check_id": "Q7", "dataset": "assay", "description": "CN-soluble vs total pairs",
                 "rule": "CN/total ratio distribution", "n_records": 0, "n_flagged": 0, "result": "info",
                 "detail": "see qaqc_precision.csv", "action": "reported", "agents_ref": "§4.2.4/§4.2.5"})
    weak = int(rock.flag_dem_weak.astype(bool).sum() + soil.flag_dem_weak.astype(bool).sum())
    rows.append({"check_id": "Q8", "dataset": "rock/soil", "description": "Sample on weakly supported DEM",
                 "rule": "> 30 m from a contour", "n_records": len(rock) + len(soil), "n_flagged": weak,
                 "result": "pass" if weak == 0 else "flagged", "action": "none", "agents_ref": "Stage 2"})
    return rows


def precision(rock: pd.DataFrame, assay: pd.DataFrame) -> pd.DataFrame:
    d = rock[rock.dupxy_group.notna()]
    cv = export.group_cv(d, "dupxy_group", ["AuPPM", "CuPPM", "AsPPM"])
    cv["group_type"] = cv.dupxy_group.map(d.groupby("dupxy_group").dupxy_type.first())
    cv.insert(0, "section", "field_duplicate_xy")
    avg = cv.groupby(["group_type", "element"]).cv_pct.agg(["size", "mean"]).reset_index()
    avg = avg.rename(columns={"size": "n", "mean": "cv_pct"}).assign(section="field_duplicate_xy_average_cv",
                                                                       dupxy_group="all")
    rows = []
    for el in ("Au", "Ag", "Cu"):
        cn, tot = f"{el}CNPPM", f"{el}PPM"
        p = assay[assay[cn].notna() & assay[tot].notna() & (assay[tot] > 0)]
        r = p[cn] / p[tot]
        rows.append({"section": "cn_vs_total", "element": f"{el}CN/{el}", "n": len(p),
                     "share_gt_1.1": round((r > 1.1).mean(), 3),
                     **{f"q{int(q * 100):02d}": round(r.quantile(q), 3) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}})
    return pd.concat([cv, avg, pd.DataFrame(rows)], ignore_index=True)


def era_figure(comp: pd.DataFrame, holes: pd.DataFrame) -> pd.DataFrame:
    c = comp[comp.comp_ok.astype(bool) & comp.AuPPM_ml.notna()]
    order = sorted(c.SiteID.unique())
    yr = holes.set_index("SiteID").lab_year
    years = sorted(yr.unique())
    cmap = dict(zip(years, plt.cm.viridis(np.linspace(0, 0.9, len(years)))))
    fig, ax = plt.subplots(figsize=(11, 5))
    bp = ax.boxplot([c.loc[c.SiteID.eq(s), "AuPPM_ml"] for s in order], tick_labels=[s[-3:] for s in order],
                    patch_artist=True, showfliers=False, medianprops={"color": "black"})
    for patch, s in zip(bp["boxes"], order):
        patch.set_facecolor(cmap[yr[s]])
    handles = [Patch(facecolor=cmap[y], edgecolor="black", label=y) for y in years]
    ax.set_yscale("log")
    ax.set_xlabel("Lubang bor (RJDH-)")
    ax.set_ylabel("Au komposit 1 m (ppm, skala log)")
    ax.set_title("Au per lubang bor menurut tahun analisis laboratorium", pad=34)
    ax.legend(handles=handles, title="Tahun lab", fontsize=8, title_fontsize=8, ncol=len(years),
              loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False)
    ax.grid(axis="y", alpha=0.3)
    path = paths.FIGURES / "07_au_lubang_tahun_v1.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return c.groupby(c.SiteID.map(yr)).AuPPM_ml.agg(["size", "median"])


# --- ioGAS ------------------------------------------------------------------------

def elements(df: pd.DataFrame, cens_suffix: str = "_cens_h") -> tuple[pd.DataFrame, dict]:
    """Harmonised analytes as `El_unit` columns (+ `_cens` Y/N where any is censored)."""
    out, src = {}, {}
    for c in [c for c in df.columns if c.endswith("_ml") and df[c].notna().any()]:
        n = export.iogas_name(c)
        out[n] = df[c]
        src[n] = c
        base = c.removesuffix("_ml")
        cc = f"{base}{cens_suffix}"
        if cc in df and df[cc].astype(str).eq("True").any():
            out[f"{n}_cens"] = export.to_yn(df[cc])
            src[f"{n}_cens"] = cc
    return pd.DataFrame(out, index=df.index), src


def labels(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in ("Lith1Interp", "Lith_group_id", "AltFacies", "Alt_facies_id", "alt_ml_label"):
        out[c] = df[c]
    out = out.rename(columns={"Lith_group_id": "Kelompok_Litologi", "Alt_facies_id": "Fasies_Alterasi"})
    out["Status_Oksidasi"] = df.ox_state.map(OX_ID)
    out["Status_Oksidasi_turunan"] = df.ox_state_derived.map(OX_ID)
    out["Oksidasi_pct"] = df.WRAltOxidPcnt_lw.round(1)
    out["Mineral_dominan"] = df.DomMin1_h
    for c in ["min_logged", "min_py", "min_cu", "min_fe_ox", "min_ja", "min_su", "min_al",
              "lith_mixed", "alt_mixed", "ox_mixed", "min_mixed", "flag_ox_conflict"]:
        out[c] = export.to_yn(df[c])
    return out


def ratios(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({f"{el}CN_{el}_rasio": df[f"{el}CN_ratio"] for el in ("Au", "Ag", "Cu")})


def iogas_tables(assay, comp, rock, soil, collar, survey, holes) -> dict:
    yr = holes.set_index("SiteID").lab_year
    a_el, a_src = elements(assay)
    a = pd.concat([pd.DataFrame({
        "HoleID": assay.SiteID, "From": assay.DepthFrom, "To": assay.DepthTo, "SampleID": assay.SampleID,
        "X": assay.X_mid.round(2), "Y": assay.Y_mid.round(2), "Z": assay.Z_mid.round(2),
        "SampleType": assay.SampleType, "LabJobNo": assay.LabJobNo, "Tahun_lab": assay.year,
        "NS_SEL": export.to_yn(assay.no_sample), "survey_extrap": export.to_yn(assay.survey_extrap),
        "S_metode": assay.S_method,
        "flag_AuCN_gt_total": export.to_yn(assay.flag_AuCN_gt_total),
        "flag_AgCN_gt_total": export.to_yn(assay.flag_AgCN_gt_total)}), a_el, ratios(assay), labels(assay)], axis=1)
    c_el, c_src = elements(comp)
    cf = {export.iogas_name(c.removesuffix("_cens_frac")) + "_cens_frac": comp[c].round(3)
          for c in comp.columns if c.endswith("_cens_frac")}
    k = pd.concat([pd.DataFrame({
        "HoleID": comp.SiteID, "From": comp.DepthFrom, "To": comp.DepthTo,
        "X": comp.X_mid.round(2), "Y": comp.Y_mid.round(2), "Z": comp.Z_mid.round(2),
        "Tahun_lab": comp.SiteID.map(yr), "Panjang_komposit": comp.comp_len, "comp_cov_m": comp.comp_cov_m.round(3),
        "comp_ok": export.to_yn(comp.comp_ok), "comp_shared_src": export.to_yn(comp.comp_shared_src),
        "survey_extrap": export.to_yn(comp.survey_extrap), "S_metode": comp.S_method_c}),
        c_el, pd.DataFrame(cf), ratios(comp), labels(comp)], axis=1)
    surf = {}
    for name, d in (("batuan", rock), ("tanah", soil)):
        el, src = elements(d)
        base = pd.DataFrame({
            "SampleID": d.SampleID.astype(str), "X": d.Easting, "Y": d.Northing, "Z": d.Z.round(2),
            "Elev_orig": d.Elev_orig, "Prospek": d.Prospect, "prospek_RJ": export.to_yn(d.is_RJ),
            "SampleType": d.SampleType, "LabJobNo": d.LabJobNo, "Tahun": d.year, "flag_elev": d.flag_elev,
            "dupxy_group": d.dupxy_group.astype("Int64"), "dupxy_type": d.dupxy_type})
        if name == "batuan":
            base["Lithology"] = d.Lithology
            base["Kelompok_Litologi"] = d.Lith_group_id
            base["IntrpAltFa"] = d.IntrpAltFa
            base["Fasies_Alterasi"] = d.Alt_facies_id
            base["flag_AuCN_gt_total"] = export.to_yn(d.flag_AuCN_gt_total)
            base["flag_AgCN_gt_total"] = export.to_yn(d.flag_AgCN_gt_total)
            parts = [base, el, ratios(d)]
        else:
            parts = [base, el]
        surf[name] = (pd.concat(parts, axis=1), src)
    col = pd.DataFrame({
        "HoleID": collar.SiteID, "X": collar.EastUTM, "Y": collar.NorthUTM, "Z": collar.RLUTM,
        "EndDepth": collar.EndDepth, "Dip": collar.Dip, "AzimUTM": collar.AzimUTM, "Tahun_lab": collar.SiteID.map(yr),
        "Z_dem": collar.Z_dem.round(2), "RL_dz": collar.RL_dz.round(2),
        "flag_collar_pad": export.to_yn(collar.flag_collar_pad), "survey_gap_m": collar.survey_gap_m,
        "eoh_extrap_uncert_m": collar.eoh_extrap_uncert_m.round(2)})
    sv = pd.DataFrame({
        "HoleID": survey.SiteID, "Depth": survey.DepthAt, "Dip": survey.Dip, "AzimUTM": survey.AzimUTM,
        "Method": survey.Method, "survey_extrap": export.to_yn(survey.survey_extrap),
        "X": survey.X.round(2), "Y": survey.Y.round(2), "Z": survey.Z.round(2)})
    return {
        "RJ_DH_assay": (a, a_src, ["SampleID"], "assay"),
        "RJ_DH_komposit_1m": (k, c_src, ["HoleID", "From"], "komposit"),
        "RJ_batuan": (*surf["batuan"], ["SampleID"], "batuan"),
        "RJ_tanah": (*surf["tanah"], ["SampleID"], "tanah"),
        "RJ_DH_collar": (col, {}, ["HoleID"], "collar"),
        "RJ_DH_survey": (sv, {}, ["HoleID", "Depth"], "survey"),
    }


DESCRIPTIONS = {  # column: (meaning_en, meaning_id, unit)
    "HoleID": ("drillhole ID", "ID lubang bor", ""), "From": ("interval top depth", "kedalaman atas interval", "m"),
    "To": ("interval bottom depth", "kedalaman bawah interval", "m"),
    "SampleID": ("sample ID", "ID sampel", ""),
    "X": ("Easting UTM 47N (downhole: interval midpoint)", "Easting UTM 47N (bor: titik tengah interval)", "m"),
    "Y": ("Northing UTM 47N", "Northing UTM 47N", "m"),
    "Z": ("elevation (surface: lidar re-drape)", "elevasi (permukaan: diproyeksikan ke lidar)", "m"),
    "Elev_orig": ("original surface elevation", "elevasi asli permukaan", "m"),
    "SampleType": ("sample type", "jenis sampel", ""), "LabJobNo": ("lab job", "nomor job lab", ""),
    "Tahun_lab": ("lab year", "tahun analisis lab", ""), "Tahun": ("lab year", "tahun analisis lab", ""),
    "NS_SEL": ("not sampled", "tidak disampel", "Y/N"),
    "survey_extrap": ("below last measured survey station", "di bawah stasiun survei terakhir", "Y/N"),
    "S_metode": ("sulfide-S method (SCIS / S2 / mixed / none)", "metode S sulfida", ""),
    "flag_AuCN_gt_total": ("AuCN > 1.1 x Au", "AuCN > 1,1 x Au", "Y/N"),
    "flag_AgCN_gt_total": ("AgCN > 1.1 x Ag", "AgCN > 1,1 x Ag", "Y/N"),
    "AuCN_Au_rasio": ("CN-soluble / total Au", "rasio Au larut sianida / total", ""),
    "AgCN_Ag_rasio": ("CN-soluble / total Ag", "rasio Ag larut sianida / total", ""),
    "CuCN_Cu_rasio": ("CN-soluble / total Cu (oxide/supergene indicator)",
                      "rasio Cu larut sianida / total (indikator oksida/supergen)", ""),
    "Lith1Interp": ("logged lithology code", "kode litologi log", ""),
    "Kelompok_Litologi": ("lithology group", "kelompok litologi", ""),
    "Lithology": ("logged lithology code", "kode litologi", ""),
    "AltFacies": ("logged alteration facies code", "kode fasies alterasi", ""),
    "IntrpAltFa": ("alteration facies code", "kode fasies alterasi", ""),
    "Fasies_Alterasi": ("alteration facies", "fasies alterasi", ""),
    "alt_ml_label": ("alteration label for ML (UA removed)", "label alterasi untuk ML", ""),
    "Status_Oksidasi": ("logged oxidation state", "status oksidasi (log)", ""),
    "Status_Oksidasi_turunan": ("oxidation state derived from % oxidised", "status oksidasi turunan dari % oksidasi", ""),
    "Oksidasi_pct": ("logged % oxidised, length-weighted", "% oksidasi (rerata tertimbang panjang)", "%"),
    "Mineral_dominan": ("dominant mineral code", "kode mineral dominan", ""),
    "min_logged": ("mineralisation logged", "mineralisasi dilog", "Y/N"),
    "min_py": ("pyrite logged", "pirit dilog", "Y/N"), "min_cu": ("Cu sulfide/sulfosalt logged", "mineral Cu dilog", "Y/N"),
    "min_fe_ox": ("Fe oxide logged", "oksida besi dilog", "Y/N"), "min_ja": ("jarosite logged", "jarosit dilog", "Y/N"),
    "min_su": ("native sulfur logged", "belerang native dilog", "Y/N"), "min_al": ("alunite logged", "alunit dilog", "Y/N"),
    "lith_mixed": ("interval spans > 1 lithology group", "interval melewati > 1 litologi", "Y/N"),
    "alt_mixed": ("interval spans > 1 alteration facies", "interval melewati > 1 alterasi", "Y/N"),
    "ox_mixed": ("interval spans > 1 oxidation state", "interval melewati > 1 status oksidasi", "Y/N"),
    "min_mixed": ("interval spans > 1 dominant mineral", "interval melewati > 1 mineral dominan", "Y/N"),
    "flag_ox_conflict": ("oxidation label conflicts with %", "label oksidasi bertentangan dengan %", "Y/N"),
    "Panjang_komposit": ("composite length", "panjang komposit", "m"),
    "comp_cov_m": ("sampled length in composite", "panjang tersampel dalam komposit", "m"),
    "comp_ok": ("composite usable (>= 0.5 m sampled)", "komposit layak (>= 0,5 m tersampel)", "Y/N"),
    "comp_shared_src": ("value repeated from one sample > 1 m", "nilai berulang dari satu sampel > 1 m", "Y/N"),
    "Prospek": ("prospect", "prospek", ""), "prospek_RJ": ("Ramba Joring prospect", "prospek Ramba Joring", "Y/N"),
    "flag_elev": ("elevation vs lidar (ok/dem_uncertain/elev_error/no_dem)", "elevasi vs lidar", ""),
    "dupxy_group": ("duplicate-XY group", "grup XY ganda", ""),
    "dupxy_type": ("duplicate-XY type", "jenis XY ganda", ""),
    "EndDepth": ("end of hole depth", "kedalaman akhir lubang", "m"), "Dip": ("dip", "kemiringan", "deg"),
    "AzimUTM": ("azimuth (UTM grid)", "azimut (grid UTM)", "deg"), "Depth": ("survey depth", "kedalaman survei", "m"),
    "Method": ("survey method", "metode survei", ""), "Z_dem": ("lidar elevation at collar", "elevasi lidar di collar", "m"),
    "RL_dz": ("collar RL minus lidar", "RL collar dikurangi lidar", "m"),
    "flag_collar_pad": ("collar below lidar (pad cut)", "collar di bawah lidar (pad)", "Y/N"),
    "survey_gap_m": ("survey gap above EOH", "celah survei di atas EOH", "m"),
    "eoh_extrap_uncert_m": ("EOH position uncertainty", "ketidakpastian posisi EOH", "m"),
}


def describe(col: str, src: dict) -> tuple[str, str, str]:
    if col in DESCRIPTIONS:
        return DESCRIPTIONS[col]
    if col.startswith("ML_"):
        return ("ML output (see LOG.md)", "keluaran ML (lihat LOG.md)", "")
    if col.endswith("_cens_frac"):
        e = col.removesuffix("_cens_frac")
        return (f"{e}: censored share of composite length", f"{e}: proporsi tersensor", "")
    if col.endswith("_cens"):
        e = col.removesuffix("_cens")
        return (f"{e} below detection (value = DL/2)", f"{e} di bawah batas deteksi (nilai = DL/2)", "Y/N")
    unit = col.rsplit("_", 1)[-1]
    return (f"{col.rsplit('_', 1)[0]}, harmonised DL (censored = DL/2); source {src.get(col, '')}",
            f"{col.rsplit('_', 1)[0]}, DL diseragamkan (tersensor = DL/2)", unit if unit in ("ppm", "pct", "pH") else "")


def check_iogas(name: str, t: pd.DataFrame, src: dict, source_df: pd.DataFrame, key: list[str]) -> list[str]:
    bad = []
    if len(t) != len(source_df):
        bad.append("row count")
    if t.duplicated(key).any():
        bad.append("duplicate key")
    if not t.columns.is_unique:
        bad.append("duplicate header")
    if any((not c.isascii()) or re.search(r"[\s/,]", c) for c in t.columns):
        bad.append("header not ASCII/clean")
    for c in t.columns[t.dtypes.eq(object)]:
        if not t[c].dropna().astype(str).map(str.isascii).all():
            bad.append(f"non-ASCII text in {c}")
    for c, s in src.items():
        if c.endswith("_cens"):
            if not t[c].isin(["Y", "N", ""]).all():
                bad.append(f"{c} not Y/N")
        elif not np.allclose(t[c].to_numpy(float), source_df[s].to_numpy(float), equal_nan=True):
            bad.append(f"{c} differs from {s}")
    return [f"{name}: {b}" for b in bad]


def readme(tables: dict) -> str:
    lines = [
        "ioGAS input tables: Ramba Joring (OlympiAR 2026 Round 2). Generated by scripts/07_export.py.",
        "Tabel masukan ioGAS: Ramba Joring. Dibuat oleh scripts/07_export.py.",
        "",
        "CONFIDENTIAL committee data / data RAHASIA panitia: do not share outside the team.",
        "",
        "Use / pemakaian: the repo owner builds the ioGAS project from these tables on this PC,",
        "driven by agents (AGENTS.md section 10, skill .claude/skills/iogas/SKILL.md).",
        "scripts/22_iogas_link.py writes matching .gas projects here (EPSG:32647, rows coloured",
        "by ML class); open those rather than the CSVs when a workflow saves the project.",
        "Pemilik repo membuat proyek ioGAS dari tabel ini; .gas yang sesuai dibuat oleh 22_iogas_link.py.",
        "",
        "Finished ioGAS projects (deliverable 2) / proyek ioGAS akhir: outputs/iogas_project/",
        "(RJ_*_final_v1.gas; start with BACA_SAYA.txt there). Terms and file names / istilah dan",
        "nama file: README.md 'Terms and file naming', PANDUAN_TIM.md bagian 1.",
        "",
        "Files / berkas:",
    ]
    use = {"RJ_DH_assay": "downhole plots, probability plots, scatter (raw intervals) / plot downhole, probabilitas",
           "RJ_DH_komposit_1m": "downhole plots and statistics on equal 1 m support / plot downhole pada komposit 1 m",
           "RJ_batuan": "rock maps, probability plots, classification by alteration / peta & plot batuan",
           "RJ_tanah": "soil maps and probability plots (cleanest surface data) / peta & plot tanah",
           "RJ_DH_collar": "collar locations / lokasi collar", "RJ_DH_survey": "downhole survey / survei lubang bor"}
    for n, (t, *_rest) in tables.items():
        lines.append(f"  {n}.csv ({len(t)} rows): {use[n]}")
    lines += [
        "  kolom_iogas.csv: meaning of every column / arti setiap kolom",
        "",
        "Notes / catatan:",
        "  - Element columns are named Element_unit (Au_ppm, Fe_pct). After import, CHECK the",
        "    element/unit aliases ioGAS guesses (e.g. AuCN_ppm is CN-soluble Au, not total Au;",
        "    S_sulfida_SCIS_pct and S_sulfida_S2_pct are different methods: never combine them).",
        "  - Values are detection-limit harmonised. Below-detection values are DL/2 and marked",
        "    Y in <Element>_cens: the flat bottom of a probability plot is DL/2, not a population.",
        "  - Blank cell = not analysed (sel kosong = tidak dianalisis). It is never zero.",
        "  - Category columns are in Bahasa Indonesia for report legends: Kelompok_Litologi,",
        "    Fasies_Alterasi, Status_Oksidasi (log), Status_Oksidasi_turunan (derived; RJDH019).",
        "  - Flags are Y/N text. Use prospek_RJ = Y to keep Ramba Joring only; NS_SEL = N and",
        "    comp_ok = Y for usable downhole data.",
        "  - Coordinates: UTM WGS84 zone 47N (EPSG:32647). Surface Z is re-draped on lidar.",
        "  - ML_* columns (when present) are model outputs: ML_thr_ thresholds (ML-1), ML_alt_/",
        "    ML_oks_/ML_lit_ chemistry-to-log classes (ML-2), ML_zona surface zones (ML-3), ML_hmm_",
        "    downhole units S1-S5 (ML-4), ML_paf_ PAF/NAF (ML-5), ML_gp_ kriging (ML-6), ML_s9_",
        "    literature comparators. Details: LOG.md.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    bad = loaders.verify_raw()
    assert not bad, f"raw files changed: {bad}"
    I = paths.INTERIM
    raw = {n: loaders.load_dh(n) for n in ["collar", "survey", *LOG_TABLES]}
    raw_rock, raw_soil = loaders.load_rock(), loaders.load_soil()
    collar = pd.read_csv(I / "03_collar.csv")
    survey = pd.read_csv(I / "03_survey.csv")
    assay = pd.read_csv(I / "05_assay_joined.csv", low_memory=False)
    comp = pd.read_csv(I / "06_composites.csv", low_memory=False)
    rock = pd.read_csv(I / "04_rock.csv", low_memory=False)
    soil = pd.read_csv(I / "03_soil.csv", low_memory=False)
    ox = pd.read_csv(I / "04_oxide.csv", low_memory=False)
    mineral = pd.read_csv(I / "04_mineralisation.csv", low_memory=False)
    es = pd.read_csv(I / "01_element_summary.csv")
    dictionary = pd.read_csv(OUT / "code_dictionary.csv")

    # --- inventory guard --------------------------------------------------------------
    sources = {"collar": collar, "survey": survey, "assay": assay, "composites": comp, "rock": rock,
               "soil": soil, "oxide": ox, "mineralisation": mineral}
    unmapped = {f"{n}.{c}" for n, d in sources.items() for c in d.columns
                if FLAG_RE.match(c) and c not in HANDLED and not c.endswith("_dl_coarse")}
    assert not unmapped, f"flag columns with no validation check: {sorted(unmapped)}"

    # --- flags and summary ------------------------------------------------------------
    dh, holes = drillhole_flags(collar, survey, assay, ox, mineral)
    flags = pd.concat([f for f in surface_flags(rock, soil) + dh if len(f)], ignore_index=True)
    n_surf, n_dh = len(rock) + len(soil), len(assay)
    n_records = {**{k: n_surf for k in ("S1", "S2", "S3", "S4", "S5")}, "D1": len(collar), "D2": len(collar),
                 "D3": int((~survey.survey_extrap.astype(bool)).sum()), "D4": n_dh, "D5": n_dh, "D6": n_dh,
                 "D7": n_dh, "D8": len(collar), "D9": len(ox), "D10": len(collar),
                 "D11": len(mineral) + n_dh, "D12": n_dh, "D13": n_dh, "D14": len(collar)}
    clean, clean_ok = clean_checks(raw, raw_rock, raw_soil)
    summ = summary(flags, n_records, clean + dataset_rows(raw["assay"], raw_rock, raw_soil, es, dictionary,
                                                          comp, rock, soil))
    prec = precision(rock, assay)
    era = era_figure(comp, holes)

    # --- checks: AGENTS §4 facts ------------------------------------------------------
    def n(cid, issue=None, ds=None):
        f = flags[flags.check_id.eq(cid)]
        if issue:
            f = f[f.issue.str.contains(issue, regex=False)]
        if ds:
            f = f[f.dataset.eq(ds)]
        return len(f)
    gaps = collar.loc[collar.survey_gap_m >= 1.0].set_index("SiteID").survey_gap_m.round(1).to_dict()
    cn_au = prec[prec.element.eq("AuCN/Au")].iloc[0]
    cn_ag = prec[prec.element.eq("AgCN/Ag")].iloc[0]
    facts = {
        "§4.1 clean checks pass on the raw tables (intervals, SampleIDs, collar vs survey)": clean_ok,
        "§4.2.8 elevation > 30 m: rock 13, soil 6": n("S1", "elev_error", "rock") == 13 and n("S1", "elev_error", "soil") == 6,
        "§4.2.8 elevation 10-30 m: rock 35, soil 13":
            n("S1", "dem_uncertain", "rock") == 35 and n("S1", "dem_uncertain", "soil") == 13,
        "§4.2.6 duplicate XY: 21 rows, 13 extra": n("S2") == 21 and n("S2") - rock.dupxy_group.nunique() == 13,
        "§4.2.2 NS-SEL 10": n("D4") == 10,
        "§4.2.4 AuCN > 1.1 x Au 125 of 979 pairs": n("D6", "AuCN") == 125 and cn_au.n == 979,
        "§4.2.4 AgCN > 1.1 x Ag 173 of 1,267 pairs": n("D6", "AgCN") == 173 and cn_ag.n == 1267,
        "§4.2.11 survey gaps >= 1 m: 82.4/51.2/34.5/15.7/2.0 m": gaps == {"RJDH001": 82.4, "RJDH012": 51.2, "RJDH011": 34.5,
                                                               "RJDH014": 15.7, "RJDH003": 2.0},
        "§4.1 pads RJDH002, RJDH006": set(flags.loc[flags.check_id.eq("D1"), "record_id"]) == {"RJDH002", "RJDH006"},
        "§4.2.10 RJDH001 has no sulfur": holes.set_index("SiteID").S_issue["RJDH001"] == "no sulfur analysed",
        "§4.2.12 azimuth swings only in RJDH001/RJDH019":
            set(flags.loc[flags.check_id.eq("D3"), "site_id"]) == {"RJDH001", "RJDH019"},
    }

    # --- ioGAS ------------------------------------------------------------------------
    tables = iogas_tables(assay, comp, rock, soil, collar, survey, holes)
    source_of = {"RJ_DH_assay": assay, "RJ_DH_komposit_1m": comp, "RJ_batuan": rock, "RJ_tanah": soil,
                 "RJ_DH_collar": collar, "RJ_DH_survey": survey}
    problems, dict_rows = [], []
    for name, (t, src, key, target) in list(tables.items()):
        t = export.merge_ml(t, key, ML_DIR, target)
        tables[name] = (t, src, key, target)
        problems += check_iogas(name, t, src, source_of[name], key)
        for c in t.columns:
            en, idn, unit = describe(c, src)
            dict_rows.append({"file": f"{name}.csv", "column": c, "source_column": src.get(c, ""),
                              "meaning_en": en, "meaning_id": idn, "unit": unit})
    facts["ioGAS files: rows, keys, ASCII headers/labels, values equal source _ml"] = not problems
    print("Plan checks")
    for k, ok in facts.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {k}")
    for p in problems:
        print("   ", p)
    assert all(facts.values()), "check failed: stop and report"

    # --- outputs ----------------------------------------------------------------------
    # judges open these in Excel: plain-ASCII text, UTF-8 with BOM so Excel reads it as UTF-8
    for name, d in (("validation_flags", flags), ("validation_summary", summ), ("qaqc_precision", prec)):
        d = d.replace("§", "", regex=True)  # section sign in AGENTS refs
        assert all(d[c].dropna().astype(str).map(str.isascii).all() for c in d.columns), f"{name}: non-ASCII"
        d.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
    IOGAS.mkdir(parents=True, exist_ok=True)
    for name, (t, *_rest) in tables.items():
        t.to_csv(IOGAS / f"{name}.csv", index=False)
    pd.DataFrame(dict_rows).to_csv(IOGAS / "kolom_iogas.csv", index=False)
    (IOGAS / "README_iogas.txt").write_text(readme(tables), encoding="utf-8")

    # --- summary print ----------------------------------------------------------------
    print(f"\nvalidation_flags.csv: {len(flags)} rows; by severity {flags.severity.value_counts().to_dict()}")
    print("  " + flags.groupby(["check_id", "dataset"]).size().rename("n").reset_index()
          .to_string(index=False).replace("\n", "\n  "))
    print(f"\nvalidation_summary.csv: {len(summ)} rows; results {summ.result.value_counts().to_dict()}")
    q1 = summ[summ.check_id.eq("Q1")].iloc[0]
    print(f"  Q1 {q1.detail}")
    for r in summ[summ.check_id.isin(["Q2", "Q4", "Q5"])].itertuples():
        print(f"  {r.check_id} {r.dataset}: flagged {r.n_flagged} of {r.n_records}; {r.detail if pd.notna(r.detail) else ''}")
    print("\nqaqc_precision.csv")
    fd = prec[prec.section.eq("field_duplicate_xy_average_cv")]
    print("  average CV% by group type: " + "; ".join(
        f"{r.group_type} {r.element} {r.cv_pct:.0f}% (groups {int(r.n)})" for r in fd.itertuples()))
    rs = prec[prec.section.eq("field_duplicate_xy") & prec.group_type.eq("resample")]
    print("  resample group: " + "; ".join(f"{r.element} mean {r['mean']:.1f}, CV {r.cv_pct:.0f}% (n {int(r.n)})"
                                           for _, r in rs.iterrows()))
    for _, r in prec[prec.section.eq("cn_vs_total")].iterrows():
        print(f"  {r.element}: pairs {int(r.n)}, share > 1.1 {r['share_gt_1.1']}, median {r.q50}, "
              f"q05-q95 {r.q05}-{r.q95}")
    print("\nLab year: composites (comp_ok) and median Au")
    print("  " + era.round(3).to_string().replace("\n", "\n  "))
    print("\nioGAS files")
    for name, (t, src, key, _t) in tables.items():
        n_ml = sum(c.startswith("ML_") for c in t.columns)
        print(f"  {name}.csv: {t.shape[0]} rows x {t.shape[1]} cols; element cols "
              f"{sum(not c.endswith('_cens') for c in src)}; ML_* {n_ml}")
    print(f"  kolom_iogas.csv: {len(dict_rows)} rows; README_iogas.txt")
    print("  outputs/figures/07_au_lubang_tahun_v1.png")
    print("\nall checks passed")


if __name__ == "__main__":
    main()
