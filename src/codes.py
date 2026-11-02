"""Code harmonisation for the downhole logs and rock samples (Stage 4, AGENTS.md §5.3).

Originals are never changed: harmonised values go to new columns. Every code in a coded
column must be in a vocabulary below, otherwise lookup() raises.

Sources: "resume" = Geological Resume_OlympiAR_2026.pdf; "conventional" = standard logging
abbreviation, not confirmed by a project legend; "inferred" = meaning derived from the data
(evidence in the entry, re-checked in scripts/04_codes.py); "VERIFY" = unresolved.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

# group key -> (EN, ID)
LITH_GROUP_NAMES = {
    "porphyry": ("Coherent dacite-andesite porphyry", "Porfiri dasit-andesit koheren"),
    "andesite": ("Andesite (Angkola Volcanics)", "Andesit (Vulkanik Angkola)"),
    "bx_phreato": ("Phreatomagmatic breccia", "Breksi freatomagmatik"),
    "bx_hydro": ("Hydrothermal breccia", "Breksi hidrotermal"),
    "bx_other": ("Unclassified breccia", "Breksi tak terklasifikasi"),
    "fault": ("Fault zone", "Zona sesar"),
    "sediment": ("Sedimentary / volcaniclastic", "Sedimen / vulkaniklastik"),
    "cover": ("Surface cover", "Penutup permukaan"),
    "void": ("Void (cavity)", "Rongga"),
    "quartz": ("Quartz / silica", "Kuarsa / silika"),
}

# vocabulary -> code -> (meaning_en, meaning_id, source, evidence / note, group key or None)
VOCAB = {
    "lith": {
        "VANh": ("hornblende andesite", "andesit hornblenda", "resume", "", "porphyry"),
        "VDA": ("dacite porphyry", "porfiri dasit", "resume", "", "porphyry"),
        "VAN": ("porphyritic andesite (Angkola Volcanics)", "andesit porfiritik (Vulkanik Angkola)",
                "resume", "", "andesite"),
        "BPM": ("phreatomagmatic breccia", "breksi freatomagmatik", "resume", "", "bx_phreato"),
        "sBPM": ("silicified phreatomagmatic breccia", "breksi freatomagmatik tersilisifikasi", "resume",
                 "resume spells it sBMP", "bx_phreato"),
        "XUS": ("unstratified sandy-matrix lithic breccia", "breksi litik matriks pasir tak berlapis",
                "resume", "interpreted as phreatomagmatic", "bx_phreato"),
        "XUS-l": ("unstratified sandy-matrix lithic breccia (l variant)", "breksi litik matriks pasir tak berlapis (varian l)",
                  "inferred", "XUS subtype; suffix meaning unknown", "bx_phreato"),
        "XUQ-w": ("unstratified white-quartz matrix breccia", "breksi matriks kuarsa putih tak berlapis",
                  "resume", "", "bx_hydro"),
        "XUQ-b": ("unstratified black-quartz matrix breccia", "breksi matriks kuarsa hitam tak berlapis",
                  "resume", "", "bx_hydro"),
        "XUQ-ms": ("unstratified massive-sulphide matrix breccia", "breksi matriks sulfida masif tak berlapis",
                   "resume", "", "bx_hydro"),
        "XUlo": ("unstratified iron-oxide matrix breccia", "breksi matriks oksida besi tak berlapis",
                 "inferred", "taken as the resume's XUIO", "bx_hydro"),
        "XUV-mn": ("unstratified breccia, subtype unknown", "breksi tak berlapis, subtipe tidak diketahui",
                   "VERIFY", "RJDH008-010, AA-altered, hematite-dominant; 'mn' likely monomict (7/10 'mon')",
                   "bx_other"),
        "BFZ": ("fault zone", "zona sesar", "conventional", "", "fault"),
        "VSS": ("volcaniclastic sediment", "sedimen vulkaniklastik", "VERIFY",
                "3 thin fine-grained intervals in RJDH017", "sediment"),
        "SST": ("sandstone", "batupasir", "conventional", "", "sediment"),
        "SCR": ("surface cover", "penutup permukaan", "inferred",
                "always the first interval from 0 m; matches UA", "cover"),
        "SCL": ("surface cover", "penutup permukaan", "inferred", "first interval from 0 m; matches UA", "cover"),
        "CAV": ("cavity / void", "rongga", "inferred", "only assay row is NS-SEL", "void"),
        "QTZ": ("quartz / silica", "kuarsa / silika", "VERIFY", "rock only, 1 SI-altered channel sample", "quartz"),
        # clast-only codes
        "SCT": ("unknown clast code", "kode klas tidak diketahui", "VERIFY", "clast field only", None),
        "SSL": ("unknown clast code (sandstone-siltstone?)", "kode klas tidak diketahui", "VERIFY", "clast field only", None),
        "VTL": ("unknown clast code", "kode klas tidak diketahui", "VERIFY", "clast field only", None),
    },
    "alt_facies": {
        "SI": ("silica (massive to vuggy quartz)", "silika", "resume", "", None),
        "AA": ("advanced argillic (quartz-alunite / dickite-kaolinite)", "argilik lanjut", "resume",
               "database does not split strong/weak AA", None),
        "AR": ("argillic (kaolinite-illite)", "argilik", "resume", "", None),
        "PP": ("propylitic (chlorite-calcite)", "propilitik", "resume", "", None),
        "UA": ("no alteration logged (cover or void)", "alterasi tidak dicatat (penutup/rongga)", "inferred",
               "coincides with SCR/SCL and CAV intervals", None),
    },
    "mineral": {
        "hm": ("hematite", "hematit", "conventional", "", None),
        "py": ("pyrite", "pirit", "conventional", "", None),
        "lm": ("limonite", "limonit", "conventional", "", None),
        "go": ("goethite", "goetit", "conventional", "", None),
        "ja": ("jarosite", "jarosit", "conventional", "", None),
        "en": ("enargite", "enargit", "resume", "Cu 298 ppm, CN/Cu 0.76 in overlapping assays", None),
        "cv": ("covellite", "kovelit", "resume", "Cu 573 ppm, CN/Cu 0.43", None),
        "co": ("Cu sulphide (chalcocite or covellite)", "sulfida Cu (kalkosit atau kovelit)", "VERIFY",
               "Cu 3,135 ppm, CN/Cu 0.79, unoxidised", None),
        "cp": ("chalcopyrite", "kalkopirit", "VERIFY", "1 row, Cu only 5 ppm", None),
        "su": ("native sulphur", "belerang native", "conventional", "", None),
        "al": ("alunite", "alunit", "conventional", "", None),
        "qt": ("quartz", "kuarsa", "conventional", "", None),
        "cy": ("clay", "lempung", "inferred", "with hm/lm, fully oxidised; = AltMin cy", None),
        "ca": ("calcite", "kalsit", "inferred", "Cu 16 ppm: not a Cu mineral", None),
        "ma": ("unknown (1 row)", "tidak diketahui", "VERIFY", "Cu 33 ppm: not malachite", None),
        "cl": ("unknown (1 row)", "tidak diketahui", "VERIFY", "", None),
        "um": ("no mineral logged", "mineral tidak dicatat", "inferred", "no other mineral on these rows", None),
        "unk": ("unknown", "tidak diketahui", "conventional", "", None),
    },
    "alt_min": {
        "si": ("silica", "silika", "conventional", "", None),
        "ka": ("kaolinite", "kaolinit", "conventional", "", None),
        "al": ("alunite", "alunit", "conventional", "", None),
        "cy": ("clay", "lempung", "conventional", "", None),
        "ch": ("chlorite", "klorit", "conventional", "11/12 in PP facies", None),
        "il": ("illite", "ilit", "conventional", "", None),
        "di": ("dickite", "dikit", "conventional", "", None),
        "sm": ("smectite", "smektit", "conventional", "", None),
        "is": ("illite-smectite", "ilit-smektit", "conventional", "", None),
        "ca": ("calcite", "kalsit", "conventional", "", None),
        "ba": ("barite", "barit", "VERIFY", "1 row", None),
        "hm": ("hematite", "hematit", "conventional", "", None),
        "py": ("pyrite", "pirit", "conventional", "", None),
        "su": ("native sulphur", "belerang native", "conventional", "", None),
    },
    "min_mode": {
        "ds": ("disseminated", "tersebar", "conventional", "", None),
        "fr": ("fracture", "rekahan", "conventional", "", None),
        "vl": ("veinlet", "urat halus", "conventional", "", None),
        "vn": ("vein", "urat", "conventional", "", None),
        "vs": ("unknown (vugs?)", "tidak diketahui", "VERIFY", "", None),
        "sng": ("unknown (single grain?)", "tidak diketahui", "VERIFY", "", None),
        "unk": ("unknown", "tidak diketahui", "conventional", "", None),
    },
    "texture": {   # AltQual and Dom/SecMinDescr (upper case)
        "PRV": ("pervasive", "pervasif", "conventional", "", None),
        "VFL": ("vug fill", "pengisi rongga", "conventional", "", None),
        "CTD": ("coating", "selaput", "conventional", "", None),
        "FRL": ("fracture lining", "pelapis rekahan", "conventional", "", None),
        "STK": ("stockwork", "stockwork", "conventional", "", None),
        "SPT": ("spotty", "bintik", "conventional", "", None),
        "DRU": ("drusy", "drusi", "conventional", "", None),
        "RPL": ("replacement", "penggantian", "conventional", "", None),
        "PTC": ("patchy", "bercak", "conventional", "", None),
        "VSI": ("vuggy silica", "silika berongga", "conventional", "", None),
        "MSI": ("massive silica", "silika masif", "conventional", "", None),
        "RSI": ("unknown silica texture", "tidak diketahui", "VERIFY", "", None),
        "MSP": ("unknown", "tidak diketahui", "VERIFY", "", None),
        "CSP": ("unknown", "tidak diketahui", "VERIFY", "", None),
        "PSP": ("unknown", "tidak diketahui", "VERIFY", "", None),
        "VRL": ("unknown", "tidak diketahui", "VERIFY", "", None),
    },
    "lith_qual": {
        "por": ("porphyritic", "porfiritik", "conventional", "", None),
        "pol": ("polymict", "polimik", "conventional", "", None),
        "mon": ("monomict", "monomik", "conventional", "", None),
        "vug": ("vuggy", "berongga", "conventional", "", None),
        "bxd": ("brecciated", "terbreksiasi", "conventional", "", None),
        "fgr": ("fine-grained", "berbutir halus", "conventional", "", None),
        "crk": ("crackle", "retak", "conventional", "", None),
        "gou": ("gouge", "gouge", "conventional", "", None),
        "mas": ("massive", "masif", "conventional", "", None),
        "ves": ("vesicular", "vesikuler", "conventional", "", None),
        "tuf": ("tuffaceous", "tufaan", "conventional", "", None),
        **{c: ("unknown", "tidak diketahui", "VERIFY", "", None)
           for c in ("tob", "pso", "msp", "csp", "flu", "wso", "snm")},
    },
}

OX_RANK = {"Oxide": 0, "Transition": 1, "Sulphide": 2}
MINERAL_FLAGS = {
    "min_py": {"py"},
    "min_cu": {"en", "cv", "co", "cp"},
    "min_fe_ox": {"hm", "go", "lm"},
    "min_ja": {"ja"},
    "min_su": {"su"},
    "min_al": {"al"},
}


def harmonise_case(s: pd.Series, case: str) -> pd.Series:
    return s.str.lower() if case == "lower" else s.str.upper()


def lookup(vocab: str, code: str) -> dict:
    """Entry for one code; KeyError if the code is not in the vocabulary."""
    en, id_, source, evidence, group = VOCAB[vocab][code]
    return {"meaning_en": en, "meaning_id": id_, "source": source, "evidence": evidence, "group": group}


def check_codes(s: pd.Series, vocab: str) -> None:
    unknown = sorted(set(s.dropna()) - set(VOCAB[vocab]))
    if unknown:
        raise KeyError(f"unmapped {vocab} codes: {unknown}")


def lith_group(df: pd.DataFrame, col: str) -> pd.DataFrame:
    check_codes(df[col], "lith")
    df = df.copy()
    key = df[col].map(lambda c: VOCAB["lith"][c][4], na_action="ignore")
    df["Lith_group"] = key.map(lambda k: LITH_GROUP_NAMES[k][0], na_action="ignore")
    df["Lith_group_id"] = key.map(lambda k: LITH_GROUP_NAMES[k][1], na_action="ignore")
    return df


def alt_facies(df: pd.DataFrame, col: str) -> pd.DataFrame:
    check_codes(df[col], "alt_facies")
    df = df.copy()
    short = {"SI": "Silica", "AA": "Advanced argillic", "AR": "Argillic", "PP": "Propylitic",
             "UA": "No alteration logged"}
    df["Alt_facies_name"] = df[col].map(short)
    df["Alt_facies_id"] = df[col].map(lambda c: VOCAB["alt_facies"][c][1].capitalize(), na_action="ignore")
    df["alt_ml_label"] = df[col].where(df[col].ne("UA"))
    return df


def ox_state(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ox_state"] = df["Comments"]
    df["ox_rank"] = df["ox_state"].map(OX_RANK).astype("Int64")
    pct = df["WRAltOxidPcnt"]
    df["flag_ox_conflict"] = (df.ox_state.eq("Sulphide") & pct.ge(90)) | (df.ox_state.eq("Oxide") & pct.eq(0))
    df["WRAltSulphIntensity_h"] = df["WRAltSulphIntensity"].where(df["WRAltSulphIntensity"] != -999)
    return df


def apply_ox_cutoffs(pct: np.ndarray, a: float, b: float) -> np.ndarray:
    return np.where(pct <= a, "Sulphide", np.where(pct <= b, "Transition", "Oxide"))


def fit_ox_cutoffs(pct: np.ndarray, label: np.ndarray) -> tuple[float, float]:
    """Cut-offs a < b on the logged % values that maximise balanced accuracy
    (Sulphide <= a < Transition <= b < Oxide). First maximum wins on ties."""
    grid = np.unique(pct)
    best, cut = -1.0, None
    for i, a in enumerate(grid):
        for b in grid[i + 1:]:
            score = balanced_accuracy_score(label, apply_ox_cutoffs(pct, a, b))
            if score > best:
                best, cut = score, (a.item(), b.item())
    return cut


def mineral_flags(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for flag, minerals in MINERAL_FLAGS.items():
        df[flag] = df[cols].isin(minerals).any(axis=1)
    return df
