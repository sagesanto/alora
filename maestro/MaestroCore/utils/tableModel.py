import pandas as pd
from scheduleLib.candidateDatabase import Candidate
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QTextOption

def splitListIntoContinuousRuns(list, ascending=True):
    listOfLists = []
    currentList, oldValue = None, None
    for value in list:
        if oldValue is None:
            oldValue = value
            currentList = [value]
            continue
        if (ascending and value - oldValue == 1) or (not ascending and oldValue - value == 1):
            currentList.append(value)
        else:
            listOfLists.append(currentList)
            currentList = [value]
        oldValue = value
    listOfLists.append(currentList)
    return listOfLists


class CandidateTableModel(QAbstractTableModel):
    def __init__(self, data: pd.DataFrame):
        """!A crude table for displaying candidates, built on pd DataFrames. It's probably easier just to make a new table model when you want to add values, not try to modify this one. """
        super(CandidateTableModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if self._data is not None:
                value = self._data.iloc[index.row(), index.column()]
                return str(value)

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]

    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._data.columns[section])

            if orientation == Qt.Orientation.Vertical:
                return str(self._data.index[section])

    def sort(self, column: int, order: Qt.SortOrder):
        self.layoutAboutToBeChanged.emit()
        col = self._data.columns[column]
        self._data.sort_values(by=col, ascending=(order == Qt.SortOrder.AscendingOrder), axis=0, inplace=True)
        self.layoutChanged.emit()

    def selectedRows(self, view):
        selectedIndexes = view.selectedIndexes()
        return list(set([index.row() for index in selectedIndexes]))

    def removeSelectedItems(self, view):
        selectedRowRuns = splitListIntoContinuousRuns(sorted(self.selectedRows(view), reverse=True), ascending=False)
        for selectedRows in selectedRowRuns:
            self.beginRemoveRows(QModelIndex(), selectedRows[-1], selectedRows[0])  # reverse order
            self._data.drop(index=selectedRows, inplace=True)
            self._data.reset_index(inplace=True, drop=True)
            self.endRemoveRows()


def loadDfInTable(dataframe: pd.DataFrame, table, clearFirst=True):  # SHARED MUTABLE STATE!!!!! :D
    if clearFirst:
        table.clear()
    df = dataframe.copy()  # .reset_index()
    table.setSortingEnabled(False)
    columnHeaders = df.columns
    numRows, numCols = len(df.index), len(columnHeaders)
    table.setRowCount(numRows)
    table.setColumnCount(numCols)
    for i in range(numRows):
        for j in range(numCols):
            item = QTableItem(str(df.iloc[i][j]))
            table.setItem(i, j, item)
    table.setHorizontalHeaderLabels(columnHeaders)
    table.resizeColumnsToContents()
    table.resizeRowsToContents()
    table.setSortingEnabled(True)


class FlexibleTableModel(QAbstractTableModel):
    def __init__(self, headers, data=None):
        super().__init__()
        self.headers = headers
        self._data = data or []

    def rowCount(self, parent=None):
        return len(self._data)
    
    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            dat = self._data[index.row()][index.column()]
            return dat.CandidateName if isinstance(dat, Candidate) else dat
        elif role == Qt.TextElideMode:
            return QTextOption.WrapAtWordBoundaryOrAnywhere

        return None

    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.ItemDataRole.DisplayRole:
            # if orientation == Qt.Orientation.Horizontal:
            #     return str(self._data.columns[section])

            if orientation == Qt.Orientation.Horizontal:
                return str(self.headers[section])

    def addItem(self, newItem):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(newItem)
        self.endInsertRows()
        # self.rowsInserted.emit(QModelIndex(), len(self._data), len(self._data))
        # this shouldnt be necessary, but it seems like it might be ^

    def sort(self, column: int, order: Qt.SortOrder):
        self.layoutAboutToBeChanged.emit()
        self._data.sort(key=lambda x: x[column], reverse=(order == Qt.SortOrder.DescendingOrder))
        self.layoutChanged.emit()

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
