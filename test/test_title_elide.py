"""Output titles that do not fit their cell are elided, the full text shows on hover (Qt and dpg)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


# ----------------------------------------------------------------------------- dpg (pure helper + cell)
def test_dpg_elide_text_keeps_short_lines_and_shortens_long_ones():
    dpg_image = pytest.importorskip("interactive_pipe.graphical.dpg_image")

    def measure(text):
        return 10 * len(text)

    assert dpg_image.elide_text("short", 100, measure) == "short"
    assert dpg_image.elide_text("abcdefghijklmnop", 60, measure) == "abcde…"
    assert dpg_image.elide_text("ok\nabcdefghijklmnop", 60, measure) == "ok\nabcde…"
    assert dpg_image.elide_text("anything", None, measure) == "anything"


def test_dpg_cell_title_tooltip_only_when_elided():
    dpg_image = pytest.importorskip("interactive_pipe.graphical.dpg_image")
    from interactive_pipe.graphical import dpg_backend

    dpg = dpg_backend.dpg
    dpg.create_context()
    try:
        with dpg.window():
            title = dpg.add_text("")
            tooltip = dpg.add_tooltip(parent=title, show=False)
            tooltip_text = dpg.add_text("", parent=tooltip)
        cell = {"title": title, "title_tooltip": tooltip, "title_tooltip_text": tooltip_text, "title_width": None}
        long_title = "a very long title that cannot fit in a narrow image cell"
        dpg_image.set_cell_title(cell, long_title)
        assert dpg.get_value(title) == long_title
        assert not dpg.get_item_configuration(tooltip)["show"]

        cell["title_width"] = 80
        dpg_image.set_cell_title(cell)  # relayout re-applies the stored title
        assert dpg.get_value(title).endswith("…")
        assert dpg.get_value(tooltip_text) == long_title
        assert dpg.get_item_configuration(tooltip)["show"]
    finally:
        dpg_backend.destroy_context()


# ----------------------------------------------------------------------------- Qt
def test_qt_elided_label_shortens_and_sets_tooltip():
    qt_widgets = pytest.importorskip("interactive_pipe.graphical.qt_widgets")
    from interactive_pipe.graphical.qt_backend import QApplication

    _app = QApplication.instance() or QApplication([])
    label = qt_widgets.ElidedLabel("short")
    label.show()
    label.resize(400, 30)
    assert label.displayed_text() == "short"
    assert label.toolTip() == ""

    long_title = "a very long title that cannot fit in a narrow image cell | Gamma: 1.00"
    label.setText(long_title)
    label.show()  # hidden widgets get no resize event
    label.resize(80, 30)
    assert label.text() == long_title  # text() keeps the full title
    assert label.displayed_text() != long_title
    assert label.displayed_text().endswith("…")
    assert label.toolTip() == long_title
    assert label.minimumSizeHint().width() == 0  # never forces its column wider

    label.resize(2000, 30)
    assert label.displayed_text() == long_title
    assert label.toolTip() == ""
    label.close()


def test_qt_elided_label_at_its_size_hint_shows_the_full_text():
    qt_widgets = pytest.importorskip("interactive_pipe.graphical.qt_widgets")
    from interactive_pipe.graphical.qt_backend import QApplication

    _app = QApplication.instance() or QApplication([])
    label = qt_widgets.ElidedLabel("Original: elephant")
    label.show()
    label.resize(label.sizeHint())
    assert label.displayed_text() == "Original: elephant"
    assert label.toolTip() == ""
    label.close()
