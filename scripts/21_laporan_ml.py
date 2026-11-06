"""Teammate ML findings report (Bahasa Indonesia, English terms in brackets): one self-contained local
HTML file. Plan: LOG.md, 2026-11-04 entry "Plan: ML findings report for teammates".

The text is hand-written in reports/laporan_ml_src.html. Headline numbers there are {{key}}
placeholders filled from the processed CSVs below, so the report cannot drift from the results; the
build fails on any unresolved placeholder, missing figure or dangling internal link. Figures are the
existing outputs (no new figures), embedded as base64 and downscaled. Nothing leaves this machine.
Reads data/processed/{ml2_scores,ml3_summary,ml4_summary,ml4_states,ml5_summary,ml5_conformal,
ml5_per_hole,ml5_uji_nag,ml6_summary,ml6_cv,drainase_ringkasan,s9_jansson_scores,
s9_rf_smoother_scores,s9_rf_smoother_kembar,validation_summary}.csv;
and s1_ambang_perbandingan_v1 (ioGAS Stage 1); writes outputs/laporan_ml/laporan_ml_v2.html
(v2, 6 Nov: ioGAS threshold comparison and ioGAS figure pointers; v1 is frozen).
Run: PYTHONIOENCODING=utf-8 uv run python scripts/21_laporan_ml.py
"""
import ast
import json
import sys

import pandas as pd

from src import paths, report as rp

SRC = paths.ROOT / "reports" / "laporan_ml_src.html"
OUT = paths.ROOT / "outputs" / "laporan_ml" / "laporan_ml_v2.html"
MAX_PX = 1800
P = paths.PROCESSED


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(P / f"{name}.csv", encoding="utf-8-sig")


def f2(x) -> str:
    return rp.fmt_id(float(x), 2)


def f0(x) -> str:
    return rp.fmt_id(float(x), 0)


def facts_validation(f: dict) -> None:
    v = read("validation_summary")
    q2 = v[v.check_id == "Q2"].set_index("dataset").n_flagged
    f["val_zero_rock"], f["val_zero_soil"] = f0(q2["rock"]), f0(q2["soil"])
    f["val_elev"] = f0(v.loc[v.check_id == "S1", "n_flagged"].iloc[0])
    f["val_n_checks"] = f0(v.check_id.nunique())


def facts_ml2(f: dict) -> None:
    s = read("ml2_scores")
    bor = s[(s.dataset == "bor") & (s.model == "rf") & (s.cv == "pad") & (s.subset == "semua")]
    for key, target, tier in [("alt", "alt", "A"), ("oks", "oks", "B"), ("lit", "lit", "B"),
                              ("py", "py", "B"), ("cu", "cu", "A")]:
        r = bor[(bor.target == target) & (bor.tier == tier)].iloc[0]
        f[f"ml2_{key}"] = f2(r.bal_acc)
        f[f"ml2_{key}_ci"] = f"{f2(r.ci05)}–{f2(r.ci95)}"
    rock = s[(s.dataset == "batuan") & (s.tier == "R2") & (s.model == "rf")].iloc[0]
    f["ml2_rock"] = f2(rock.bal_acc)


def facts_ml3(f: dict) -> None:
    s = read("ml3_summary").set_index(["dataset", "zone"])
    for ds in ("tanah", "batuan"):
        for z, k in (("Rendah", "R"), ("Sedang", "S"), ("Tinggi", "T")):
            r = s.loc[(ds, z)]
            f[f"ml3_{ds}_n_{k}"] = f0(r.n)
            f[f"ml3_{ds}_au_{k}"] = rp.fmt_id(float(r.Au_median), 3 if ds == "tanah" else 2)
            f[f"ml3_{ds}_stabil_{k}"] = f2(r.mean_stabil)
        f[f"ml3_{ds}_n"] = f0(s.loc[ds].n.sum())


def facts_ml4(f: dict) -> None:
    s = read("ml4_summary")
    h = s[s.kind == "hyperparameter"].set_index("name").value
    f["ml4_K"] = h["K_selected"]
    f["ml4_n"] = f0(h["n_composites"])
    f["ml4_boot_ari"] = f2(h["boot_ari_median"])
    f["ml4_boot_ari_ci"] = f"{f2(h['boot_ari_05'])}–{f2(h['boot_ari_95'])}"
    st = read("ml4_states").set_index("state")
    for i, r in st.iterrows():
        f[f"ml4_S{i}_n"] = f0(r.n)
        f[f"ml4_S{i}_holes"] = f0(r.n_holes)
        f[f"ml4_S{i}_au"] = rp.fmt_id(float(r.Au_gmean), 3 if r.Au_gmean < 0.1 else 2)
        f[f"ml4_S{i}_cu"] = f0(r.Cu_gmean)
        f[f"ml4_S{i}_run"] = rp.fmt_id(float(r.run_m), 1)
        f[f"ml4_S{i}_stabil"] = f2(r.stability_median)


