from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QDateTime, QAbstractTableModel
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox, QListWidget, QListWidgetItem, QFrame, QSpacerItem
from PyQt6.QtGui import QPixmap
import PyQt6.QtWidgets as QtWidgets


from scheduleLib.candidateDatabase import Candidate, BaseCandidate


class FlexibleListModel(QAbstractListModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data or []

    def rowCount(self, parent=None):
        return len(self._data)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            dat = self._data[index.row()]
            return dat.CandidateName if isinstance(dat, BaseCandidate) else dat

        return None

    def addItem(self, newItem):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(newItem)
        self.endInsertRows()

    def selectedRows(self, view):
        selectedIndexes = view.selectedIndexes()
        return [index.row() for index in selectedIndexes]

    def removeSelectedItems(self, view):
        selectedRows = self.selectedRows(view)
        # Sort the rows in reverse order to avoid index shifting when removing items
        selectedRows.sort(reverse=True)

        for row in selectedRows:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._data[row]
            self.endRemoveRows()

    def removeItem(self, item):
        if item in self._data:
            i = self._data.index(item)
            self.beginRemoveRows(QModelIndex(), i, i)
            del self._data[i]
            self.endRemoveRows()


class DateTimeRangeListModel(FlexibleListModel):
    def __init__(self):
        super().__init__()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            dat = self._data[index.row()]
            return "{} - {}".format(dat[0].toString(dat[2]), dat[1].toString(dat[2]))

        if role == Qt.ItemDataRole.EditRole:
            dat = self._data[index.row()]
            return str(dat[0].toSecsSinceEpoch() + " " + dat[1].toSecsSinceEpoch())

        return None

    def addItem(self, startTime: QDateTime, endTime: QDateTime, timeDisplayFormat="MM/dd/yyyy hh:mm"):
        super().addItem((startTime, endTime, timeDisplayFormat))


class ModuleListEntry(QWidget):
    def __init__(self, name, active, icon_path, parent=None):
        super().__init__(parent)
        self.name = name
        layout = QVBoxLayout(self)
        content_layout = QHBoxLayout()
        # self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(active)
        # checkbox.stateChanged.connect(lambda state,n=name: self.module_manager.activate_module(n) if state == Qt.CheckState.Checked else self.module_manager.deactivate_module(n))
        # self.checkbox.stateChanged.connect(lambda state,n=name: self.handle_module_change(state,n))
        # checkbox.stateChanged.connect(lambda state,n=name: self.module_manager.activate_module(n) if state == Qt.CheckState.Checked else self.module_manager.deactivate_module(n))
        content_layout.addWidget(self.checkbox)
        label = QLabel()
        label.setText(name)
        content_layout.addWidget(label)
        # add spacer to push icon to the right
        spacer = QSpacerItem(1, 1, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        content_layout.addItem(spacer)
        self.icon_label = QLabel()
        pixmap = QPixmap(icon_path)
        self.icon_label.setPixmap(pixmap)
        content_layout.addWidget(self.icon_label)
        layout.addLayout(content_layout)

        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        self.setLayout(layout)
    
    def change_icon(self, icon_path):
        pixmap = QPixmap(icon_path)
        self.icon_label.setPixmap(pixmap)
    
    def change_icon_tooltip(self, tooltip):
        self.icon_label.setToolTip(tooltip)