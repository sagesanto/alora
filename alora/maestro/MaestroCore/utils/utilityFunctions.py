from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QTableWidget, \
    QTableWidgetItem as QTableItem, QLineEdit, QListView, QDockWidget, QComboBox, QPushButton, QMessageBox, QTableView
from PyQt6.QtCore import Qt, QItemSelectionModel, QDateTime
import pandas as pd
from datetime import datetime

from scheduleLib import genUtils


def getSelectedFromList(view: QListView):
    selectedIndexes = view.selectedIndexes()
    return [index.data(Qt.ItemDataRole.DisplayRole) for index in selectedIndexes]


def redock(dock: QDockWidget, window):
    dock.setParent(window)
    dock.setFloating(False)


def updateTableDisplay(tableView: QTableView):
    tableView.setSortingEnabled(False)
    tableData = tableView.model()._data
    if isinstance(tableData, pd.DataFrame):
        for i, col in enumerate(tableData.columns):
            max_char = max(max([len(str(x)) for x in tableData[col].values]), len(col))
            tableView.setColumnWidth(i, max_char * 10)
    else:
        tableView.resizeColumnsToContents()
    tableView.setSortingEnabled(True)
    # table.resizeRowsToContents()


def addLineContentsToList(lineEdit: QLineEdit, lis):
    if lineEdit.text():
        lis.addItem(lineEdit.text())
        lineEdit.clear()


def getSelectedFromTable(table, colIndex):
    selected = []
    indexes = table.selectionModel().selectedRows()
    model = table.model()
    for index in indexes:
        selected.append(model.data(model.index(index.row(), colIndex), Qt.ItemDataRole.DisplayRole))
    return selected


def loadDfInTable(dataframe: pd.DataFrame, table: QTableWidget, clearFirst=True):  # SHARED MUTABLE STATE!!!!! :D
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
            item = QTableItem(str(df.iloc[i].iloc[j]))
            table.setItem(i, j, item)
    table.setHorizontalHeaderLabels(columnHeaders)
    table.resizeColumnsToContents()
    table.resizeRowsToContents()
    table.setSortingEnabled(True)


def comboValToIndex(comboBox: QComboBox, val):
    return comboBox.findText(val())


def datetimeToQDateTime(dt: datetime):
    return QDateTime.fromSecsSinceEpoch(int(dt.timestamp()))


def qDateTimeToDatetime(t):
    return datetime.fromtimestamp(t.toSecsSinceEpoch())


def qDateTimeEditToString(timeEdit, fmt="MM/dd/yyyy hh:mm"):
    return timeEdit.dateTime().toString(fmt)


def onlyEnableWhenItemsSelected(button, sourceView):

    # if the view sourceView has its model replaced with a new one and *then* the old model emits modelAboutToBeReset,
    # these two lines should allow the buttons to become attached to the new TableModel
    sourceView.model().modelAboutToBeReset.connect(lambda: onlyEnableWhenItemsSelected(button, sourceView))
    sourceView.model().modelAboutToBeReset.connect(lambda: button.setEnabled(False))
    # sourceView.model().modelAboutToBeReset.connect(lambda: print("modelAboutToBeReset"))

    sourceView.selectionModel().selectionChanged.connect(
        lambda: button.setEnabled(
            bool(len(sourceView.selectedIndexes()))))
    
    # sourceView.selectionModel().selectionChanged.connect(lambda: print(len(sourceView.selectedIndexes())))
