import os.path

from PyQt6.QtCore import pyqtSignal, QAbstractListModel
from PyQt6.QtWidgets import QPushButton, QFileDialog, QListView, QAbstractItemView, QApplication
from PyQt6 import QtGui, QtCore
from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QTableWidget, \
    QTableWidgetItem as QTableItem, QLineEdit, QListView, QDockWidget, QComboBox, \
            QPushButton, QMessageBox, QHBoxLayout, QVBoxLayout, QCheckBox, QLabel, QListWidgetItem, \
            QSizePolicy, QSpinBox, QSpacerItem, QTextEdit, QDoubleSpinBox, QScrollArea, QDialog, QDialogButtonBox
from PyQt6.QtCore import Qt, QItemSelectionModel, QDateTime, QSortFilterProxyModel, QTimer, QMimeData, QDataStream, QByteArray, \
    QIODevice, QIODeviceBase, QEventLoop, QCoreApplication
import PyQt6.QtWidgets as QtWidgets
from PyQt6.QtGui import QPalette, QColor, QDrag
from MaestroCore.utils.utilityFunctions import onlyEnableWhenItemsSelected
from datetime import datetime, timedelta 
import pandas as pd

def getSelectedFromTable(table, colIndex):
    selected = []
    indexes = table.selectionModel().selectedRows()
    model = table.model()
    for index in indexes:
        selected.append(model.data(model.index(index.row(), colIndex)))
    return selected


class ModelRemoveButton(QPushButton):
    def connectList(self, list: QListView):
        try:
            self.clicked.disconnect()
        except:
            pass
        self.clicked.connect(lambda: list.model().removeSelectedItems(list))
        onlyEnableWhenItemsSelected(self, list)


