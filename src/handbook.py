"""Local evidence inventory and localized facts for the team handbook."""
import csv
import re
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATA = ROOT / "data/processed"
FIG = ROOT / "outputs/figures/iogas"
PROJECT = ROOT / "outputs/iogas_project"
KIRIM = ROOT / "outputs/kirim"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def records(name):
    return [s.split("|") for s in (REPORTS / name).read_text(encoding="utf-8").splitlines()
            if s and not s.startswith("#")]


def select(items, **criteria):
    return [r for r in items if all(r[k] == v for k, v in criteria.items())]


def one(items, **criteria):
    result, = select(items, **criteria)
    return result


def amount(value, digits=0):
    """Return ID and EN renderings of one underlying number."""
    en = f"{float(value):,.{digits}f}"
    return en.translate(str.maketrans(",.", ".,")), en


def facts_tables():
    soil = rows(DATA / "iogas/RJ_tanah.csv")
    rock = rows(DATA / "iogas/RJ_batuan.csv")
    s = one(soil, SampleID="1009765")
    zones = rows(DATA / "ml3_summary.csv")
    th = one(rows(DATA / "s1_ambang_perbandingan_v1.csv"), dataset="tanah", element="As")
    z = one(rows(DATA / "s2_zona_vs_kelas_v1.csv"), dataset="tanah", element="Au", zona="Tinggi", kelas_ambang="Latar")
    cont = select(rows(DATA / "ml4_comparisons.csv"), label="HMM", scope="pad kembar")
    near, far = one(cont, d_from="0.0"), one(cont, d_from="50.0")
    nag = rows(DATA / "s4_kelas_nag_ringkasan_v1.csv")
    tested = [r for r in nag if r["kelas_nag"] in {"NAF", "PAF-HC", "PAF-LC"} and r["zona_oksidasi"] != "Semua"]
    samp = one(rows(DATA / "iogas/RJ_DH_assay.csv"), SampleID="1075876")
    assert samp["ML_paf_set"] == "PAF-LC|PAF-HC" and samp["ML_paf_kelola"] == "PAF-HC"
    target = {r["item"]: r["nilai"] for r in rows(DATA / "ml6_summary.csv")}
    f = dict(soil_all=amount(len(soil)), rock_all=amount(len(rock)),
             soil_rj=amount(len(select(soil,prospek_RJ="Y"))), rock_rj=amount(len(select(rock,prospek_RJ="Y"))),
             rock_model=amount(sum(int(r["n"]) for r in select(zones,dataset="batuan"))),
             elev_raw=amount(s["Elev_orig"]), elev_z=amount(s["Z"],2), thr_n=amount(th["n"]),
             as1=amount(th["pp_ambang_1"]), as2=amount(th["pp_ambang_2"]), as_gmm=amount(th["gmm_utama"],2),
             as_visual_pct=amount(th["pct_di_atas_pp1"],1), as_model_pct=amount(th["pct_di_atas_gmm_utama"],1),
             bg_n=amount(z["n"]), high_n=amount(z["n_zona"]), near=amount(float(near["agree"])*100,1),
             far=amount(float(far["agree"])*100,1), chance=amount(float(near["chance"])*100,1),
             acid_n=amount(sum(int(r["n"]) for r in tested if r["kelas_nag"]!="NAF")),
             nag_n=amount(sum(int(r["n"]) for r in tested)), sulf_n=amount(sum(int(r["n"]) for r in select(tested,zona_oksidasi="Sulfida"))),
             reaches=amount(target["drainage_reaches"]), doubt=amount(target["drainage_ragu"]),
             sample=(samp["SampleID"],)*2, hole=(samp["HoleID"],)*2, from_m=amount(samp["From"]), to_m=amount(samp["To"],1))
    for key, ox, label in [("sulf_hc","Sulfida","PAF-HC"),("ox_lc","Oksida","PAF-LC"),("ox_hc","Oksida","PAF-HC")]:
        f[key]=amount(one(tested,zona_oksidasi=ox,kelas_nag=label)["n"])
    tables = {}
    scores = select(rows(DATA / "ml2_scores.csv"), dataset="bor",model="rf",cv="pad",subset="semua")
    score_rows=[]
    for target, tier, label in [("alt","A",("Alterasi","Alteration")),("oks","B",("Oksidasi","Oxidation")),("py","B",("Pirit","Pyrite")),("lit","B",("Litologi","Lithology"))]:
        r=one(scores,target=target,tier=tier)
        score_rows.append([label,amount(r["n"]),amount(r["bal_acc"],2),amount(r["ci05"],2),amount(r["ci95"],2)])
    tables["scores"] = ([("Target","Target"),("Interval","Intervals"),("Akurasi seimbang","Balanced accuracy"),("P5","P5"),("P95","P95")],score_rows)
    zone_names={"Tinggi":"High","Rendah":"Low","Sedang":"Medium"}
    tables["zones"]=([("Media","Medium"),("Zona","Zone"),("Sampel","Samples"),("Median Au (ppm)",)*2,("Median As (ppm)",)*2,("Median Cu (ppm)",)*2],
        [[(r["dataset"],"soil" if r["dataset"]=="tanah" else "rock"),(r["zone"],zone_names[r["zone"]]),amount(r["n"]),amount(r["Au_median"],3),amount(r["As_median"]),amount(r["Cu_median"],1)] for r in zones])
    state_names=["Low Au and Cu · sulfide","Low Au and Cu · oxide","Moderate Au, low Cu · oxide","Moderate Au, high Cu · sulfide","High Au, low Cu · oxide"]
    tables["states"]=([("Satuan","State"),("Komposit","Composites"),("Median Au (ppm)",)*2,("Median Cu (ppm)",)*2,("Stabilitas","Stability")],
        [[(r["nama"],f"S{r['state']} {state_names[int(r['state'])-1]}"),amount(r["n"]),amount(r["Au_median"],3),amount(r["Cu_median"]),amount(r["stability_median"],2)] for r in rows(DATA/"ml4_states.csv")])
    tables["nag"]=([("Zona log","Logged zone"),("Kelas uji","Test class"),("Sampel","Samples"),("Median pH",)*2,("Median kg H₂SO₄/t",)*2],
        [[(r["zona_oksidasi"],"oxide" if r["zona_oksidasi"]=="Oksida" else "sulfide"),(r["kelas_nag"],)*2,amount(r["n"]),amount(r["median_NAG_pH"],2),amount(r["median_NAG_pH45_kgH2SO4_t"],2)] for r in tested])
    tables["holes"]=([("Usulan","Proposal"),("Tujuan","Purpose"),("Azimut / dip","Azimuth / dip"),("Panjang (m)","Length (m)"),("Ke alur (m)","To drainage (m)")],
        [[(r["usulan"],)*2,("Perluasan","Extension") if r["usulan"] in {"RJ-U01","RJ-U02"} else ("Penutup celah","Gap test") if r["tingkat"]=="A" else ("Uji tanah","Test soil anomaly"),(f"{r['az']}° / {r['dip']}°",)*2,amount(r["EndDepth"]),amount(r["jarak_alur"])] for r in rows(DATA/"ml6_usulan_lubang.csv")])
    return f,tables


