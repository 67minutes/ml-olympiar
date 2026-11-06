"""Build the offline bilingual chapter handbook. Run: uv run python scripts/29_laporan_final.py"""
import os
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from src import handbook as hb
from src import report

OUT = hb.ROOT / "outputs/laporan_final/laporan_final_v1.html"


def pair(idn, en):
    return f'<span class="id" lang="id">{escape(idn)}</span><span class="en" lang="en">{escape(en)}</span>'


def link(path, label=None):
    url=quote(os.path.relpath(path, OUT.parent).replace(os.sep,"/"), safe="/")
    return f'<a href="{url}">{label or escape(path.name)}</a>'


def render_table(spec):
    headers, rows=spec
    head="".join(f"<th>{pair(*x)}</th>" for x in headers)
    body="".join("<tr>"+"".join(f"<td>{pair(*x)}</td>" for x in row)+"</tr>" for row in rows)
    return f'<div class="tablebox"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def glossary():
    terms={key:(a,b) for key,a,b in hb.records("handbook_terms.txt")}
    for r in hb.rows(hb.DATA/"code_dictionary.csv"):
        key=r["code"]
        if r["meaning_id"] and r["meaning_en"]:
            qualifier = {"inferred": (" (interpretasi)", " (inferred)"), "VERIFY": (" [VERIFY]", " [VERIFY]")}.get(r["source"], ("",""))
            terms.setdefault(key,(r["meaning_id"] + qualifier[0], r["meaning_en"] + qualifier[1]))
    fields = {key:(a,b) for key,a,b in hb.records("handbook_ml_fields.txt")}
    for r in hb.rows(hb.DATA/"iogas/kolom_iogas.csv"):
        key = r["column"]
        description = (r["meaning_id"], r["meaning_en"])
        if key.startswith("ML_") and r["meaning_en"].startswith("ML output"):
            suffix = key.split("_",2)[-1]
            if key.startswith("ML_thr_"):
                element, stat = suffix.rsplit("_populasi",1)[0], "population"
                if suffix.endswith("_p_atas"):
                    element, stat = suffix[:-7], "probability"
                description = ((f"Populasi campuran untuk {element}.", f"Mixture population for {element}.")
                               if stat == "population" else
                               (f"Peluang populasi atas untuk {element}.", f"Upper-population probability for {element}."))
            elif suffix == "p_maks" or key in fields or suffix in fields:
                description = fields[key] if key in fields else fields[suffix]
            elif suffix.startswith("pval_"):
                label = suffix[5:]
                description = (f"Nilai p konformal untuk {label}.",f"Conformal p-value for {label}.")
            elif suffix.startswith("p_"):
                label = suffix[2:].replace("_"," ")
                description = (f"Peluang model untuk kelas {label}.", f"Model probability for class {label}.")
        if all(description):
            terms.setdefault(key,description)
    entries="".join(f'<div class="term" data-list="terms"><strong>{escape(k)}</strong>{pair(*v)}</div>' for k,v in terms.items())
    return '<details id="glossary"><summary>'+pair("Glosarium dan kamus kolom","Glossary and column dictionary")+'</summary>'+search("terms")+entries+"</details>"


def search(kind):
    return f'<label>{pair("Cari istilah atau nama berkas","Search by term or filename")}<input class="search" type="search" id="{kind}-query"></label><small aria-live="polite" id="{kind}-count"></small>'


