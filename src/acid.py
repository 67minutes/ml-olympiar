"""ML-5: PAF/NAF classes from NAG tests and Mondrian conformal prediction (AGENTS.md §6 task 5).

Labels come from RJDH012 NAG tests only: NAG pH < 4.5 means potentially acid forming (PAF);
the NAG capacity titrated to pH 4.5 splits PAF into low and high capacity. ANC was not
measured, so this capacity stands in for NAPP in the AMIRA (2002) PAF-LC definition.

Conformal prediction is Mondrian (class-conditional) and cross-conformal: each fold model
scores its own held-out rows (calibration) and every new row, and p-values pool the counts
over folds. A class enters a row's prediction set when its p-value exceeds alpha, so each
true class is covered at about 1 - alpha for exchangeable (RJDH012-like) material.
"""
import numpy as np
import pandas as pd

CLASSES = ("NAF", "PAF-LC", "PAF-HC")   # ordered by risk
PH_CUT = 4.5
CAP_CUT = 10.0                          # kg H2SO4/t at pH 4.5
MPA_FACTOR = 30.6                       # kg H2SO4/t per % S (pyrite stoichiometry)
ANC_CA = 10 * 98.08 / 40.08             # kg H2SO4/t per % Ca as CaCO3 (24.5)
ANC_MG = 10 * 98.08 / 24.305            # kg H2SO4/t per % Mg as MgCO3 (40.4)


# --- labels and NAPP proxy ---------------------------------------------------------
def nag_class(ph, cap, cap_cut: float = CAP_CUT) -> np.ndarray:
    """NAF / PAF-LC / PAF-HC from NAG pH and NAG capacity at pH 4.5 (None without NAG)."""
    ph, cap = np.asarray(ph, float), np.asarray(cap, float)
    out = np.where(ph >= PH_CUT, "NAF", np.where(cap >= cap_cut, "PAF-HC", "PAF-LC")).astype(object)
    out[np.isnan(ph)] = None
    return out


def napp_proxy(s_scis, s_total, ca, mg) -> pd.DataFrame:
    """MPA from SCIS and total S (SCIS is not proven to be reactive sulfide), an upper-bound ANC (all Ca and Mg as carbonate) and
    the lower-bound NAPP it implies (kg H2SO4/t). A positive NAPP_min rules PAF in."""
    ss, st, ca, mg = (np.asarray(v, float) for v in (s_scis, s_total, ca, mg))
    anc = ANC_CA * ca + ANC_MG * mg
    return pd.DataFrame({"MPA_SCIS": MPA_FACTOR * ss, "MPA_total": MPA_FACTOR * st, "ANC_maks": anc,
                         "NAPP_min_SCIS": MPA_FACTOR * ss - anc, "NAPP_min_total": MPA_FACTOR * st - anc})


# --- validation folds --------------------------------------------------------------
def depth_blocks(depth_from, size: float) -> np.ndarray:
    """Contiguous depth block per interval (floor of DepthFrom / size)."""
    return np.floor(np.asarray(depth_from, float) / size).astype(int)


# --- conformal ---------------------------------------------------------------------
def nonconformity(P: np.ndarray) -> np.ndarray:
    """Score of every candidate class: 1 - its predicted probability (n × classes)."""
    return 1.0 - np.asarray(P, float)


def mondrian_pvalues(cal: list[tuple[np.ndarray, np.ndarray]], test: list[np.ndarray],
                     classes=CLASSES) -> np.ndarray:
    """Cross-conformal class-conditional p-values.

    cal: per fold, (P_heldout, y_heldout) from that fold's model on its held-out rows.
    test: per fold, that fold's model's probabilities for the rows to predict (n × classes).
    p_c(x) = (sum over folds of #{held-out i with y_i = c and score_i >= score_k(x, c)} + 1)
             / (n_c + 1), where score = 1 - p(class)."""
    classes = list(classes)
    n = len(test[0])
    count = np.zeros((n, len(classes)))
    n_c = np.zeros(len(classes))
    for (P_cal, y_cal), P_test in zip(cal, test, strict=True):
        y_cal = np.asarray(y_cal, dtype=object)
        A_test = nonconformity(P_test)
        for j, c in enumerate(classes):
            m = y_cal == c
            if not m.any():
                continue
            a_cal = 1.0 - np.asarray(P_cal, float)[m, j]
            n_c[j] += m.sum()
            count[:, j] += (a_cal[None, :] >= A_test[:, j, None] - 1e-12).sum(axis=1)
    if (n_c == 0).any():
        raise ValueError("a class has no calibration rows")
    return (count + 1) / (n_c + 1)


