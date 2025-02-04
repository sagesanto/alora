from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QDateTime, QAbstractTableModel

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