def build():
    assets=hb.inventory()
    names={}
    for p in assets: names.setdefault(p.name,[]).append(p)
    def original(name):
        paths=names[name]
        # Chapter sources always use the original instead of a submission copy.
        unique=[p for p in paths if hb.KIRIM not in p.parents]
        if len(unique)==1: return unique[0]
        if len(paths)==1: return paths[0]
        raise ValueError(f"ambiguous source: {name}")
    facts,tables=hb.facts_tables()
    def prose(a,b):
        return pair(*(report.fill_facts(s,{k:v[i] for k,v in facts.items()}) for i,s in enumerate([a,b])))
    content=hb.records("handbook_chapters.txt")+hb.records("handbook_synthesis.txt")
    chapters=[r for r in content if r[0]=="chapter"]
    assert [int(r[1]) for r in chapters]==list(range(1,10))
    supplements = hb.records("handbook_supplements.txt")
    def figure(name, idn, en):
        p = original(name)
        tool = "ioGAS" if p.parent == hb.FIG else ("QGIS" if "maps" in p.parts else "Python")
        img = f'<img src="{p.relative_to(hb.ROOT).as_posix()}" alt="{escape(name)}" loading="lazy">'
        return (f'<figure data-place>{link(p, img)}<figcaption><span class="meta">{tool}</span>'
                f'{prose(idn,en)}<span class="source">{link(p)}</span></figcaption></figure>')
    toc=[("start","Panduan nama","Reading the names"),("overview","Ringkasan temuan","Findings at a glance")]+[
        (f"ch{n}",f"{n}. {a}",f"{n}. {b}") for _,n,a,b in chapters]+[("index","Indeks bukti","Evidence index")]
    nav=''.join(f'<a href="#{k}">{pair(a,b)}</a>' for k,a,b in toc)
    parts=['<section id="start" data-place><div class="eyebrow">Martabe · Sumatra Utara / North Sumatra</div><h1>Ramba Joring</h1><p class="lead">'+pair("Buku temuan untuk penulis laporan eksplorasi dan lingkungan","A findings handbook for the exploration and environmental report writers")+'</p><h3>'+pair("Cara membaca nama sebelum mulai","How to read the names before you begin")+'</h3>']
    for a,b in [
        ("Tanah, batuan dan bor mewakili tiga media berbeda. Kadar Au_ppm ialah massa emas per sejuta satuan massa (setara g/t). X dan Y ialah koordinat timur dan utara dalam meter. Pada bor, From dan To ialah kedalaman sepanjang lintasan.","Soil (tanah), rock grabs (batuan) and drilling (bor) are separate sample media. Au_ppm is gold in parts per million by mass, equivalent to g/t. X and Y are easting and northing in metres. In a hole, From and To measure depth along its trace."),
        ("s1_pp_tanah_As_v1.png dibaca dari kiri: tahap ioGAS 1, plot probabilitas, tanah, arsen, versi 1. ML-1 adalah tugas pemodelan ambang yang terpisah. S1 dalam penampang bor ialah satu dari lima satuan kimia. AA dan SI pada pita sebelahnya adalah kode alterasi yang dicatat ahli geologi.","Read s1_pp_tanah_As_v1.png from the left: ioGAS stage 1, probability plot, soil, arsenic, version 1. ML-1 is the separate threshold modelling task. S1 on a drill section is one of five chemical states. AA and SI on the adjacent strip are alteration codes recorded by geologists."),
        ("ML_paf_kelola dibaca sebagai keluaran model (ML), potensi pembentukan asam (paf), dan keputusan penanganan (kelola). Bedakan kelas dari uji, himpunan kelas yang diprediksi, dan keputusan pengelolaan. Pada material yang belum diuji, keputusan mengikuti kelas terburuk yang masih mungkin.","Read ML_paf_kelola as model output (ML), potential acid formation (paf), and handling decision (kelola). Distinguish the class derived from a lab test, the set of predicted classes, and the handling decision. Untested material is managed using the most severe plausible class."),
        ("Gambar utama tertanam dalam HTML. Klik nama berkas untuk membuka gambar resolusi asli, tabel atau proyek dari salinan repositori. Pada plot, nama unsur dan satuan tetap mengikuti ioGAS.","Key figures are embedded in the HTML. Click a filename to open the full-resolution figure, table or project from a local repo checkout. Element and unit labels on original plots follow ioGAS.")]:
        parts.append("<p>"+pair(a,b)+"</p>")
    parts.extend([glossary(),'</section><section id="overview" data-place><h2>'+pair("Ringkasan temuan","Findings at a glance")+'</h2><ul class="summary-list">'])
    for n,a,b in [
        (3,"Arsen tanah menunjukkan bahwa pilihan ambang dapat mengubah fraksi sampel yang ditindaklanjuti. Periksa kurva sebelum mengutip satu angka.","Soil arsenic shows how threshold choice changes the follow-up population. Read the curve before quoting a cutoff."),
        (4,"Jejak tanah paling luas di barat-tengah layak diperiksa di lapangan. Kekuatan bukti zonasi berbeda antara tanah dan batuan.","The largest west-central soil footprint merits field follow-up. Soil and rock support different levels of confidence in zoning."),
        (5,"Satuan kaya Cu dan satuan kaya Au dapat dibedakan pada bor. Kesesuaian melemah ketika jarak antarlubang membesar.","Drilling distinguishes copper-rich and gold-rich states. Agreement declines as holes diverge."),
        (6,"Dari {{sulf_n}} sampel sulfida yang bersifat asam, {{sulf_hc}} berkapasitas tinggi. Keputusan penanganan di luar lubang uji perlu konfirmasi.","Of {{sulf_n}} acidic sulfide samples, {{sulf_hc}} have high capacity. Handling decisions outside the test hole need confirmation."),
        (7,"Dua usulan perluasan, satu uji celah dan dua uji tanah menjawab pertanyaan berbeda. Periksa tapak dan aliran sebelum pemboran.","Two extensions, one gap test and two soil tests address different questions. Verify pads and drainage before drilling.")]:
        parts.append(f'<li><a href="#ch{n}">{prose(a,b)}</a></li>')
    parts.append("</ul></section>")
    for kind,*args in content:
        if kind=="chapter":
            n,a,b=args
            parts.append(f'<section id="ch{n}" data-place><div class="eyebrow">{pair("Bab "+n,"Chapter "+n)}</div><h2>{pair(a,b)}</h2>')
        elif kind in {"p","lead"}:
            parts.append(f'<p data-place class="{kind}">{prose(*args)}</p>')
        elif kind=="table":
            parts.append(render_table(tables[args[0]]))
        elif kind=="method":
            figures = "".join(figure(*item[1:]) for item in supplements if item[0] == n)
            parts.append("<details><summary>"+pair("Metode, batas dan bukti tambahan","Methods, limits and supporting figures")+"</summary><p>"+prose(*args)+"</p>"+figures+"</details>")
        elif kind=="say":
            parts.append('<blockquote data-place><div class="tag">'+pair("Bahan penulisan","Suggested report wording")+"</div><p>"+prose(*args)+"</p></blockquote>")
        elif kind=="fig":
            parts.append(figure(*args))
        elif kind=="links":
            refs="".join("<li>"+link(original(name))+"</li>" for name in args[0].split(";"))
            parts.append('<h3>'+pair("Sumber untuk bab ini","Sources for this chapter")+'</h3><ul class="refs">'+refs+f'</ul><a class="chapterjump" href="#index" data-chapter="{n}">'+pair("Lihat semua bukti bab ini →","Browse all evidence for this chapter →")+"</a></section>")
        else: raise ValueError(kind)
    parts.append('<section id="index" data-place><h2>'+pair("Indeks bukti","Evidence index")+'</h2><p>'+pair("Cari dengan nama unsur, nomor lubang, topik atau nama berkas. Setiap tautan membuka berkas asli di repositori.","Search by element, hole ID, topic or filename. Each link opens the original local repository file.")+'</p><div class="filters">'+search("index")+'<label>'+pair("Bab","Chapter")+'<select id="chapter-filter">')
    for value,idn,en in [("","Semua bab","All chapters")]+[(n,f"{n}. {a}",f"{n}. {b}") for _,n,a,b in chapters]:
        parts.append(f'<option value="{value}" data-id-label="{escape(idn)}" data-en-label="{escape(en)}">{escape(idn)}</option>')
    parts.append("</select></label></div>")
    for p,(ch,idn,en) in sorted(assets.items(),key=lambda i:(int(i[1][0].split(",")[0]),i[0].name)):
        rel=p.relative_to(hb.ROOT).as_posix()
        parts.append(f'<div class="entry" data-list="index" data-chapters="{ch}">{link(p)} · {pair("Bab "+ch,"Chapter "+ch)}<br>{pair(idn,en)}<br><small>{escape(rel)}</small></div>')
    parts.append("</section>")
    page=(hb.REPORTS/"handbook_ui.html").read_text(encoding="utf-8").replace("@@NAV@@",nav).replace("@@BODY@@","".join(parts))
    assert not report.check_links(page) and "{{" not in page
    page,images=report.embed_images(page,hb.ROOT,1800)
    OUT.parent.mkdir(exist_ok=True,parents=True)
    OUT.write_text(page,encoding="utf-8")
    print(f"{len(chapters)} chapters, {len(assets)} indexed files, {len(images)} embedded figures; {OUT.stat().st_size:,} bytes")


if __name__=="__main__":
    build()