def stage_subject(name):
    """English key to the original ioGAS plot/project name."""
    words={"pp":"probability plot","kelas":"class","tanah":"soil","batuan":"rock","bor":"drillholes","box":"box plot",
           "lubang":"by hole","tahun":"by year","oksidasi":"oxidation","alterasi":"alteration","keyakinan":"confidence",
           "zona":"zone","status":"state","hmm":"HMM","peta":"sample map","peta3d":"3D plan view","strip":"downhole strip",
           "penampang":"section","kembar":"paired holes","Lain":"off section","xy":"scatter","duplikat":"resamples",
           "tukey":"Tukey outliers","uji":"testing","nag":"NAG","kelola":"handling","amd":"acid drainage elements",
           "phNAG":"NAG pH","kapNAG":"NAG acid capacity","Stotal":"total sulfur","komposit":"composites","lingkungan":"environment",
           "akhir":"final","warna":"colours","qaqc":"QAQC","rjdh012":"RJDH012","halley":"Halley diagram"}
    return " · ".join(words.get(t,t) for t in Path(name).stem.split("_") if not re.fullmatch(r"s[1-5]|v1|RJ",t))


def inventory():
    assets={}
    def add(p,ch,description):
        p=p.resolve()
        if not p.is_file(): raise FileNotFoundError(p)
        if p in assets: raise ValueError(f"duplicate inventory entry: {p}")
        assets[p]=(str(ch),*description)
    images=rows(FIG/"indeks_gambar_iogas.csv")
    projects=rows(PROJECT/"indeks_proyek_iogas.csv")
    assert len(images)==129 and len(projects)==51
    translations = records("handbook_iogas_terms.txt")
    for r in images:
        p=FIG/r["file"]
        desc = r["isi"] + (" · " + r["warna"] if r["warna"] != "-" else "")
        en = desc
        for idn, english in translations:
            en = en.replace(idn, english)
        add(p,int(p.name[1])+2,(desc, en))
    for r in projects:
        ch=", ".join(re.findall(r"\d+",r["bab_laporan"].split("(")[0]))
        add(PROJECT/r["file"],ch,(f"Proyek {r['jenis']} · {r['data']} · {r['jendela_plot']} jendela",
             f"{'Final' if r['jenis']=='akhir' else 'Supporting'} project · {stage_subject(r['file'])} · {r['baris']} rows, {r['jendela_plot']} plot windows"))
    assert set(FIG.glob("*.png"))=={FIG/r["file"] for r in images}
    assert set(PROJECT.rglob("*.gas"))=={PROJECT/r["file"] for r in projects}
    rules=records("handbook_assets.txt")
    files=list(DATA.rglob("*.csv"))+list((DATA/"iogas").glob("*.gas"))+list((ROOT/"outputs/figures").glob("*.png"))
    for ext in ("*.qgz","*.png"):
        files.extend((ROOT/"outputs/maps").rglob(ext))
    for ext in ("*.tif","*.gpkg"):
        files.extend((ROOT/"gis").glob(ext))
    files.extend([FIG/"indeks_gambar_iogas.csv",PROJECT/"indeks_proyek_iogas.csv",KIRIM/"MANIFEST.csv",ROOT/"PANDUAN_TIM.md",*ROOT.glob("*.pdf"),*list((ROOT/"data/raw").glob("*.pdf"))])
    for p in files:
        rule=next((r for r in rules if any(fnmatch(p.name,pat) for pat in r[1].split(";"))),None)
        if not rule: raise ValueError(f"unclassified asset: {p}")
        ch,_,*desc=rule
        if p.name.startswith("12_") and "shap" in p.name: ch="6"
        if p.parent.name=="qc": desc=["Pemeriksaan QGIS · "+desc[0],"QGIS review view · "+desc[1]]
        add(p,ch,desc)
    for r in rows(KIRIM/"MANIFEST.csv"):
        src=ROOT/r["sumber"]
        if src in assets:
            ch,idn,en=assets[src]
            add(KIRIM/r["file"],ch,("Salinan kiriman · "+idn,"Submission copy · "+en))
        else:
            if not r["file"].endswith(".zip"): raise ValueError(r)
            add(KIRIM/r["file"],"3, 4, 5, 6",("Arsip proyek ioGAS untuk kiriman.","Submission archive of ioGAS projects."))
    return assets
