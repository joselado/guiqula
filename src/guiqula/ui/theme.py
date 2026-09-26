"""The plain Qt look (decision 13.6): the Fusion style with an explicit
light palette, so a dark desktop theme does not produce a half-dark window,
and the few colours the widgets share. A dark palette arrives with the
theming of phase 5."""
from PySide6.QtGui import QColor, QPalette

# shared colours (also used by the structure canvas, as hex strings)
ERROR = "#b3261e"
ERROR_BACKGROUND = "#fde7e4"
NOTICE_BACKGROUND = "#fff4d6"
DISABLED = "#8a8a8a"
SUBLATTICE = {1.0: "#2f6db3", -1.0: "#d9822b", None: "#4a4a4a"}
SELECTED = "#e0218a"
REGION = "#2e9e5b"
REMOVED = "#b3261e"
BOND = "#9a9a9a"
CELL = "#5b8fd0"

LIGHT = {
    QPalette.ColorRole.Window: "#efefef",
    QPalette.ColorRole.WindowText: "#1e1e1e",
    QPalette.ColorRole.Base: "#ffffff",
    QPalette.ColorRole.AlternateBase: "#f5f5f5",
    QPalette.ColorRole.ToolTipBase: "#ffffe1",
    QPalette.ColorRole.ToolTipText: "#1e1e1e",
    QPalette.ColorRole.Text: "#1e1e1e",
    QPalette.ColorRole.Button: "#e8e8e8",
    QPalette.ColorRole.ButtonText: "#1e1e1e",
    QPalette.ColorRole.BrightText: "#ffffff",
    QPalette.ColorRole.Highlight: "#3874c8",
    QPalette.ColorRole.HighlightedText: "#ffffff",
    QPalette.ColorRole.Link: "#2f6db3",
    QPalette.ColorRole.PlaceholderText: "#8a8a8a",
}

STYLESHEET = f"""
QFrame#errorBar {{ background: {ERROR_BACKGROUND}; border-bottom: 1px solid {ERROR}; }}
QFrame#recoveryBar {{ background: {NOTICE_BACKGROUND}; border-bottom: 1px solid #d8b24a; }}
QLabel#formError {{ color: {ERROR}; }}
QLabel#formTitle {{ font-weight: bold; font-size: 11pt; }}
QLabel#formDoc {{ color: #505050; }}
"""


def apply(app):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in LIGHT.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(DISABLED))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