def facts_ml5(f: dict) -> None:
    s = read("ml5_summary").set_index("item").nilai
    for k in ("NAF", "PAF-LC", "PAF-HC"):
        f[f"ml5_n_{k.replace('-', '')}"] = s[f"n {k}"]
    c = read("ml5_conformal")
    c = c[(c.fitur == "transfer") & (c.model == "rf") & (c.blok_m == 10) & (c.alpha == 0.1)
          & (c.subset == "semua")].set_index("kelas")
    for k in ("NAF", "PAF-LC", "PAF-HC", "semua"):
        kk = k.replace("-", "")
        f[f"ml5_cov_{kk}"] = f2(c.loc[k, "cakupan"])
        f[f"ml5_size_{kk}"] = f2(c.loc[k, "ukuran_set"])
        f[f"ml5_single_{kk}"] = f0(100 * c.loc[k, "singleton"])
    tot = read("ml5_per_hole").set_index("SiteID").loc["TOTAL"]
    for col, key in (("m_NAF", "NAF"), ("m_PAF-LC", "PAFLC"), ("m_PAF-HC", "PAFHC"),
                     ("m_PAF-HC_pasti", "PAFHC_pasti")):
        f[f"ml5_m_{key}"] = f0(tot[col])
    u = read("ml5_uji_nag")
    f["ml5_nag_runs"], f["ml5_nag_m"] = f0(len(u)), f0(u.length_m.sum())
    p1 = u[u.prioritas.astype(str).str.startswith("1")]
    f["ml5_nag_p1_runs"], f["ml5_nag_p1_m"] = f0(len(p1)), f0(p1.length_m.sum())


def facts_ml6(f: dict) -> None:
    s = read("ml6_summary").set_index("item").nilai
    ls = ast.literal_eval(s["length_scales_m"])[0]
    f["ml6_ls_along"], f["ml6_ls_across"], f["ml6_ls_vert"] = (rp.fmt_id(x, 1) for x in ls)
    skill = json.loads(s["skill_vs_mean"])
    f["ml6_pads_better"], f["ml6_n_pads"] = skill["pads_better"], skill["n_pads"]
    f["ml6_dmlpd"] = rp.fmt_id(skill["delta_mlpd_vs_mean"], 3)
    f["ml6_dmlpd_se"] = rp.fmt_id(skill["se"], 3)
    f["ml6_reaches"], f["ml6_ragu"] = s["drainage_reaches"], s["drainage_ragu"]
    f["ml6_collar_A"], f["ml6_collar_A_pass"] = f0(s["n_collar_A"]), f0(s["n_collar_A_pass"])
    d = read("drainase_ringkasan").set_index("ambang")
    f["ml6_drain_m"] = f0(d.loc["2ha", "panjang_m"])


def facts_s9(f: dict) -> None:
    j = read("s9_jansson_scores").set_index(["kasus", "metode"])
    f["s9_u1_gmm_oks"] = f2(j.loc[("U1", "GMM (pipeline kami)"), "ARI_oksidasi"])
    f["s9_u1_km_oks"] = f2(j.loc[("U1", "k-means (K_GMM)"), "ARI_oksidasi"])
    f["s9_rock_km_gmm"] = f2(j.loc[("batuan", "k-means (K_GMM)"), "ARI_GMM"])
    r = read("s9_rf_smoother_scores").set_index(["target", "metode"])
    f["s9_rf_alt_V"] = f2(r.loc[("alterasi", "RF dihaluskan"), "V"])
    f["s9_hmm_alt_V"] = f2(r.loc[("alterasi", "HMM (ML-4)"), "V"])
    for key, idx in (("rf_raw", ("alterasi", "RF mentah")), ("rf_smooth", ("alterasi", "RF dihaluskan")),
                     ("hmm", ("alterasi", "HMM (ML-4)")), ("log_alt", ("alterasi", "Log alterasi")),
                     ("log_oks", ("oksidasi", "Log oksidasi"))):
        f[f"s9_sw_{key}"] = rp.fmt_id(float(r.loc[idx, "switch_per_100m"]), 1)
    k = read("s9_rf_smoother_kembar")
    k = k[k.d_from == 0].set_index("label").agree
    f["s9_twin_hmm"] = f2(k["HMM (ML-4)"])
    f["s9_twin_log"] = f2(k["Log alterasi"])
    f["s9_twin_rf"] = f2(k["RF dihaluskan (alterasi)"])


def facts_iogas(f: dict) -> None:
    """Probability-plot picks (ioGAS, blind) vs nearest GMM break: agreement counts, no ranking."""
    d = read("s1_ambang_perbandingan_v1")
    k1, k2 = d.pp1_kesesuaian_T.astype(str), d.pp2_kesesuaian_T.astype(str)
    near = ~k1.str.startswith("berbeda") | ~k2.str.startswith("berbeda")
    f["thr_n"] = len(d)
    f["thr_dekat"] = int(near.sum())
    f["thr_beda"] = int((~near).sum())
    f["thr_ci"] = int((k1.str.startswith("dalam") | k2.str.startswith("dalam")).sum())


def build_facts() -> dict:
    f: dict = {}
    for fn in (facts_validation, facts_ml2, facts_ml3, facts_ml4, facts_ml5, facts_ml6, facts_s9, facts_iogas):
        fn(f)
    return {k: str(v) for k, v in f.items()}


def main() -> None:
    facts = build_facts()
    html = rp.fill_facts(SRC.read_text(encoding="utf-8"), facts)
    dangling = rp.check_links(html)
    if dangling:
        sys.exit(f"dangling internal links: {dangling}")
    html, used = rp.embed_images(html, paths.ROOT, MAX_PX)
    assert 'src="outputs/' not in html
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"facts {len(facts)}, figures {len(used)}, {OUT.stat().st_size / 1e6:.1f} MB -> {OUT}")


if __name__ == "__main__":
    main()
