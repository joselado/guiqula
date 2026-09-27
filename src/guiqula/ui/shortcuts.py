"""Keyboard shortcuts (PLAN.md phase 5, design item 11): one table, which
the window's actions, the Help > Keyboard shortcuts dialog and guiqula's
user guide share.

A shortcut's context says where it works: "window" anywhere in the main
window; "outliner", "canvas" only while that widget has the focus (so that
single keys never fire while typing into a box); "console" and "code
editor" are keys those editors handle themselves, listed here so the
dialog shows them. A key of the window context may not be used by any
other shortcut (Qt would find it ambiguous when both are live); keys of
widget contexts may repeat across widgets. tests/ui/test_shortcuts.py
checks both, and that every shortcut of the table is bound in the window.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

WIDGET_CONTEXTS = ("outliner", "canvas")      # QAction shortcuts on one widget
HANDLED_CONTEXTS = ("console", "code editor")  # keys the widget handles itself

# (id, keys, context, what it does)
SHORTCUTS = (
    ("new", ("Ctrl+N",), "window", "new document"),
    ("open", ("Ctrl+O",), "window", "open a project"),
    ("gallery", ("Ctrl+Shift+O",), "window", "presets gallery"),
    ("save", ("Ctrl+S",), "window", "save"),
    ("save_as", ("Ctrl+Shift+S",), "window", "save as"),
    ("export_script", ("Ctrl+E",), "window",
     "export the pyqula script of the selected calculation"),
    ("quit", ("Ctrl+Q",), "window", "quit"),
    ("undo", ("Ctrl+Z",), "window", "undo"),
    ("redo", ("Ctrl+Shift+Z", "Ctrl+Y"), "window", "redo"),
    ("workspace_geometry", ("Ctrl+1",), "window", "Geometry workspace"),
    ("workspace_hamiltonian", ("Ctrl+2",), "window", "Hamiltonian (or Model) workspace"),
    ("workspace_calculate", ("Ctrl+3",), "window", "Calculate workspace"),
    ("find", ("Ctrl+F",), "window",
     "search the palette of the workspace (ops, terms or calculations)"),
    ("structure_tab", ("Ctrl+0",), "window", "show the Structure tab"),
    ("close_result", ("Ctrl+W",), "window", "close the result tab shown"),
    ("run", ("F5",), "window", "run the selected calculation"),
    ("cancel", ("Esc",), "window", "cancel the selected calculation's job"),
    ("shortcuts", ("Ctrl+/",), "window", "this list of shortcuts"),
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
    ("remove_selected", ("Del",), "canvas", "remove the selected atoms (a Remove atoms op)"),
    ("fit", ("Home",), "canvas", "show the whole geometry"),
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
