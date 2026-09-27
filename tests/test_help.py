"""In-app help (decision 13.13, PLAN.md section 11): the guides split into
sections, every anchor a registry entry names exists (a renamed upstream
section fails here, and tools/update_vendor.sh runs this file), and every
entry's help is put together."""
import pytest

from guiqula import vendoring
from guiqula.docs import entries
from guiqula.docs.guide import Guide, GuideError, math_images, rewrite
from guiqula.registry import base as registry

TEXT = """# Top
intro
```python
# a comment, not a heading
h.add_zeeman([0, 0, 1])
```
## Alpha
text $x^2$ and `$not math$`
$$
E = \\tfrac12 m v^2
$$
### Details
more
## Beta
### Details
```
g.get_supercell(2)
```
"""


def test_sections_anchors_and_calls():
    guide = Guide(TEXT, "test")
    assert guide.anchors() == ["Top", "Alpha", "Alpha > Details", "Beta", "Beta > Details"]
    assert guide.text("Alpha").startswith("## Alpha") and "more" in guide.text("Alpha")
    assert "Beta" not in guide.text("Alpha")
    assert guide.find("Beta > Details").parent == "Beta"
    assert guide.calls("add_zeeman") == ["Top"]
    assert guide.calls("get_supercell") == ["Beta > Details"]
    with pytest.raises(GuideError, match="no section"):
        guide.find("Details")
    ambiguous = Guide("## A\n### X\n### X\n", "t")
    with pytest.raises(GuideError, match="2 sections"):
        ambiguous.find("A > X")


def test_equations_become_images_outside_code():
    text, equations = math_images(Guide(TEXT).text("Alpha"))
    assert equations == ["x^2", "E = \\frac{1}{2} m v^2"]
    assert "![equation](formula:0)" in text and "`$not math$`" in text
    assert rewrite("\\mathbf k \\cdot \\vec r \\mod 1") == \
        "\\mathbf{k} \\cdot \\vec{r} \\ \\mathrm{mod}\\  1"


def test_every_anchor_of_the_registry_exists():
    """The anchor test of 13.13: each section a registry entry names is in
    the vendored guide (or guiqula's), once."""
    assert vendoring.find_guide() is not None
    assert entries.anchor_problems() == []


def test_reference_sections_are_found():
    guide = entries.pyqula_guide()
    assert entries.reference_anchor(guide, "h.add_zeeman") == "h.add_zeeman()"
    assert entries.reference_anchor(guide, "h.add_modified_haldane") == \
        "h.add_modified_haldane() / h.add_antihaldane()"
    assert entries.reference_anchor(guide, "classicalspin.SpinModel.add_heisenberg") == \
        "sm.add_heisenberg()"
    assert entries.reference_anchor(guide, "latticegas.LatticeGas.anneal") == "lg.anneal()"
    assert entries.reference_anchor(guide, "geometry.honeycomb_lattice") is None


@pytest.mark.parametrize("spec", registry.entries(), ids=lambda s: f"{s.family}:{s.kind}")
def test_every_entry_has_help(spec):
    text = entries.entry_help(spec)
    assert text.startswith(f"# {spec.label}")
    for anchor in entries.entry_anchors(spec, entries.pyqula_guide()):
        assert entries.pyqula_guide().text(anchor).splitlines()[0] in text
    for target in entries.pyqula_targets(spec):
        assert f"## pyqula: {target}" in text
    if spec.params and not spec.runs_code and not spec.document_level:   # a sweep: a loop
        assert "## pyqula code" in text


def test_the_guides_contents_and_an_override(tmp_path, monkeypatch):
    contents = entries.contents("pyqula")
    assert "(help:pyqula/Density%20of%20states)" in contents
    assert "(help:guiqula/Fields%3A%20parameters%20that%20depend%20on%20the%20position)" in \
        entries.contents("guiqula")
    package = tmp_path / "src" / "pyqula"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.setenv(vendoring.ENV_VAR, str(tmp_path / "src"))
    assert vendoring.find_guide()[0] in ("vendored", "checkout")   # the override has none
    (tmp_path / "documentation").mkdir()
    (tmp_path / "documentation" / "user_guide.md").write_text("# Mine\n")
    assert vendoring.find_guide() == ("override", tmp_path / "documentation" / "user_guide.md")


def test_a_chapter_is_its_introduction_and_links():
    """A top-level section of pyqula's guide can be hundreds of lines: a
    lattice's help shows the introduction of "Setting up a Hamiltonian" and
    links to its sections, not the whole chapter."""
    from guiqula.docs.guide import Guide
    text = entries.entry_help(registry.get("lattice", "honeycomb_lattice"))
    assert "# Setting up a Hamiltonian" in text
    assert "(help:pyqula/Including%20an%20onsite%20energy)" in text
    assert "## Including an onsite energy" not in text
    guide = Guide(TEXT)
    assert [c.anchor for c in guide.children("Top")] == ["Alpha", "Beta"]
    assert guide.own_text("Top").startswith("# Top\nintro") and "Alpha" not in \
        guide.own_text("Top")
    assert "more" in entries.section_text("pyqula", guide, "Alpha")       # level 2: in full
    assert entries.section_text("pyqula", guide, "Top").endswith(
        "Its sections: [Alpha](help:pyqula/Alpha), [Beta](help:pyqula/Beta).\n")
