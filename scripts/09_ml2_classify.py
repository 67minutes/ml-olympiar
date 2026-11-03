"""ML-2: logged classes from chemistry (AGENTS.md §6 task 2). Plan: LOG.md, 2026-11-03 ML-2 entry.

Random forests (plus logistic and prior baselines) on log10 Au/Ag/Cu/As and log-ratios,
optionally with sulfide S (SCIS) or CN-soluble ratios, predict logged alteration,
oxidation, lithology group and pyrite / Cu-mineral presence on raw sampled assays.
Validation leaves out whole drill pads (collars < 30 m apart); leave-one-hole-out is run
once per target to show the twin-pad leak. Surface rock alteration has its own model with
150 m spatial-block CV. Reads data/interim/05_assay_joined.csv, 03_collar.csv,
04_rock.csv; writes data/processed/ml/{assay,batuan}__ml2_classify.csv,
data/processed/ml2_{scores,review_list,shap_importance,per_pad}.csv and
outputs/figures/09_*_v1.png. Prints summaries only.
Run: uv run python scripts/09_ml2_classify.py  (then rerun scripts/07_export.py)
"""
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from joblib import Parallel, delayed
from matplotlib.lines import Line2D
from sklearn.metrics import balanced_accuracy_score, confusion_matrix

from src import classify as cl, paths

warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")
warnings.filterwarnings("ignore", message="A single label was found")

B_CI = 1000
P_REVIEW = 0.7
REVIEW_MIN_M = 3.0
P_AMBIG = 0.5
BLOCK_M = 150.0
ROCK_SPLITS = 5
N_SHAP = 600

DH_COLS = {"Au": "AuPPM_ml", "Ag": "AgPPM_ml", "Cu": "CuPPM_ml", "As": "AsPPM_ml"}
DH_RATIOS = [("Cu", "Au"), ("As", "Au"), ("Cu", "As")]
TIERS = {  # tier: (log columns, ratios, raw columns)
    "A": (DH_COLS, DH_RATIOS, {}),
    "B": ({**DH_COLS, "S_SCIS": "SCIS_PCT_ml"}, DH_RATIOS, {}),
    "C": ({**DH_COLS, "AuCN/Au": "AuCN_ratio", "CuCN/Cu": "CuCN_ratio"}, DH_RATIOS, {}),
    "A+kedalaman": (DH_COLS, DH_RATIOS, {"kedalaman": "depth_v"}),
    "B+kedalaman": ({**DH_COLS, "S_SCIS": "SCIS_PCT_ml"}, DH_RATIOS, {"kedalaman": "depth_v"}),
    "A_tanpaAg": ({k: v for k, v in DH_COLS.items() if k != "Ag"}, [("Cu", "Au"), ("As", "Au")], {}),
}
ROCK_COLS = {"Au": "AuPPM_ml", "Cu": "CuPPM_ml", "As": "AsPPM_ml"}
ROCK_TIERS = {
    "R1": (ROCK_COLS, [("Cu", "Au"), ("As", "Au")], {}),
    "R2": ({**ROCK_COLS, "Hg": "HgPPM_ml", "Pb": "PbPPM_ml", "Sb": "SbPPM_ml", "Zn": "ZnPPM_ml"},
           [("Cu", "Au"), ("As", "Au")], {}),
}
ALT_ID = {"AA": "Argilik lanjut", "SI": "Silika", "AR": "Argilik", "PP": "Propilitik"}
OX_ID = {"Oxide": "Oksida", "Transition": "Transisi", "Sulphide": "Sulfida"}
LIT_MAIN = {"Coherent dacite-andesite porphyry": "Porfiri dasit-andesit koheren", "Phreatomagmatic breccia": "Breksi freatomagmatik",
            "Hydrothermal breccia": "Breksi hidrotermal", "Fault zone": "Zona sesar"}
LIT_ID = {**LIT_MAIN, "Other": "Lainnya"}
YN_ID = {"N": "Tidak", "Y": "Ya"}
TARGET_ID = {"alt": "Alterasi", "oks": "Oksidasi", "lit": "Litologi", "py": "Pirit", "cu": "Mineral Cu",
             "alt_batuan": "Alterasi batuan permukaan"}
FEAT_ID = {"S_SCIS": "S (SCIS)", "kedalaman": "Kedalaman vertikal"}
UNIT = {"Au": "g/t", "Ag": "ppm", "Cu": "ppm", "As": "ppm", "S_SCIS": "%", "Hg": "ppm", "Pb": "ppm",
        "Sb": "ppm", "Zn": "ppm"}
