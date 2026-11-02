"""Stage 4: codes (AGENTS.md §5.3). Plan: LOG.md, 2026-11-02 Stage 4 entry.

Case-harmonised code columns (originals kept), lithology groups, alteration facies names,
oxidation state (+ a derived state for RJDH019, which has none logged), mineral presence
flags and the code dictionary. Reads data/interim/03_*.csv; writes data/interim/04_*.csv and
data/processed/code_dictionary.csv. Prints counts only.
Run: uv run python scripts/04_codes.py
"""
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, confusion_matrix

from src import codes, loaders, paths

TABLES = ["lithology", "alteration", "mineralisation", "oxide", "rock"]
MIN_COLS = ["DomMin1", "DomMin2", "DomMin3", "SecMin1", "SecMin2", "SecMin3"]
# (table, column, vocabulary, case fold or None = check only)
CODED = [
    ("lithology", "Lith1Interp", "lith", None),
    ("lithology", "Lith1Qual1", "lith_qual", "lower"),
    ("lithology", "Lith1Qual2", "lith_qual", "lower"),
    ("lithology", "Clast1", "lith", None),
    ("lithology", "Clast2", "lith", None),
    ("alteration", "AltFacies", "alt_facies", None),
    ("alteration", "AltQual1", "texture", "upper"),
    ("alteration", "AltQual2", "texture", "upper"),
    ("alteration", "AltQual3", "texture", "upper"),
    ("alteration", "AltMin1", "alt_min", "lower"),
    ("alteration", "AltMin2", "alt_min", "lower"),
    *[("mineralisation", c, "mineral", "lower") for c in MIN_COLS],
    ("mineralisation", "DomMinMode", "min_mode", "lower"),
    ("mineralisation", "SecMinMode", "min_mode", "lower"),
    ("mineralisation", "DomMinDescr", "texture", None),
    ("mineralisation", "SecMinDescr", "texture", None),
    ("rock", "Lithology", "lith", None),
    ("rock", "IntrpAltFa", "alt_facies", None),
]
AGENTS_FACIES = {"AA": 442, "SI": 158, "AR": 77, "UA": 18, "PP": 12}


