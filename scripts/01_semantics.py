"""Stage 1: semantics (AGENTS.md §5.1). Plan and DL rule change: LOG.md, 2026-11-02.

Reads data/raw, writes data/interim/01_*.csv. Prints counts only, no data values.
Run: uv run python scripts/01_semantics.py
"""
import numpy as np
import pandas as pd

from src import loaders, paths
from src import semantics as sem

EXPECTED_ROWS = {"assay": 2476, "rock": 469, "soil": 259}
REVIEW_COLS = ["AuPPM", "AgPPM", "AsPPM", "CuPPM", "ZnPPM", "PbPPM", "HgPPM",
               "SCIS_PCT", "S2_SPCT", "S_PCT"]
SENSITIVITY_SHARES = [0.05, 0.10, 0.20]


def add_dates(name: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if name == "assay":
        df["lab_date"] = sem.parse_dates(df["LabJobDate"], dayfirst=True)
        df["year"] = df["lab_date"].dt.year.astype("Int64")
        n_bad = df["lab_date"].isna().sum() - df["SampleType"].eq("NS-SEL").sum()
    else:
        if name == "rock":
            df["collect_date"] = sem.parse_dates(df["DateCollec"], fmt="%Y%m%d")
        else:
            df["collect_date"] = sem.parse_dates(df["DateCollected"], dayfirst=True)
        df["year"] = df["collect_date"].dt.year.astype("Int64")
        n_bad = df["collect_date"].isna().sum()
    assert n_bad == 0, f"{name}: {n_bad} unparsed dates"
    return df


def process(name: str, raw: pd.DataFrame):
    surface = name != "assay"
    cols = sem.analyte_columns(raw)
    if surface:
        df, zeros = sem.zeros_to_nan(raw, cols)
    else:
        assert not (raw[cols] == 0).any().any(), f"{name}: unexpected zeros in drillhole assays"
        df, zeros = raw.copy(), pd.Series(0, index=cols)
    df = add_dates(name, df)

    floors = sem.detect_floors(df, cols)
    n_analysed = df[cols].notna().sum()
    dl = sem.harmonised_dl(floors, n_analysed)
    df = sem.harmonise(sem.flag_censored(df, floors), floors, dl)
    df = sem.add_cn_ratios(df)

    sensitivity = {}
    for share in SENSITIVITY_SHARES:
        alt = sem.harmonise(df[["LabJobNo", *dl.index]], floors,
                            sem.harmonised_dl(floors, n_analysed, share))
        sensitivity[share] = pd.Series({c: round(100 * alt[f"{c}_cens_h"].sum() / n_analysed[c], 1)
                                        for c in dl.index})

    if surface:
        df["is_RJ"] = df["Prospect"].eq("Ramba Joring")
    else:
        df = sem.add_s_method(df)
        df["no_sample"] = df["SampleType"].eq("NS-SEL")

    check(name, raw, df, cols, zeros, dl, floors)
    summary = sem.element_summary(df, cols, zeros, dl, sensitivity)

    job_year = df.groupby("LabJobNo")["year"].agg(lambda y: y.mode().iloc[0] if y.notna().any() else pd.NA)
    floors.insert(2, "year", floors["job"].map(job_year))
    floors["share_of_column"] = (floors["n"] / floors["column"].map(n_analysed)).round(3)
    floors["harmonised_dl"] = floors["column"].map(dl)

    empty = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty)
    floors.insert(0, "dataset", name)
    summary.insert(0, "dataset", name)
    return df, floors, summary, empty