C_RF, C_LR, C_DUM, C_INK, C_INK2 = "#2a78d6", "#52514e", "#b9b8b2", "#0b0b0b", "#52514e"


def yn(s: pd.Series) -> pd.Series:
    return s.map({True: "Y", False: "N", "True": "Y", "False": "N"})


def targets(a: pd.DataFrame) -> dict:
    """target: (labels (NaN = not trained on), predict mask, classes, tiers, boundary mask, label map)."""
    lit = a.Lith_group.where(a.Lith_group.isin(LIT_MAIN), "Other")
    lit = lit.where(~a.Lith_group.isin(["Surface cover", "Void (cavity)"]) & a.Lith_group.notna())
    logged_min = a.min_logged.astype(bool)
    bnd = {p: a[f"{p}_mixed"].astype(bool) | (a[f"{p}_frac"] < 0.5) for p in ("alt", "ox", "lith", "min")}
    return {
        "alt": (a.alt_ml_label, a.alt_ml_label.notna(), list(ALT_ID), ["A", "B", "C"], bnd["alt"], ALT_ID),
        "oks": (a.ox_state, a.ox_state.notna() | a.SiteID.eq("RJDH019"), list(OX_ID),
                ["A", "B", "C", "A+kedalaman", "B+kedalaman"], bnd["ox"], OX_ID),
        "lit": (lit, lit.notna(), list(LIT_ID), ["A", "B"], bnd["lith"], LIT_ID),
        "py": (yn(a.min_py).where(logged_min), pd.Series(True, index=a.index), ["N", "Y"], ["A", "B"],
               bnd["min"], YN_ID),
        "cu": (yn(a.min_cu).where(logged_min), pd.Series(True, index=a.index), ["N", "Y"], ["A", "B"],
               bnd["min"], YN_ID),
    }


def label_bahasa(s, m):
    return pd.Series(s).map(m)


def score_rows(y, P, classes, groups, mask=None) -> dict:
    lab = pd.notna(y) & (mask if mask is not None else True)
    if lab.sum() == 0 or len(set(y[lab])) < 2:
        return {"n": int(lab.sum())}
    s = cl.scores(y[lab], P[lab], classes)
    s["n_groups"] = len(pd.unique(groups[lab]))
    return s