def overlap(a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Share of the summed length of intervals `a` covered by intervals `b` (same hole)."""
    tot = cov = 0.0
    for x in a.itertuples():
        bb = b[b.SiteID.eq(x.SiteID)]
        tot += x.DepthTo - x.DepthFrom
        cov += np.clip(np.minimum(bb.DepthTo, x.DepthTo) - np.maximum(bb.DepthFrom, x.DepthFrom), 0, None).sum()
    return cov / tot


def harmonise(t: dict) -> list[dict]:
    """Add <col>_h columns, check every code is in its vocabulary; return dictionary rows."""
    rows = []
    for table, col, vocab, case in CODED:
        df = t[table]
        s = df[col]
        if case:
            s = codes.harmonise_case(s, case)
            df[f"{col}_h"] = s
        codes.check_codes(s, vocab)
        folded = pd.Series(s.dropna().unique())
        assert folded.str.lower().is_unique, f"{table}.{col}: codes differ only by case after harmonising"
        for code, n in s.value_counts().items():
            rows.append({"table": table, "field": col, "vocabulary": vocab, "code": code, "n": int(n),
                         "raw_variants": "/".join(sorted(df.loc[s.eq(code), col].unique())),
                         **codes.lookup(vocab, code)})
    return rows


def derived_oxidation(ox: pd.DataFrame) -> pd.DataFrame:
    """RJDH019 has no logged state: derive one from WRAltOxidPcnt, cut-offs by
    leave-one-hole-out on the logged holes (human decision, Stage 4 plan)."""
    logged = ox[ox.ox_state.notna()]
    pred = pd.Series(index=logged.index, dtype=object)
    for site in logged.SiteID.unique():
        train, test = logged[logged.SiteID.ne(site)], logged[logged.SiteID.eq(site)]
        a, b = codes.fit_ox_cutoffs(train.WRAltOxidPcnt.to_numpy(), train.ox_state.to_numpy())
        pred[test.index] = codes.apply_ox_cutoffs(test.WRAltOxidPcnt.to_numpy(), a, b)
    bacc = balanced_accuracy_score(logged.ox_state, pred)
    acc = (pred == logged.ox_state).mean()
    a, b = codes.fit_ox_cutoffs(logged.WRAltOxidPcnt.to_numpy(), logged.ox_state.to_numpy())
    labels = ["Oxide", "Transition", "Sulphide"]
    cm = pd.DataFrame(confusion_matrix(logged.ox_state, pred, labels=labels),
                      index=[f"logged {x}" for x in labels], columns=[f"derived {x}" for x in labels])
    print(f"\nDerived oxidation (leave-one-hole-out over {logged.SiteID.nunique()} logged holes)")
    print(f"  final cut-offs on all logged holes: Sulphide <= {a}% < Transition <= {b}% < Oxide")
    print(f"  LOHO accuracy {acc:.3f}, balanced accuracy {bacc:.3f} (majority-class baseline 0.333)")
    print("  " + cm.to_string().replace("\n", "\n  "))
    assert bacc > 1 / 3, "derived oxidation does not beat the majority class: stop and report"
    ox = ox.copy()
    ox["ox_state_derived"] = codes.apply_ox_cutoffs(ox.WRAltOxidPcnt.to_numpy(), a, b)
    ox["ox_state_source"] = np.where(ox.ox_state.notna(), "logged", "derived_pct")
    ox.attrs.update(cut_a=a, cut_b=b, loho_acc=acc, loho_bacc=bacc)
    return ox


def main() -> None:
    bad = loaders.verify_raw()
    assert not bad, f"raw files changed: {bad}"
    stage3 = {n: pd.read_csv(paths.INTERIM / f"03_{n}.csv", low_memory=False) for n in TABLES}
    t = {n: df.copy() for n, df in stage3.items()}

    rows = harmonise(t)
    t["lithology"] = codes.lith_group(t["lithology"], "Lith1Interp")
    t["rock"] = codes.alt_facies(codes.lith_group(t["rock"], "Lithology"), "IntrpAltFa")
    t["alteration"] = codes.alt_facies(t["alteration"], "AltFacies")
    t["mineralisation"] = codes.mineral_flags(t["mineralisation"], [f"{c}_h" for c in MIN_COLS])
    t["oxide"] = derived_oxidation(codes.ox_state(t["oxide"]))

    # --- checks -------------------------------------------------------------------
    for n in TABLES:
        assert len(t[n]) == len(stage3[n]), f"{n}: row count changed"
        assert t[n][stage3[n].columns].equals(stage3[n]), f"{n}: an original column changed"
    fac = t["alteration"].AltFacies.value_counts().to_dict()
    ox = t["oxide"]
    lith, alt = t["lithology"], t["alteration"]
    ua = alt[alt.AltFacies.eq("UA")]
    cover_void = lith[lith.Lith1Interp.isin(["SCR", "SCL", "CAV"])]
    assay = pd.read_csv(paths.INTERIM / "03_assay.csv", low_memory=False)
    cav = lith[lith.Lith1Interp.eq("CAV")].iloc[0]
    cav_assays = assay[assay.SiteID.eq(cav.SiteID) & assay.DepthFrom.lt(cav.DepthTo) & assay.DepthTo.gt(cav.DepthFrom)]
    facts = {
        "AltFacies AA 442, SI 158, AR 77, UA 18, PP 12 (§3)": fac == AGENTS_FACIES,
        "oxidation: 127 null labels, all RJDH019 (Stage 4 profiling)":
            ox.ox_state.isna().sum() == 127 and set(ox.loc[ox.ox_state.isna(), "SiteID"]) == {"RJDH019"},
        "UA length inside SCR/SCL/CAV >= 0.95": overlap(ua, cover_void) >= 0.95,
        "SCR/SCL length inside UA >= 0.95": overlap(lith[lith.Lith1Interp.isin(["SCR", "SCL"])], ua) >= 0.95,
        "SCR/SCL always the first interval (from 0 m)":
            lith.loc[lith.Lith1Interp.isin(["SCR", "SCL"]), "DepthFrom"].eq(0).all(),
        "CAV assays are all NS-SEL": len(cav_assays) > 0 and cav_assays.no_sample.all(),
    }
    print("\nAGENTS.md / evidence checks")
    for k, ok in facts.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {k}")
    print(f"  (UA inside SCR/SCL/CAV: {overlap(ua, cover_void):.3f})")
    assert all(facts.values()), "check failed: stop and report"

    # --- summary ------------------------------------------------------------------
    d = pd.DataFrame(rows)
    print("\nCase variants merged (field: harmonised <- raw)")
    for r in d[d.raw_variants.str.contains("/")].itertuples():
        print(f"  {r.table}.{r.field}: {r.code} <- {r.raw_variants} (n {r.n})")
    print("\nLith_group (downhole intervals | rock samples)")
    lg = pd.concat([lith.Lith_group.value_counts().rename("downhole"),
                    t["rock"].Lith_group.value_counts().rename("rock")], axis=1).fillna(0).astype(int)
    print("  " + lg.to_string().replace("\n", "\n  "))
    m = t["mineralisation"]
    print("\nMineral presence flags (mineralisation intervals): "
          + ", ".join(f"{f} {int(m[f].sum())}" for f in codes.MINERAL_FLAGS))
    print(f"Oxidation: {ox.ox_state.value_counts().to_dict()}; conflicts {int(ox.flag_ox_conflict.sum())}; "
          f"WRAltSulphIntensity -999 -> NaN {int(ox.WRAltSulphIntensity.eq(-999).sum())}")
    print(f"RJDH019 derived: {ox.loc[ox.SiteID.eq('RJDH019'), 'ox_state_derived'].value_counts().to_dict()}")
    print(f"Dictionary sources: {d.drop_duplicates(['vocabulary', 'code']).source.value_counts().to_dict()}")

    # --- outputs ----------------------------------------------------------------
    for n in TABLES:
        t[n].to_csv(paths.INTERIM / f"04_{n}.csv", index=False)
    paths.PROCESSED.mkdir(parents=True, exist_ok=True)
    cols = ["table", "field", "vocabulary", "code", "raw_variants", "n", "group", "meaning_en", "meaning_id",
            "source", "evidence"]
    d["group"] = d.group.map(lambda k: codes.LITH_GROUP_NAMES[k][0] if isinstance(k, str) else "")
    d[cols].to_csv(paths.PROCESSED / "code_dictionary.csv", index=False)
    print("\nOutputs")
    for n in TABLES:
        print(f"  04_{n}.csv: {t[n].shape[0]} rows x {t[n].shape[1]} cols")
    print(f"  data/processed/code_dictionary.csv: {len(d)} rows")
    print("\nall checks passed")


if __name__ == "__main__":
    main()
