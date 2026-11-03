import pytest
from PIL import Image

from src import report as rp


def test_fmt_id_uses_decimal_comma_and_dot_thousands():
    assert rp.fmt_id(0.7016) == "0,70"
    assert rp.fmt_id(2412) == "2.412"
    assert rp.fmt_id(1350.5, 1) == "1.350,5"
    assert rp.fmt_id(866.0, 0) == "866"


def test_fill_facts_replaces_and_rejects_unresolved_or_empty():
    assert rp.fill_facts("a {{x}} b {{ y }}", {"x": "1", "y": 2}) == "a 1 b 2"
    with pytest.raises(KeyError):
        rp.fill_facts("{{x}} {{z}}", {"x": "1"})
    with pytest.raises(ValueError):
        rp.fill_facts("{{x}}", {"x": " "})


def test_embed_images_inlines_downscaled_and_raises_on_missing(tmp_path):
    Image.new("RGB", (4000, 1000), "white").save(tmp_path / "f.png")
    html, used = rp.embed_images('<img src="f.png" alt="a">', tmp_path, max_px=800)
    assert used == ["f.png"] and 'src="data:image/png;base64,' in html and 'src="f.png"' not in html
    with pytest.raises(FileNotFoundError):
        rp.embed_images('<img src="nope.png">', tmp_path)


def test_check_links_reports_dangling_anchors():
    html = '<a href="#a">x</a><a href="#b">y</a><h2 id="a">A</h2>'
    assert rp.check_links(html) == ["b"]
