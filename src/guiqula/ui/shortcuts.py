"""Keyboard shortcuts (PLAN.md phase 5, design item 11): one table, which
the window's actions, the Help > Keyboard shortcuts dialog and guiqula's
user guide share.

A shortcut's context says where it works: "window" anywhere in the main
window; "outliner", "canvas" only while that widget has the focus (so that
single keys never fire while typing into a box); "console", "code editor",
"2D canvas" and "3D canvas" are keys those widgets handle themselves (the
last two are how the drawings are moved, ui/canvas_navigation.py and the
numpad of ui/pyvista_view.py), listed here so the dialog shows them. A key
of the window context may not be used by any other shortcut (Qt would find
it ambiguous when both are live); keys of widget contexts may repeat across
widgets. tests/ui/test_polish.py checks both, and that every shortcut of
the table is bound in the window.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

WIDGET_CONTEXTS = ("outliner", "canvas")      # QAction shortcuts on one widget
# keys the widget handles itself
HANDLED_CONTEXTS = ("console", "code editor", "2D canvas", "3D canvas")

# (id, keys, context, what it does)
SHORTCUTS = (
    ("new", ("Ctrl+N",), "window", "new document"),
    ("open", ("Ctrl+O",), "window", "open a project"),
    ("gallery", ("Ctrl+Shift+O",), "window", "presets gallery"),
    ("save", ("Ctrl+S",), "window", "save"),
    ("save_as", ("Ctrl+Shift+S",), "window", "save as"),
    ("export_script", ("Ctrl+E",), "window",
     "export the pyqula script of the selected calculation"),
    ("export_bundle", ("Ctrl+Shift+E",), "window",
     "export the figure, data and script of the selected calculation's result"),
    ("quit", ("Ctrl+Q",), "window", "quit"),
    ("undo", ("Ctrl+Z",), "window", "undo"),
    ("redo", ("Ctrl+Shift+Z", "Ctrl+Y"), "window", "redo"),
    ("workspace_geometry", ("Ctrl+1",), "window", "Geometry workspace"),
    ("workspace_hamiltonian", ("Ctrl+2",), "window", "Hamiltonian (or Model) workspace"),
    ("workspace_calculate", ("Ctrl+3",), "window", "Calculate workspace"),
    ("find", ("Ctrl+F",), "window",
     "the Add menu of the workspace, with its search line (ops, terms or calculations); "
     "the filter of the start page"),
    ("structure_tab", ("Ctrl+0",), "window", "show the Structure tab"),
    ("close_result", ("Ctrl+W",), "window", "close the result tab or the grid shown"),
    ("run", ("F5",), "window", "run the selected calculation"),
    ("cancel", ("Esc",), "window", "cancel the selected calculation's job"),
    ("shortcuts", ("Ctrl+/",), "window", "this list of shortcuts"),
    ("help", ("F1",), "window", "help on the selected entry"),
    ("help_search", ("Shift+F1",), "window",
     "the Help panel's search line: the entries and guide sections that answer a question"),
    ("delete", ("Del",), "outliner", "delete the selected entry"),
    ("rename", ("F2",), "outliner", "rename the selected entry"),
    ("duplicate", ("Ctrl+D",), "outliner", "duplicate the selected entry"),
    ("move_up", ("Alt+Up",), "outliner", "move the selected entry up"),
    ("move_down", ("Alt+Down",), "outliner", "move the selected entry down"),
    ("tool_pick", ("P",), "canvas", "pick tool (click an atom)"),
    ("tool_box", ("B",), "canvas", "box selection tool"),
    ("tool_lasso", ("L",), "canvas", "lasso selection tool"),
    ("select_all", ("Ctrl+A",), "canvas", "select every site"),
    ("select_none", ("Ctrl+Shift+A",), "canvas", "select nothing"),
    ("select_invert", ("Ctrl+I",), "canvas", "invert the selection"),
    ("remove_selected", ("Del", "Backspace"), "canvas",
     "remove the selected atoms (a Remove atoms op)"),
    ("fit", ("Home",), "canvas", "show the whole geometry"),
    ("zoom_in", ("+", "="), "2D canvas", "zoom in (in 3D as well)"),
    ("zoom_out", ("-",), "2D canvas", "zoom out (in 3D as well)"),
    ("zoom_selection", ("3",), "2D canvas",
     "zoom to the selected sites, or to everything when none is (in 3D as well)"),
    ("zoom_drawing", ("4",), "2D canvas", "show the whole drawing (Home does it too)"),
    ("zoom_previous", ("`",), "2D canvas", "the previous zoom"),
    ("zoom_next", ("~", "Shift+`"), "2D canvas", "the next zoom"),
    ("scroll_left", ("Ctrl+Left",), "2D canvas", "scroll left (pan left in 3D)"),
    ("scroll_right", ("Ctrl+Right",), "2D canvas", "scroll right (pan right in 3D)"),
    ("scroll_up", ("Ctrl+Up",), "2D canvas", "scroll up (pan up in 3D)"),
    ("scroll_down", ("Ctrl+Down",), "2D canvas", "scroll down (pan down in 3D)"),
    ("view_axes", ("Num+1", "Num+3", "Num+7"), "3D canvas", "front, right and top view"),
    ("view_opposite", ("Ctrl+Num+1", "Ctrl+Num+3", "Ctrl+Num+7"), "3D canvas",
     "back, left and bottom view"),
    ("view_orbit", ("Num+4", "Num+6", "Num+8", "Num+2"), "3D canvas",
     "orbit left, right, up and down by 15 degrees"),
    ("view_pan", ("Ctrl+Num+4", "Ctrl+Num+6", "Ctrl+Num+8", "Ctrl+Num+2"), "3D canvas",
     "pan left, right, up and down"),
    ("view_projection", ("Num+5",), "3D canvas", "perspective or orthographic"),
    ("view_flip", ("Num+9",), "3D canvas", "the opposite side of the view"),
    ("view_zoom", ("Num++", "Num+-"), "3D canvas", "zoom in and out"),
    ("view_selected", ("Num+.",), "3D canvas", "the selected sites in sight"),
    ("console_run", ("Return",), "console", "run the input"),
    ("console_newline", ("Shift+Return",), "console", "a new line in the input"),
    ("console_history", ("Up", "Down"), "console", "walk the history"),
    ("code_apply", ("Ctrl+Return",), "code editor", "apply the code of a Python node"),
)
BY_ID = {row[0]: row for row in SHORTCUTS}
ID_PROPERTY = "guiqula_shortcut"


def keys(shortcut_id):
    return BY_ID[shortcut_id][1]


def text(shortcut_id):
    """The keys as the platform writes them ("Ctrl+Shift+Z, Ctrl+Y")."""
    return ", ".join(QKeySequence(k).toString(QKeySequence.SequenceFormat.NativeText)
                     for k in keys(shortcut_id))


def bind(action, shortcut_id):
    """Give a QAction the keys of a shortcut, in its context (a widget
    context: the action must be added to that widget)."""
    shortcut_id, key_list, context, _ = BY_ID[shortcut_id]
    if context in HANDLED_CONTEXTS:
        raise ValueError(f"{shortcut_id} is handled by its widget, not bound to an action")
    action.setShortcuts([QKeySequence(k) for k in key_list])
    action.setShortcutContext(Qt.ShortcutContext.WindowShortcut if context == "window"
                              else Qt.ShortcutContext.WidgetShortcut)
    action.setProperty(ID_PROPERTY, shortcut_id)
    return action


def rows():
    """(context, keys as text, what) for the dialog and the user guide."""
    return [(context, text(sid), what) for sid, _, context, what in SHORTCUTS]


def markdown_table():
    """The table as guiqula's user guide shows it (a test keeps them equal)."""
    lines = ["| where | keys | what |", "|---|---|---|"]
    lines += [f"| {context} | {keys} | {what} |" for context, keys, what in rows()]
    return "\n".join(lines)