def main() -> None:
    I, ml_dir = paths.INTERIM, paths.PROCESSED / "ml"
    ml_dir.mkdir(exist_ok=True)
    raw = pd.read_csv(I / "05_assay_joined.csv", low_memory=False)
    collar = pd.read_csv(I / "03_collar.csv")
    pads = cl.pad_groups(collar)
    print("pads:", pads.value_counts().size, "|", ", ".join(sorted(p for p in pads.unique() if "-" in p)))
    a = raw[~raw.no_sample.astype(bool)].copy()
    a["depth_v"] = a.SiteID.map(collar.set_index("SiteID").RLUTM) - a.Z_mid
    a["pad"] = a.SiteID.map(pads)
    holes = a.SiteID
    T = targets(a)
    feats = {t: cl.log_features(a, *spec) for t, spec in TIERS.items()}
    for t, X in feats.items():
        ok = cl.complete(X)
        print(f"tier {t:12s} rows {ok.sum():5d}  holes {a.SiteID[ok].nunique():2d}  pads {a.pad[ok].nunique():2d}")

    # --- downhole OOF, leave-one-pad-out (all models) + leave-one-hole-out (RF, tier A) --
    configs, jobs = [], []
    for tg, (y, pmask, classes, tiers, _b, _m) in T.items():
        for tier in tiers:
            X = feats[tier]
            rows = cl.complete(X) & pmask
            for kind in cl.MODELS:
                for cv, grp in (("pad", a.pad), ("hole", holes)):
                    if cv == "hole" and not (kind == "rf" and tier == "A"):
                        continue
                    j = cl.oof_jobs(X[rows], y[rows], grp[rows], classes, kind)
                    configs.append((tg, tier, kind, cv, rows, len(j)))
                    jobs += j
    print(f"\nfitting {len(jobs)} outer folds ({len(configs)} configs; RF leaf tuned in inner GroupKFold)")
    res = Parallel(n_jobs=-1)(delayed(cl.fold_job)(*j) for j in jobs)

    oof, k = {}, 0
    for tg, tier, kind, cv, rows, nj in configs:
        classes = T[tg][2]
        P, leaves = cl.collect(int(rows.sum()), classes, res[k:k + nj])
        k += nj
        full = np.full((len(a), len(classes)), np.nan)
        full[rows.to_numpy()] = P
        oof[(tg, tier, kind, cv)] = (full, rows, leaves)

    # --- scores ------------------------------------------------------------------------
    score_list, per_pad = [], []
    for (tg, tier, kind, cv), (P, rows, leaves) in oof.items():
        y, _pm, classes, _t, bnd, _m = T[tg]
        yv, rv = y.to_numpy(object), rows.to_numpy()
        grp = (a.pad if cv == "pad" else holes).to_numpy(object)
        base = dict(dataset="bor", target=tg, tier=tier, model=kind, cv=cv)
        for subset, m in (("semua", None), ("bersih", ~bnd.to_numpy()), ("batas", bnd.to_numpy())):
            s = score_rows(yv[rv], P[rv], classes, grp[rv], None if m is None else m[rv])
            if subset == "semua" and kind != "dummy" and "bal_acc" in s:
                lab = pd.notna(yv[rv])
                s["ci05"], s["ci95"] = cl.group_bootstrap(yv[rv][lab], cl.predict(P[rv][lab], classes),
                                                          grp[rv][lab], B=B_CI)
            if kind == "rf" and leaves[0] is not None:
                s["leaf_mode"] = int(pd.Series(leaves).mode().iloc[0])
            score_list.append({**base, "subset": subset, **s})
        if kind == "rf" and tier not in ("A", "A_tanpaAg") and cv == "pad":  # tier A on the same rows
            PA = oof[(tg, "A", "rf", "pad")][0]
            same = rv & ~np.isnan(PA[:, 0])
            s = score_rows(yv[same], PA[same], classes, grp[same])
            score_list.append({**base, "tier": f"A pada baris {tier}", "subset": "semua", **s})
        if kind == "rf" and cv == "pad" and tier == "A":
            lab = rv & pd.notna(yv)
            for p in pd.unique(grp[lab]):
                m = lab & (grp == p)
                per_pad.append(dict(target=tg, pad=p, n=int(m.sum()),
                                    bal_acc=balanced_accuracy_score(yv[m], cl.predict(P[m], classes))))
    sc = pd.DataFrame(score_list)

    # --- export tier per target: richer tier where it beats tier A on its own rows --------
    ml = pd.DataFrame({"SampleID": raw.SampleID})
    export_P, export_tier = {}, {}
    gain_rows = []
    for tg, (y, pmask, classes, tiers, bnd, lmap) in T.items():
        PA, rowsA, _ = oof[(tg, "A", "rf", "pad")]
        P, tier_used = PA.copy(), pd.Series(np.where(rowsA, "A", None), index=a.index, dtype=object)
        chem = [t for t in tiers if t in ("B", "C")]
        gains = []
        for t in chem:
            r = sc[(sc.target == tg) & (sc.model == "rf") & (sc.cv == "pad") & (sc.subset == "semua")]
            g = r[r.tier == t].bal_acc.iloc[0] - r[r.tier == f"A pada baris {t}"].bal_acc.iloc[0]
            gain_rows.append(dict(target=tg, tier=t, gain_vs_A_same_rows=g))
            if g > 0:
                gains.append((g, t))
        for g, t in sorted(gains):  # largest gain written last, so it wins where tiers overlap
            Pt, rt, _ = oof[(tg, t, "rf", "pad")]
            P[rt.to_numpy()] = Pt[rt.to_numpy()]
            tier_used[rt] = t
        export_P[tg], export_tier[tg] = P, tier_used
        ok = ~np.isnan(P[:, 0])
        pred = pd.Series(np.where(ok, cl.predict(np.nan_to_num(P, nan=0), classes), None), index=a.index)
        pmax = pd.Series(np.where(ok, np.nanmax(np.nan_to_num(P, nan=-1), axis=1), np.nan), index=a.index)
        yv, grp = y.to_numpy(object), a.pad.to_numpy(object)
        s = score_rows(yv[ok], P[ok], classes, grp[ok])
        lab = ok & pd.notna(yv)
        s["ci05"], s["ci95"] = cl.group_bootstrap(yv[lab], cl.predict(P[lab], classes), grp[lab], B=B_CI)
        sc = pd.concat([sc, pd.DataFrame([dict(dataset="bor", target=tg, tier="ekspor", model="rf", cv="pad",
                                               subset="semua", **s)])], ignore_index=True)
        cols = {}
        if len(classes) == 2:
            cols[f"ML_{tg}_p"] = pd.Series(np.where(ok, P[:, 1], np.nan), index=a.index).round(4)
        else:
            cols[f"ML_{tg}_prediksi"] = pred.map(lmap)
            cols[f"ML_{tg}_p_maks"] = pmax.round(4)
            cols[f"ML_{tg}_ambigu"] = pd.Series(np.where(ok, np.where(pmax < P_AMBIG, "Y", "N"), None), index=a.index)
            for j, c in enumerate(classes):
                cols[f"ML_{tg}_p_{c.replace(' ', '_')}"] = pd.Series(np.where(ok, P[:, j], np.nan), index=a.index).round(4)
            cols[f"ML_{tg}_entropi"] = pd.Series(np.where(ok, cl.entropy(np.nan_to_num(P, nan=0)), np.nan),
                                                 index=a.index).round(4)
        cols[f"ML_{tg}_tier"] = tier_used
        for c, v in cols.items():
            ml[c] = v.reindex(raw.index)

    # --- review list (ML vs logged) --------------------------------------------------------
    review = []
    for tg in ("alt", "oks", "lit"):
        y, _pm, classes, _t, _b, lmap = T[tg]
        P = export_P[tg]
        ok = ~np.isnan(P[:, 0])
        d = pd.DataFrame({"SiteID": a.SiteID, "DepthFrom": a.DepthFrom, "DepthTo": a.DepthTo,
                          "logged": y.map(lmap), "predicted": None, "p": np.nan})
        d.loc[ok, "predicted"] = pd.Series(cl.predict(P[ok], classes)).map(lmap).to_numpy()
        d.loc[ok, "p"] = P[ok].max(axis=1)
        flag = d.logged.notna() & d.predicted.notna() & (d.logged != d.predicted) & (d.p >= P_REVIEW)
        r = cl.disagreement_runs(d, flag, REVIEW_MIN_M)
        r.insert(0, "target", tg)
        review.append(r)
        print(f"review {tg}: {int(flag.sum())} assays p>={P_REVIEW} disagree; {len(r)} runs >= {REVIEW_MIN_M} m")
    review = pd.concat(review, ignore_index=True)

    # --- RJDH019 oxidation: predicted vs derived ---------------------------------------------
    m19 = a.SiteID.eq("RJDH019").to_numpy() & ~np.isnan(export_P["oks"][:, 0])
    p19 = pd.Series(cl.predict(export_P["oks"][m19], T["oks"][2]))
    d19 = a.loc[m19, "ox_state_derived"].reset_index(drop=True)
    agree19 = float((p19 == d19).mean())
    print(f"\nRJDH019 oxidation (no log): ML vs derived from % oxidised agree {agree19:.1%} (n {m19.sum()})")
    print(pd.crosstab(d19.rename("derived"), p19.rename("ML")).to_string())

    # --- final all-data RF + SHAP ------------------------------------------------------------
    shap_rows, shap_store = [], {}
    rng = np.random.default_rng(cl.SEED)
    for tg in ("alt", "oks", "lit", "py"):
        for tier in ("A", "B"):
            y, _pm, classes, *_ = T[tg]
            X = feats[tier]
            rows = cl.complete(X) & y.notna()
            leaf = int(sc[(sc.target == tg) & (sc.tier == tier) & (sc.model == "rf") & (sc.cv == "pad")
                          & (sc.subset == "semua")].leaf_mode.iloc[0])
            m = cl.rf(leaf).set_params(n_jobs=-1).fit(X[rows].to_numpy(), y[rows].to_numpy(object))
            take = rng.choice(np.flatnonzero(rows), min(N_SHAP, int(rows.sum())), replace=False)
            sv = np.asarray(shap.TreeExplainer(m).shap_values(X.iloc[take].to_numpy()))  # n × f × k
            if sv.ndim == 2:
                sv = sv[..., None]
            for j, c in enumerate(m.classes_):
                for f_i, f in enumerate(X.columns):
                    shap_rows.append(dict(target=tg, tier=tier, cls=c, feature=f,
                                          mean_abs_shap=float(np.abs(sv[:, f_i, j]).mean())))
            shap_store[(tg, tier)] = (X.iloc[take], sv, list(m.classes_))
    shap_imp = pd.DataFrame(shap_rows)

    # --- surface rock alteration -----------------------------------------------------------
    rock = pd.read_csv(I / "04_rock.csv", low_memory=False)
    rj = rock[rock.is_RJ.astype(bool)].copy()
    rj["block"] = cl.spatial_blocks(rj.Easting, rj.Northing, BLOCK_M)
    rclasses = ["SI", "AR", "PP"]
    ry = rj.alt_ml_label.where(rj.alt_ml_label.isin(rclasses))
    rfeats = {t: cl.log_features(rj, *spec) for t, spec in ROCK_TIERS.items()}
    folds = cl.group_folds(rj.block, ROCK_SPLITS)
    print(f"\nrock RJ {len(rj)}: blocks {rj.block.nunique()}, labels {ry.value_counts().to_dict()}")
    rconf, rjobs = [], []
    for tier, X in rfeats.items():
        rows = cl.complete(X)
        print(f"rock tier {tier}: rows {rows.sum()} (labelled {(rows & ry.notna()).sum()})")
        for kind in cl.MODELS:
            j = cl.oof_jobs(X[rows], ry[rows], rj.block[rows], rclasses, kind,
                            folds=[f & set(rj.block[rows]) for f in folds if f & set(rj.block[rows])])
            rconf.append((tier, kind, rows, len(j)))
            rjobs += j
    rres = Parallel(n_jobs=-1)(delayed(cl.fold_job)(*j) for j in rjobs)
    roof, k = {}, 0
    for tier, kind, rows, nj in rconf:
        P, leaves = cl.collect(int(rows.sum()), rclasses, rres[k:k + nj])
        k += nj
        full = np.full((len(rj), 3), np.nan)
        full[rows.to_numpy()] = P
        roof[(tier, kind)] = (full, rows)
        yv, g = ry.to_numpy(object), rj.block.to_numpy(object)
        rv = rows.to_numpy()
        s = score_rows(yv[rv], P, rclasses, g[rv])
        if kind != "dummy":
            lab = pd.notna(yv[rv])
            s["ci05"], s["ci95"] = cl.group_bootstrap(yv[rv][lab], cl.predict(P[lab], rclasses), g[rv][lab], B=B_CI)
        if kind == "rf":
            s["leaf_mode"] = int(pd.Series(leaves).mode().iloc[0])
        sc = pd.concat([sc, pd.DataFrame([dict(dataset="batuan", target="alt_batuan", tier=tier, model=kind,
                                               cv=f"blok{int(BLOCK_M)}m", subset="semua", **s)])], ignore_index=True)
    r2 = sc[(sc.dataset == "batuan") & (sc.model == "rf")].set_index("tier").bal_acc
    PA_r, rows_r = roof[("R1", "rf")]
    P2, rows2 = roof[("R2", "rf")]
    same = rows2.to_numpy() & ry.notna().to_numpy()
    yv = ry.to_numpy(object)
    gain_r = (balanced_accuracy_score(yv[same], cl.predict(P2[same], rclasses))
              - balanced_accuracy_score(yv[same], cl.predict(PA_r[same], rclasses)))
    gain_rows.append(dict(target="alt_batuan", tier="R2", gain_vs_A_same_rows=gain_r))
    PR = PA_r.copy()
    rtier = pd.Series(np.where(rows_r, "R1", None), index=rj.index, dtype=object)
    if gain_r > 0:
        PR[rows2.to_numpy()] = P2[rows2.to_numpy()]
        rtier[rows2] = "R2"
    okr = ~np.isnan(PR[:, 0])
    rml = pd.DataFrame({"SampleID": rock.SampleID})
    pr = pd.Series(np.where(okr, cl.predict(np.nan_to_num(PR, nan=0), rclasses), None), index=rj.index)
    pm = pd.Series(np.where(okr, np.nan_to_num(PR, nan=-1).max(axis=1), np.nan), index=rj.index)
    rcols = {"ML_alt_prediksi": pr.map(ALT_ID), "ML_alt_p_maks": pm.round(4),
             "ML_alt_ambigu": pd.Series(np.where(okr, np.where(pm < P_AMBIG, "Y", "N"), None), index=rj.index)}
    for j, c in enumerate(rclasses):
        rcols[f"ML_alt_p_{c}"] = pd.Series(np.where(okr, PR[:, j], np.nan), index=rj.index).round(4)
    rcols["ML_alt_tier"] = rtier
    for c, v in rcols.items():
        rml[c] = v.reindex(rock.index)
    # label-mismatch check: drillhole alteration model (no Ag) applied to RJ rock
    Xd = feats["A_tanpaAg"]
    rowsd = cl.complete(Xd) & T["alt"][0].notna()
    md = cl.rf(5).set_params(n_jobs=-1).fit(Xd[rowsd].to_numpy(), T["alt"][0][rowsd].to_numpy(object))
    Xr = cl.log_features(rj, *TIERS["A_tanpaAg"])
    okx = cl.complete(Xr)
    transfer = pd.crosstab(rj.alt_ml_label[okx].rename("log_batuan"),
                           pd.Series(md.predict(Xr[okx].to_numpy()), index=Xr[okx].index).rename("prediksi_model_bor"))
    print("\ndrillhole alteration model applied to RJ rock (rows = logged surface facies):")
    print(transfer.to_string())

    # --- write -----------------------------------------------------------------------------
    for m_, key_df, nm in ((ml, raw, "assay"), (rml, rock, "batuan")):
        assert len(m_) == len(key_df) and m_.SampleID.is_unique
        m_.to_csv(ml_dir / f"{nm}__ml2_classify.csv", index=False)
    assert ml.loc[raw.no_sample.astype(bool).to_numpy(), [c for c in ml if c.startswith("ML_")]].isna().all().all()
    assert rml.loc[~rock.is_RJ.astype(bool).to_numpy(), [c for c in rml if c.startswith("ML_")]].isna().all().all()
    sc.to_csv(paths.PROCESSED / "ml2_scores.csv", index=False)
    review.to_csv(paths.PROCESSED / "ml2_review_list.csv", index=False)
    shap_imp.to_csv(paths.PROCESSED / "ml2_shap_importance.csv", index=False)
    pd.DataFrame(per_pad).to_csv(paths.PROCESSED / "ml2_per_pad.csv", index=False)
    transfer.to_csv(paths.PROCESSED / "ml2_rock_transfer.csv")

    # --- figures ---------------------------------------------------------------------------
    plot_scores(sc, paths.FIGURES / "09_skor_v1.png")
    conf = {tg: (T[tg][0], export_P[tg], T[tg][2], T[tg][5]) for tg in T}
    conf["alt_batuan"] = (ry, PR, rclasses, ALT_ID)
    plot_confusion(conf, paths.FIGURES / "09_matriks_konfusi_v1.png")
    plot_shap(shap_imp, paths.FIGURES / "09_shap_v1.png")
    plot_dependence(shap_store, paths.FIGURES / "09_shap_dependensi_v1.png")
    plot_reliability({tg: conf[tg] for tg in ("alt", "oks", "lit", "alt_batuan")},
                     paths.FIGURES / "09_reliabilitas_v1.png")
    plot_per_pad(pd.DataFrame(per_pad), paths.FIGURES / "09_skor_pad_v1.png")

    # --- summary ---------------------------------------------------------------------------
    show = sc[sc.subset.eq("semua")][["dataset", "target", "tier", "model", "cv", "n", "n_groups", "bal_acc",
                                      "ci05", "ci95", "macro_f1", "kappa", "pr_auc", "prevalence", "leaf_mode"]]
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 200):
        print("\n" + show.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        sub = sc[(sc.model == "rf") & (sc.cv == "pad") & (sc.tier.isin(["A", "ekspor"]) | sc.tier.str.startswith("B"))
                 & sc.subset.isin(["bersih", "batas"])][["target", "tier", "subset", "n", "bal_acc"]]
        print("\nclean vs boundary assays (RF, pads):\n" + sub.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        rec = sc[(sc.tier == "ekspor") | ((sc.dataset == "batuan") & (sc.model == "rf"))]
        print("\nper-class recall / precision (export):")
        print(rec[["target", "tier"] + [c for c in sc if c.startswith(("recall_", "precision_"))]]
              .dropna(axis=1, how="all").to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        print("\ntier gain vs A on same rows (RF balanced accuracy):\n"
              + pd.DataFrame(gain_rows).to_string(index=False, float_format=lambda x: f"{x:+.3f}"))
        top = (shap_imp.groupby(["target", "tier", "feature"]).mean_abs_shap.mean().reset_index()
               .sort_values(["target", "tier", "mean_abs_shap"], ascending=[True, True, False])
               .groupby(["target", "tier"]).head(3))
        print("\ntop SHAP features (mean |SHAP| over classes):\n" + top.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        for tg in T:
            print(f"export tier use {tg}: {export_tier[tg].value_counts().to_dict()}")
        print(f"rock export tier use: {rtier.value_counts().to_dict()}")
        print("\nreview runs per target and hole:\n"
              + review.groupby(["target", "SiteID"]).length_m.agg(["size", "sum"]).unstack(0).fillna(0).to_string())
    print("\noutputs: data/processed/ml/{assay,batuan}__ml2_classify.csv; data/processed/ml2_*.csv; "
          "outputs/figures/09_*_v1.png")


# --- plots -----------------------------------------------------------------------------------
def _clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def plot_scores(sc: pd.DataFrame, path) -> None:
    """Balanced accuracy per target × tier: RF (CI), logistic, prior baseline, RF leave-one-hole-out."""
    s = sc[sc.subset.eq("semua") & ~sc.tier.str.startswith("A pada") & sc.tier.ne("A_tanpaAg")]
    keys = s[s.model.eq("rf") & s.cv.ne("hole")][["target", "tier"]].drop_duplicates().to_numpy().tolist()
    fig, ax = plt.subplots(figsize=(7.5, 0.32 * len(keys) + 1.2))
    for i, (tg, tier) in enumerate(keys):
        r = s[(s.target == tg) & (s.tier == tier)]
        def val(model, cv=None):
            q = r[(r.model == model) & (r.cv != "hole" if cv is None else r.cv == cv)]
            return q.iloc[0] if len(q) else None
        rf = val("rf")
        ax.plot([rf.ci05, rf.ci95], [i, i], color=C_RF, lw=2, alpha=0.35, solid_capstyle="butt")
        for model, mk, col in (("dummy", "|", C_DUM), ("logreg", "s", C_LR), ("rf", "o", C_RF)):
            q = val(model)
            if q is not None:
                ax.plot(q.bal_acc, i, mk, color=col, ms=6 if mk != "|" else 10, mew=2)
        h = val("rf", "hole")
        if h is not None:
            ax.plot(h.bal_acc, i, "o", mfc="none", mec=C_INK, ms=7)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([f"{TARGET_ID[tg]} · {tier}" for tg, tier in keys], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0.2, 1.0)
    ax.set_xlabel("Akurasi seimbang (validasi silang tanpa pad / blok yang sama)", fontsize=8.5)
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="x", color="#e6e5e0", lw=0.6)
    _clean(ax)
    ax.legend(handles=[Line2D([], [], marker="o", color=C_RF, ls="", label="Random Forest"),
                       Line2D([], [], color=C_RF, lw=2, alpha=0.35, label="Selang bootstrap pad 5–95%"),
                       Line2D([], [], marker="s", color=C_LR, ls="", label="Regresi logistik"),
                       Line2D([], [], marker="|", color=C_DUM, ls="", ms=10, mew=2, label="Acuan (proporsi kelas)"),
                       Line2D([], [], marker="o", mfc="none", mec=C_INK, ls="", label="RF, tanpa lubang yang sama")],
              fontsize=7, frameon=False, loc="lower right")
    ax.set_title("Prediksi kelas log dari kimia: skor per target dan set fitur", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_confusion(conf: dict, path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(12, 7.6))
    for ax, (tg, (y, P, classes, lmap)) in zip(axes.ravel(), conf.items()):
        yv = pd.Series(y).to_numpy(object)
        ok = ~np.isnan(P[:, 0]) & pd.notna(yv)
        cm = confusion_matrix(yv[ok], cl.predict(P[ok], classes), labels=classes)
        cmn = cm / cm.sum(axis=1, keepdims=True).clip(min=1)
        ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
        for i in range(len(classes)):
            for j in range(len(classes)):
                ax.text(j, i, f"{cmn[i, j]:.2f}\n({cm[i, j]})", ha="center", va="center", fontsize=7,
                        color="white" if cmn[i, j] > 0.6 else C_INK)
        lab = [lmap[c] for c in classes]
        ax.set_xticks(range(len(classes)))
        ax.set_xticklabels(lab, fontsize=7, rotation=30, ha="right")
        ax.set_yticks(range(len(classes)))
        ax.set_yticklabels(lab, fontsize=7)
        ax.set_xlabel("Prediksi ML", fontsize=8)
        ax.set_ylabel("Log geologi", fontsize=8)
        ax.set_title(f"{TARGET_ID[tg]} (n {ok.sum()}, akurasi seimbang "
                     f"{balanced_accuracy_score(yv[ok], cl.predict(P[ok], classes)):.2f})", fontsize=9)
    fig.suptitle("Matriks konfusi (proporsi per baris log; prediksi di luar pad/blok latih)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _feat_label(f: str) -> str:
    return FEAT_ID.get(f, f)


def plot_shap(imp: pd.DataFrame, path) -> None:
    """Mean |SHAP| per feature, stacked by class, tier B (alteration, oxidation, lithology)."""
    cmap = plt.get_cmap("tab10")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, tg in zip(axes, ("alt", "oks", "lit")):
        d = imp[(imp.target == tg) & (imp.tier == "B")].pivot(index="feature", columns="cls", values="mean_abs_shap")
        d = d.loc[d.sum(axis=1).sort_values().index]
        left = np.zeros(len(d))
        lmap = {"alt": ALT_ID, "oks": OX_ID, "lit": LIT_ID}[tg]
        for j, c in enumerate(d.columns):
            ax.barh([_feat_label(f) for f in d.index], d[c], left=left, color=cmap(j), label=lmap.get(c, c))
            left += d[c].to_numpy()
        ax.set_xlabel("Rerata |SHAP| (peluang kelas)", fontsize=8)
        ax.tick_params(labelsize=7.5)
        ax.set_title(f"{TARGET_ID[tg]} (fitur set B)", fontsize=9)
        ax.legend(fontsize=6.5, frameon=False, loc="lower right")
        _clean(ax)
    fig.suptitle("Kontribusi unsur terhadap prediksi (SHAP, Random Forest)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_dependence(store: dict, path) -> None:
    """SHAP vs element value (element units, log axis) for the top features of two classes."""
    picks = [("alt", "SI"), ("oks", "Sulphide")]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.4))
    for row, (tg, cls_) in zip(axes, picks):
        X, sv, classes = store[(tg, "B")]
        j = classes.index(cls_)
        order = np.argsort(-np.abs(sv[:, :, j]).mean(axis=0))[:3]
        for ax, f_i in zip(row, order):
            f = X.columns[f_i]
            ax.scatter(10 ** X.iloc[:, f_i], sv[:, f_i, j], s=6, color=C_RF, alpha=0.5, lw=0)
            ax.set_xscale("log")
            ax.axhline(0, color=C_INK2, lw=0.6)
            u = UNIT.get(f, "rasio")
            ax.set_xlabel(f"{_feat_label(f)} ({u}, skala log)", fontsize=8)
            ax.set_ylabel(f"SHAP → peluang {({**ALT_ID, **OX_ID})[cls_]}", fontsize=8)
            ax.tick_params(labelsize=7)
            _clean(ax)
    fig.suptitle("Ketergantungan SHAP: bagaimana nilai unsur mengubah peluang kelas (fitur set B)", fontsize=10.5)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_reliability(conf: dict, path) -> None:
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.plot([0, 1], [0, 1], color=C_DUM, lw=1, ls=(0, (3, 2)))
    cmap = plt.get_cmap("tab10")
    for k, (tg, (y, P, classes, _m)) in enumerate(conf.items()):
        yv = pd.Series(y).to_numpy(object)
        ok = ~np.isnan(P[:, 0]) & pd.notna(yv)
        r = cl.reliability(yv[ok], P[ok], classes)
        r = r[r.n >= 10]
        ax.plot(r.conf, r.acc, "o-", color=cmap(k), ms=3.5, lw=1.2, label=TARGET_ID[tg])
    ax.set_xlabel("Peluang kelas teratas (keyakinan ML)", fontsize=8.5)
    ax.set_ylabel("Proporsi cocok dengan log", fontsize=8.5)
    ax.set_xlim(0.2, 1)
    ax.set_ylim(0, 1)
    ax.tick_params(labelsize=7.5)
    ax.legend(fontsize=7, frameon=False)
    _clean(ax)
    ax.set_title("Keandalan peluang (kelas ≥ 10 sampel per selang)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_per_pad(pp: pd.DataFrame, path) -> None:
    d = pp.pivot(index="pad", columns="target", values="bal_acc")[["alt", "oks", "lit", "py", "cu"]]
    fig, ax = plt.subplots(figsize=(5.2, 0.32 * len(d) + 1.2))
    ax.imshow(d.to_numpy(float), cmap="Blues", vmin=0, vmax=1, aspect="auto")
    for i in range(d.shape[0]):
        for j in range(d.shape[1]):
            v = d.iat[i, j]
            ax.text(j, i, "—" if pd.isna(v) else f"{v:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if pd.notna(v) and v > 0.6 else C_INK)
    ax.set_xticks(range(d.shape[1]))
    ax.set_xticklabels([TARGET_ID[c] for c in d.columns], fontsize=7.5)
    ax.set_yticks(range(d.shape[0]))
    ax.set_yticklabels(d.index, fontsize=7.5)
    ax.set_title("Akurasi seimbang per pad yang ditahan (RF, set A)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