def prediction_sets(pval: np.ndarray, alpha: float) -> np.ndarray:
    return np.asarray(pval) > alpha


def set_label(S: np.ndarray, classes=CLASSES) -> np.ndarray:
    """'NAF|PAF-LC'-style text per row ('kosong' for an empty set)."""
    return np.array(["|".join(c for c, s in zip(classes, row) if s) or "kosong" for row in S], dtype=object)


def manage(S: np.ndarray, pval: np.ndarray, classes=CLASSES) -> np.ndarray:
    """Conservative management class: the highest-risk class in the set. An empty set (no
    class fits) is handled as the riskier of PAF-LC and the class with the largest p-value."""
    S = np.asarray(S, bool)
    risk = np.arange(len(classes))
    top = np.where(S.any(axis=1), (S * (risk + 1)).max(axis=1) - 1,
                   np.maximum(np.argmax(pval, axis=1), list(classes).index("PAF-LC")))
    return np.asarray(classes, dtype=object)[top]


def coverage(y, S: np.ndarray, classes=CLASSES) -> pd.DataFrame:
    """Per true class: n, coverage (true class in set), mean set size, singleton share."""
    y = np.asarray(y, dtype=object)
    rows = []
    for j, c in enumerate(classes):
        m = y == c
        if m.any():
            rows.append({"kelas": c, "n": int(m.sum()), "cakupan": float(S[m, j].mean()),
                         "ukuran_set": float(S[m].sum(1).mean()), "singleton": float((S[m].sum(1) == 1).mean())})
    rows.append({"kelas": "semua", "n": len(y), "cakupan": float(S[np.arange(len(y)),
                 [list(classes).index(v) for v in y]].mean()),
                 "ukuran_set": float(S.sum(1).mean()), "singleton": float((S.sum(1) == 1).mean())})
    return pd.DataFrame(rows)


# --- tiers and runs ----------------------------------------------------------------
def tier(has_scis, has_s2, transition, out_of_range) -> np.ndarray:
    """1: SCIS, RJDH012-like; 2: SCIS but Transition or a feature beyond the training range;
    3: S2 in place of SCIS; 4: no sulfur."""
    has_scis, has_s2, transition, oor = (np.asarray(v, bool) for v in (has_scis, has_s2, transition, out_of_range))
    return np.where(has_scis, np.where(transition | oor, 2, 1), np.where(has_s2, 3, 4))


def merge_runs(d: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Contiguous runs per hole: rows (SiteID, DepthFrom, DepthTo, *by) are joined while the
    next interval starts where the last ended and `by` values are equal."""
    s = d.sort_values(["SiteID", "DepthFrom"])
    rows, cur = [], None
    for r in s.itertuples(index=False):
        key = tuple(getattr(r, b) for b in by)
        if cur and r.SiteID == cur["SiteID"] and np.isclose(r.DepthFrom, cur["to"]) and key == cur["key"]:
            cur["to"], cur["n"] = r.DepthTo, cur["n"] + 1
            continue
        if cur:
            rows.append(cur)
        cur = {"SiteID": r.SiteID, "from": r.DepthFrom, "to": r.DepthTo, "n": 1, "key": key}
    if cur:
        rows.append(cur)
    out = pd.DataFrame([{"SiteID": c["SiteID"], "from": c["from"], "to": c["to"], "length_m": c["to"] - c["from"],
                         "n": c["n"], **dict(zip(by, c["key"]))} for c in rows],
                       columns=["SiteID", "from", "to", "length_m", "n", *by])
    return out.round({"from": 2, "to": 2, "length_m": 2})