class AddSelectedButton(QPushButton):
    """!
    When pressed, this button will get a list of the selected items in a column (indicated by colIndex) of a QTableView sourceTable. Call f with this list, and add the returned results to a recipient QListModel
    This button will be disabled when no items are selected in the table, and become enabled when items are selected
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = self.recipient = self.index = self.function = None

    def connectPair(self, sourceTable: QAbstractItemView, colIndex, recipient: QAbstractListModel, f):
        self.source = sourceTable
        self.index = colIndex
        self.recipient = recipient
        self.function = f
        self.clicked.connect(self.addToList)
        sourceTable.selectionModel().selectionChanged.connect(
            lambda: self.setEnabled(bool(len(sourceTable.selectedIndexes()))))

    def addToList(self):
        ls = self.function(getSelectedFromTable(self.source, self.index))
        for l in ls:
            if l not in self.recipient.data:
                self.recipient.addItem(l)


class FileSelectionButton(QPushButton):
    chosen = pyqtSignal(str)

    def __init__(self, parent=None, default=None):
        super().__init__(parent)
        self.pattern = None
        self.prompt = None
        self.clicked.connect(self.chooseFile)
        self.path = None
        self.default = default
        self.dir = False

    def setText(self, text: str):  # if we don't have default text, make the first time our text is set the default
        if self.default is None:
            self.default = text
        super().setText(text)

    def updateFilePath(self, path):
        self.path = path
        self.setNameFromPath(path)

    def setNameFromPath(self, path):
        self.setText(path.split("/")[
                         -1])  # this was originally split by os.sep (\ on windows) but it seems to always come in with /

    def getPath(self):
        return self.path

    def setPrompt(self, prompt):
        self.prompt = prompt
        return self

    def setPattern(self, pattern):
        self.pattern = pattern
        return self

    def isDirectoryDialog(self, dir: bool):
        self.dir = dir

    def chooseFile(self):
        if self.dir:
            filepath = QFileDialog.getExistingDirectory(self, self.prompt)
        else:
            filepath = QFileDialog.getOpenFileName(self, self.prompt, self.path or "./", self.pattern)[
                0]
        #         filepath = QFileDialog.getOpenFileName(self, 'Select Database File', "./", "Database File (*.db)")[
        #                        0] or self.default
        filepath = (self.default if self.path is None else os.path.abspath(self.path)) if not filepath else filepath
        self.updateFilePath(filepath)
        self.chosen.emit(self.path)

class DraggableButton(QPushButton):
    def __init__(self, text, index, main_window, parent=None):
        super().__init__(text, parent)
        self.index = index
        self.main_window = main_window
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Left click – open the popup using the main window reference
            self.main_window.openPopupDialog(self.text())
        elif event.button() == Qt.MouseButton.RightButton:
            # Right click – start dragging
            drag = QDrag(self)
            mime_data = QMimeData()

            # Encode row index into the mime data
            data = QByteArray()
            stream = QDataStream(data, QIODeviceBase.OpenModeFlag.WriteOnly)
            stream.writeInt(self.index)
            mime_data.setData("application/x-schedule-item", data)

            drag.setMimeData(mime_data)
            drag.setPixmap(self.grab())

            drag.exec(Qt.DropAction.MoveAction)  



class DropWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.parent = parent
        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # ✅ Correct in Qt6
        self.setLayout(self.layout)
        self.prev_container_size = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-schedule-item"):
            event.accept()
            self.prev_container_size = self.parent.schedule_display_container.height()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-schedule-item"):
            data = event.mimeData().data("application/x-schedule-item")
            stream = QDataStream(data, QIODeviceBase.OpenModeFlag.ReadOnly)
            from_index = stream.readInt()

            # ✅ `position()` returns QPointF in Qt6, convert to QPoint
            pos = event.position().toPoint()
            insert_at = self.findButtonIndex(pos)

            if insert_at is not None and insert_at != from_index:
                self.rearrangeSchedule(from_index, insert_at)


            event.accept()  # ✅ Explicit acceptance

        else:
            event.ignore()

    def findButtonIndex(self, pos):
        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if widget and widget.geometry().contains(pos):
                return i
        return None

    def rearrangeSchedule(self, from_index, to_index):
        if from_index < 0 or from_index >= len(self.parent.scheduleDf):
            return
        if to_index < 0 or to_index >= len(self.parent.scheduleDf):
            return

        row = self.parent.scheduleDf.iloc[[from_index]].copy()
        print(f"From slot: {from_index} ({self.parent.scheduleDf.iloc[[from_index]]['Target']})")
        print(f"To slot: {to_index} ({self.parent.scheduleDf.iloc[[to_index]]['Target']})")

        # remove the row from the original position
        self.parent.scheduleDf.drop(index=from_index, inplace=True)
        self.parent.scheduleDf.reset_index(drop=True, inplace=True)

        duration = row["Duration (Minutes)"].values[0]  # length of the observation that we're moving around
        
        if from_index < to_index:  # we're moving the observation down (later) in the schedule
            idx1 = from_index
            idx2 = to_index-1
            dt = timedelta(minutes=-duration)

        else:
            idx1 = to_index
            idx2 = from_index-1
            dt = timedelta(minutes=duration)
            # in this case, we do the adjustment to the target row before we move things around
            row["Start Time (UTC)"] = self.parent.scheduleDf.loc[idx1:idx2,"Start Time (UTC)"].values[0]

        # shift the affected rows (the rows that are being leapfrogged) by the duration of the observation
        self.parent.scheduleDf.loc[idx1:idx2,"Start Time (UTC)"] = self.parent.scheduleDf.loc[idx1:idx2,"Start Time (UTC)"] + dt
        self.parent.scheduleDf.loc[idx1:idx2,"End Time (UTC)"] = self.parent.scheduleDf.loc[idx1:idx2,"End Time (UTC)"] + dt

        if from_index < to_index:
            # move the start time of the row we're moving to be the end time of the last row that was leapfrogged
            row["Start Time (UTC)"] = self.parent.scheduleDf.loc[idx1:idx2,"End Time (UTC)"].values[-1]

        # move the end time of the observation to match the start (plus the duration)
        row["End Time (UTC)"] = row["Start Time (UTC)"] + timedelta(minutes=duration)

        upper = self.parent.scheduleDf.iloc[:to_index]
        lower = self.parent.scheduleDf.iloc[to_index:]

        # stack the three parts together
        self.parent.scheduleDf = pd.concat([upper, row, lower], ignore_index=True)
        # self.parent.scheduleDf.reset_index(drop=True, inplace=True)

        # now that we've made the changes, redraw the display
        self.parent.displaySchedule(redraw=True)