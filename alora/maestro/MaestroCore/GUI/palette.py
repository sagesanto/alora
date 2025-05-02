from PyQt6.QtGui import QPalette, QColor, QGuiApplication

from os.path import join, dirname, abspath, pardir

# https://doc.qt.io/qt-6/stylesheet-examples.html#customizing-qdockwidget
# https://doc.qt.io/qt-6/stylesheet-reference.html#list-of-properties
# https://doc.qt.io/qt-6/stylesheet-examples.html#customizing-qtabwidget-and-qtabbar
# https://github.com/QuasarApp/QStyleSheet/blob/master/materialStyle/materialStyle.css

colors = {
    "selected_text": "#ffffff",
    "selected": "#4575e4",
    "focused": "#e7e7e7",
    "border": "#c2c7cb",
    "background": "#ffffff",
}

palette =  QGuiApplication.palette()

# Define colors
selected_text = QColor(colors["selected_text"])
selected = QColor(colors["selected"])
focused = QColor(colors["focused"])
border = QColor(colors["border"])
background = QColor(colors["background"])

# Apply colors to the palette
palette.setColor(QPalette.ColorRole.HighlightedText, selected_text)  # Selection text color
palette.setColor(QPalette.ColorRole.Highlight, selected)  # Selection background color
palette.setColor(QPalette.ColorRole.Base, background)  # Background for input fields
palette.setColor(QPalette.ColorRole.Window, background)  # General background
# palette.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))  # General text color
palette.setColor(QPalette.ColorRole.Button, background)  # Button background
# palette.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))  # Button text
# palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))  # Text color
# palette.setColor(QPalette.ColorRole.AlternateBase, focused)  # Alternate row background

stylesheet_path = join(dirname(abspath(__file__)),"styles.qss")

stylesheet = ""
with open(stylesheet_path, "r") as f:
    stylesheet = f.read()

for cname, c in colors.items():
    stylesheet = stylesheet.replace("{{" + cname + "}}",c)


