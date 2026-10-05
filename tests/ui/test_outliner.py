"""The outliner says what each row is and in what state, and nothing is cut
off (PLAN.md phase 8, package P7): the Status column sized to its longest
text and the Entry column taking the rest, the marks of ui/marks.py, the
system's summary and the mean field read across their rows, a label wider
than its column wrapped onto further lines, the full text in every row's
tooltip."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontMetrics, QFontMetricsF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from guiqula.io import project
from guiqula.ui import marks, theme
from guiqula.ui.app import build_main_window
from guiqula.ui.outliner import (ADD_ROLE, LINE, MARK_ROLE, _summary, leading_marks,
                                 marks_width, text_margin, text_width, wrapped,
                                 wraps)
from guiqula.ui.outliner import status_width as drawn_width


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()
    theme.set_ui_text("normal")
    theme.apply_text(QApplication.instance())


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)
    for _ in range(5):                    # the delayed layout of the rows that wrap
        QApplication.processEvents()
        qtbot.wait(20)


def load(qtbot, window, preset):
    window.session.act("load", path=preset)
    window.select("")
    settle(qtbot, window)


def cut(outliner):
    """The rows whose label or status is not wholly in sight, with why: a
    label line wider than its room or a label whose lines are not its text,
    a status elided in its column or under its "+", a "+" past the right
    edge, the status of a detail row outside its row."""
    view = outliner.viewport()
    margin = text_margin(outliner)
    out = []
    for item_id, item in outliner._items.items():
        index = outliner.indexFromItem(item, 0)
        option = QStyleOptionViewItem()
        outliner.initViewItemOption(option)
        option.rect = outliner.visualRect(index)
        delegate = outliner.itemDelegateForColumn(0)
        delegate.initStyleOption(option, index)
        room = delegate.label_room(option, index)
        lines = option.text.split(LINE)
        if not wraps(option.font, item.text(0), room):
            pass                      # squeezed narrower than a word: elided, by design
        elif "".join(lines).replace(" ", "") != item.text(0).replace(" ", "") or any(
                text_width(option.font, line) > room for line in lines) or \
                option.rect.height() < len(lines) * QFontMetrics(option.font).lineSpacing():
            out.append((item_id, item.text(0), "label"))
        text = item.text(1)
        if outliner.is_detail(item_id):
            index = outliner.indexFromItem(item, 0)
            option = QStyleOptionViewItem()
            outliner.initViewItemOption(option)
            option.rect = outliner.visualRect(index)
            delegate = outliner.itemDelegateForColumn(0)
            _, status, one_line = delegate.layout(option, index)
            font = outliner.font()
            state = item.data(1, MARK_ROLE)
            if one_line:              # as it is drawn: the marks as icons
                fits = drawn_width(font, text, state) <= status.width() + 1
            else:                     # the leading marks on the first line, the rest beside
                names, rest = leading_marks(text, state)
                width = status.width() - marks_width(font, names)
                lines = wrapped(font, rest, width)
                bound = QFontMetrics(font).boundingRect(
                    QRect(0, 0, width, status.height()),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), lines)
                fits = bound.height() <= status.height() and bound.width() <= width \
                    and lines.replace("\n", "").replace(" ", "") == rest.replace(" ", "") \
                    and all(QFontMetricsF(font).horizontalAdvance(line) <= width
                            for line in lines.splitlines())
            if not fits or not option.rect.contains(status) or status.right() >= view.width():
                out.append((item_id, text, "detail"))
            continue
        index = outliner.indexFromItem(item, 1)
        rect = outliner.visualRect(index)
        if rect.right() >= view.width():
            out.append((item_id, text, "column past the edge"))
        if text:
            option = QStyleOptionViewItem()
            outliner.initViewItemOption(option)
            option.rect = rect
            outliner.itemDelegateForColumn(1).initStyleOption(option, index)
            # as it is drawn: the marks as icons (P8), the rest as text
            width = drawn_width(option.font, text, item.data(1, MARK_ROLE))
            if option.text != text or width > rect.width() - 2 * margin:
                out.append((item_id, text, "elided"))
        if item.data(1, ADD_ROLE):
            button = outliner.add_button(item.data(1, ADD_ROLE))
            left = button.mapTo(view, QPoint(0, 0)).x()
            if not button.isVisible() or left + button.width() > view.width():
                out.append((item_id, text, "+ out of sight"))
            elif text and rect.x() + margin + drawn_width(
                    outliner.font(), text, item.data(1, MARK_ROLE)) > left:
                out.append((item_id, text, "under the +"))
    return out


@pytest.mark.parametrize("preset", project.presets())
def test_no_status_is_cut_at_the_default_width(window, qtbot, preset, shot):
    """Every preset at 1200x800, with normal and large interface text: the
    Status column covers its longest text, every "+" is in sight, the Entry
    column takes the rest."""
    load(qtbot, window, preset)
    outliner = window.outliner
    try:
        for size in ("normal", "large"):
            window.set_ui_text(size)
            settle(qtbot, window)
            assert cut(outliner) == [], size
            assert outliner.header().length() == outliner.viewport().width(), size
            assert outliner.columnWidth(1) == outliner.status_width(), size
            assert outliner.horizontalScrollBar().maximum() == 0, size
    finally:
        window.set_ui_text("normal")
    shot(window.docks["outlinerDock"], preset)


def test_the_status_column_follows_its_contents(window, qtbot):
    """Short states keep the column narrow; a lock widens it, and the
    Entry column gives back what the column takes."""
    load(qtbot, window, "honeycomb_zeeman_rashba")
    outliner = window.outliner
    narrow = outliner.columnWidth(1)
    assert narrow < 84                   # P2's fixed width, now only what "spinful" needs
    entry = outliner.columnWidth(0)
    window.session.do("lock", target="t1")
    assert outliner.item("t1").text(1) == "spinful · locked"
    assert outliner.columnWidth(1) > narrow and \
        outliner.columnWidth(0) == entry - (outliner.columnWidth(1) - narrow)
    assert cut(outliner) == []
    window.session.undo()
    assert outliner.columnWidth(1) == narrow


def test_the_rows_say_what_they_are(window, qtbot):
    """What a row is in the label, its state in the status: no op
    parameters, no "base lattice", no Hilbert space on the section rows."""
    load(qtbot, window, "honeycomb_zeeman_rashba")
    outliner = window.outliner
    texts = {i: (outliner.item(i).text(0), outliner.item(i).text(1)) for i in (
        "s1/geometry", "s1/base", "op1", "s1/regions", "s1/hamiltonian", "t1", "t2",
        "s1/meanfield", "calculations", "c1", "c2")}
    assert texts == {
        "s1/geometry": ("Geometry", ""), "s1/base": ("Honeycomb lattice", ""),
        "op1": ("op1  Supercell · n [2, 2, 1]", ""), "s1/regions": ("Regions", ""),
        "s1/hamiltonian": ("Hamiltonian", ""), "t1": ("t1  Zeeman / exchange field", "spinful"),
        "t2": ("t2  Rashba spin-orbit coupling", "spinful"), "s1/meanfield": ("Mean field", "off"),
        "calculations": ("Calculations", ""), "c1": ("c1  Band structure", ""),
        "c2": ("c2  Density of states", "")}
    # the system: its summary across the row, the kind in the tooltip
    system = outliner.item("s1")
    assert system.text(0) == "s1  graphene with exchange and Rashba"
    assert system.text(1) == "2D · 8 sites · spinful" and outliner.is_detail("s1")
    assert system.isFirstColumnSpanned() and system.font(0).bold()
    assert "a quantum system: 2D, 8 sites, spinful, dimension 16" in system.toolTip(0)
    # every row's tooltip is its full label, then its state in words, on both columns
    for item_id, (label, _) in texts.items():
        item = outliner.item(item_id)
        assert item.toolTip(0) == item.toolTip(1) and item.toolTip(0).startswith(label)
    assert "the Hilbert space after it: spinful" in outliner.item("t1").toolTip(0)
    assert outliner.item("op1").toolTip(0).count("n [2, 2, 1]") == 1   # once, in the label
    assert "the base lattice" in outliner.item("s1/base").toolTip(0)
    assert "not run yet" in outliner.item("c1").toolTip(0)
    assert "on s1" in outliner.item("c1").toolTip(0)
    # several systems: a calculation names its own
    second = window.session.do("add_system", lattice="square_lattice")
    assert outliner.item("c1").text(0) == "c1  Band structure on s1"
    assert outliner.item(second).text(1) == "building…"         # dimmed until it is built
    assert outliner.item(second).foreground(1).color().name() == theme.DISABLED.lower()
    window.session.undo()
    assert outliner.item("c1").text(0) == "c1  Band structure"


def test_the_marks_of_a_row(window, qtbot):
    """One mark per state, from ui/marks.py: disabled, invalid and failed
    in the error colour, a warning, locked, and a calculation's done, stale,
    running and failed."""
    load(qtbot, window, "honeycomb_zeeman_rashba")
    outliner, session = window.outliner, window.session
    error = theme.ERROR.lower()
    session.do("set_enabled", entry="t2", enabled=False)
    t2 = outliner.item("t2")
    assert t2.text(1) == marks.DISABLED == "○" and "disabled" in t2.toolTip(1)
    assert t2.foreground(1).color().name() == theme.DISABLED.lower()
    session.undo()
    square = session.do("add_system", lattice="square_lattice")      # pyqula refuses it
    term = session.do("add_term", system=square, kind="sublattice_imbalance")
    qtbot.waitUntil(lambda: outliner.item(term).text(1) == marks.INVALID == "✗", timeout=120_000)
    item = outliner.item(term)
    assert item.text(0) == f"{term}  Sublattice imbalance"
    assert item.foreground(0).color().name() == item.foreground(1).color().name() == error
    assert "invalid, skipped:" in item.toolTip(0) and "sublattice" in item.toolTip(0)
    session.undo(2)
    settle(qtbot, window)
    session.do("lock", target="s1")
    assert outliner.item("s1").text(1) == "2D · 8 sites · spinful · locked"
    assert "locked (s1)" in outliner.item("s1").toolTip(0)
    session.undo()
    # a calculation: running with its progress, done, stale, failed
    session.calc_jobs["c2"] = SimpleNamespace(status="running", progress=0.7, done=False,
                                              error=None)
    sent = []
    outliner.command.connect(lambda name, args: sent.append(name))
    try:
        outliner.update_calculation(session, "c2")
        qtbot.wait(10)                      # a toggle is sent from a zero-delay timer
        assert sent == []                   # its tooltip changed, no check box was toggled
        assert outliner.item("c2").text(1) == "70%"
        assert "running, 70%" in outliner.item("c2").toolTip(0)
        session.calc_jobs["c2"] = SimpleNamespace(status="failed", progress=0.7, done=True,
                                                  error="no memory left")
        outliner.update_calculation(session, "c2")
        assert outliner.item("c2").text(1) == marks.FAILED
        assert outliner.item("c2").foreground(1).color().name() == error
        assert "failed: no memory left" in outliner.item("c2").toolTip(1)
    finally:
        del session.calc_jobs["c2"]
    outliner.update_calculation(session, "c2")
    assert outliner.item("c2").text(1) == "" and outliner.item("c2").data(
        1, Qt.ItemDataRole.ForegroundRole) is None
    job = session.run_calculation("c1")
    qtbot.waitUntil(lambda: job.done, timeout=300_000)
    assert job.status == "done", job.error
    qtbot.waitUntil(lambda: outliner.item("c1").text(1) == marks.DONE, timeout=10_000)
    session.do("set_param", entry="t1", name="m", value=[0.0, 0.0, 0.3])
    assert outliner.item("c1").text(1) == marks.STALE == "↻"
    assert outliner.item("c1").foreground(1).color().name() == theme.DISABLED.lower()
    assert "stale" in outliner.item("c1").toolTip(0)
    session.undo()
    assert outliner.item("c1").text(1) == marks.DONE


def test_the_mean_field_reads_unclipped(window, qtbot, shot):
    """The mean field reads "off" in the Status column, and when it is on
    its interactions and when it runs, across the row and wrapped when the
    outliner is narrow, never cut."""
    load(qtbot, window, "honeycomb_hubbard")
    outliner = window.outliner
    item = outliner.item("s1/meanfield")
    assert item.text(1) == "U = 3, runs with the calculations"
    assert outliner.is_detail("s1/meanfield") and item.checkState(0) == Qt.CheckState.Checked
    assert "not while editing" in item.toolTip(0)
    dock = window.docks["outlinerDock"]
    window.resizeDocks([dock], [200], Qt.Orientation.Horizontal)       # narrower: wrapped
    settle(qtbot, window)
    one_line = outliner.visualItemRect(outliner.item("s1/geometry")).height()
    assert outliner.visualItemRect(item).height() > 2 * one_line
    assert cut(outliner) == []
    shot(dock, "narrow")
    window.resize(1800, 800)                                           # wide: one line
    window.resizeDocks([dock], [600], Qt.Orientation.Horizontal)
    settle(qtbot, window)
    assert outliner.visualItemRect(item).height() == one_line
    assert cut(outliner) == []
    window.resize(1200, 800)
    # its checkbox sits on the first line, beside the label, and a click there turns it off
    window.resizeDocks([dock], [200], Qt.Orientation.Horizontal)
    settle(qtbot, window)
    index = outliner.indexFromItem(item, 0)
    delegate = outliner.itemDelegateForColumn(0)
    option = QStyleOptionViewItem()
    outliner.initViewItemOption(option)
    rect = outliner.visualRect(index)
    option.rect = QRect(rect.x(), rect.y(), rect.width(), delegate.line_height(option, index))
    delegate.initStyleOption(option, index)
    check = outliner.style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator,
                                            option, outliner)
    assert check.bottom() < rect.y() + one_line
    QTest.mouseClick(outliner.viewport(), Qt.MouseButton.LeftButton, pos=check.center())
    qtbot.waitUntil(lambda: not window.session.document.system("s1").hamiltonian.meanfield
                    .enabled, timeout=5000)
    window.session.undo()
    session = window.session
    session.do("set_meanfield", system="s1", enabled=False)
    item = outliner.item("s1/meanfield")
    assert item.text(1) == "off" and not outliner.is_detail("s1/meanfield")
    assert item.foreground(0).color().name() == theme.DISABLED.lower()
    session.undo()
    # large text in an outliner squeezed to 140 px: "calculations" is wider than the line,
    # and only that word breaks inside, rather than being cut at the edge
    window.set_ui_text("large")
    try:
        window.resizeDocks([dock], [140], Qt.Orientation.Horizontal)
        settle(qtbot, window)
        item = outliner.item("s1/meanfield")
        index = outliner.indexFromItem(item, 0)
        option = QStyleOptionViewItem()
        outliner.initViewItemOption(option)
        option.rect = outliner.visualRect(index)
        _, status, one_line = outliner.itemDelegateForColumn(0).layout(option, index)
        assert not one_line and text_width(outliner.font(), "calculations") > status.width()
        assert cut(outliner) == [], cut(outliner)
        lines = wrapped(outliner.font(), item.text(1), status.width()).splitlines()
        pieces = [w for line in lines for w in line.split() if w not in item.text(1).split()]
        assert pieces and all(piece in "calculations" for piece in pieces)   # that word only
        shot(dock, "large_squeezed")
    finally:
        window.set_ui_text("normal")
    window.reset_layout()


def test_parameters_read_short():
    """An op's or a model's parameters in a label: numbers as %g, so that a
    filling of a third does not take the whole row."""
    assert _summary({"filling": 1 / 3, "seed": 1}) == "filling 0.333333, seed 1"
    assert _summary({"n": 4.0, "nedges": 6, "rot": 0.0, "clean": True}) == \
        "n 4, nedges 6, rot 0, clean"
    assert _summary({"n": [2, 2, 1]}) == "n [2, 2, 1]"
    assert _summary({"m": [0.0, 0.0, 0.1]}) == "m [0, 0, 0.1]"