def check(name, raw, df, cols, zeros, dl, floors):
    assert len(df) == EXPECTED_ROWS[name], f"{name}: row count changed"
    assert df["SampleID"].is_unique, f"{name}: duplicate SampleID"
    fl = floors[floors.is_censoring_floor]
    for c in cols:
        # no NaN created except the converted zeros
        assert df[c].isna().sum() == raw[c].isna().sum() + zeros[c], f"{name}.{c}: new NaN"
        # raw values unchanged where they were not zero
        keep = raw[c].notna() & (raw[c] != 0)
        assert np.array_equal(df.loc[keep, c].to_numpy(), raw.loc[keep, c].to_numpy()), \
            f"{name}.{c}: raw value changed"
        if c not in dl.index:
            continue
        ml, cens_h = df[f"{c}_ml"], df[f"{c}_cens_h"].fillna(False).astype(bool)
        assert ml.isna().equals(df[c].isna()), f"{name}.{c}_ml: NaN pattern differs"
        # _ml differs from raw only where flagged censored
        changed = ~np.isclose(ml.fillna(-1), df[c].fillna(-1))
        assert not (changed & ~cens_h).any(), f"{name}.{c}_ml changed an uncensored value"
        # censored values sit at harmonised DL/2 or at their own (coarser) job DL/2
        jf = fl[fl.column == c].set_index("job")
        own_half = df["LabJobNo"].map(jf.true_dl) / 2
        ok = np.isclose(ml, dl[c] / 2) | np.isclose(ml, own_half)
        assert ok[cens_h].all(), f"{name}.{c}_ml: censored value not at a DL/2"
        # never halve twice: censored values in DL/2 jobs never drop below the stored floor
        half_jobs = jf.index[jf.floor_is == "DL/2"]
        at_floor = df["LabJobNo"].isin(half_jobs) & df[f"{c}_cens"].fillna(False).astype(bool)
        floor_v = df["LabJobNo"].map(jf.floor)
        assert (ml[at_floor] >= floor_v[at_floor] - 1e-12).all(), f"{name}.{c}: halved twice"


def check_agents_facts(assay, rock_raw):
    """Reproduce AGENTS.md §4.2 counts. A mismatch must be reported, not patched."""
    facts = {
        "rock CaPCT zeros = 443": (rock_raw["CaPCT"] == 0).sum() == 443,
        "drillhole Au/Ag/Cu/As analysed = 2466":
            all(assay[c].notna().sum() == 2466 for c in ["AuPPM", "AgPPM", "CuPPM", "AsPPM"]),
        "NS-SEL rows = 10, all unassayed":
            assay["no_sample"].sum() == 10
            and assay.loc[assay.no_sample, ["AuPPM", "AgPPM", "CuPPM", "AsPPM"]].isna().all().all(),
        "AuCN > 1.1 x Au in 125/979 pairs":
            (assay.flag_AuCN_gt_total.sum(), assay.flag_AuCN_gt_total.notna().sum()) == (125, 979),
        "AgCN > 1.1 x Ag in 173/1267 pairs":
            (assay.flag_AgCN_gt_total.sum(), assay.flag_AgCN_gt_total.notna().sum()) == (173, 1267),
    }
    for k, ok in facts.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {k}")
    assert all(facts.values()), "AGENTS.md §4.2 fact not reproduced: stop and report"


def main() -> None:
    bad = loaders.verify_raw()
    assert not bad, f"raw files changed: {bad}"

    raw = {"assay": loaders.load_dh("assay"), "rock": loaders.load_rock(),
           "soil": loaders.load_soil()}
    results = {n: process(n, raw[n]) for n in raw}

    print("AGENTS.md §4.2 checks")
    check_agents_facts(results["assay"][0], raw["rock"])

    paths.INTERIM.mkdir(parents=True, exist_ok=True)
    for n, (df, *_) in results.items():
        df.to_csv(paths.INTERIM / f"01_{n}.csv", index=False)
    floors = pd.concat([r[1] for r in results.values()])
    summary = pd.concat([r[2] for r in results.values()])
    floors.to_csv(paths.INTERIM / "01_detection_limits.csv", index=False)
    floors[floors.column.isin(REVIEW_COLS)].to_csv(paths.INTERIM / "01_dl_review.csv", index=False)
    summary.to_csv(paths.INTERIM / "01_element_summary.csv", index=False)

    print("\nOutputs")
    for n, (df, _, s, empty) in results.items():
        print(f"  01_{n}.csv: {df.shape[0]} rows x {df.shape[1]} cols; "
              f"dropped {len(empty)} empty cols; zeros->NaN {int(s.zeros_to_nan.sum())}")
        print(f"    ml_usable: {s.loc[s.ml_usable, 'column'].tolist()}")
    print("\nall checks passed")


if __name__ == "__main__":
    main()
