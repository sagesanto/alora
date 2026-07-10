from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QTableWidget, \
    QTableWidgetItem as QTableItem, QLineEdit, QListView, QDockWidget, QComboBox, QPushButton, QMessageBox, QTableView
from PyQt6.QtCore import Qt, QItemSelectionModel, QDateTime
from PyQt6 import QtWidgets
import pandas as pd
from datetime import datetime
from os.path import join, abspath, dirname
from alora.maestro.scheduleLib import genUtils

# used to align a table column centered
class CenterAlignDelegate(QtWidgets.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super(CenterAlignDelegate, self).initStyleOption(option, index)
        option.displayAlignment = Qt.AlignmentFlag.AlignCenter

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
            max_char = max(*[len(str(x)) for x in tableData[col].values], len(col))
            tableView.setColumnWidth(i, max_char * 10)
            if isinstance(tableData[col].values[0], (str)):
                tableView.setItemDelegateForColumn(i, CenterAlignDelegate(tableView))
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
    # set a button to only be enabled when items in a given table or list are selected
    
    prior = getattr(button, "enableWhenSelectedWatch", None)
    if prior is not None:
        prior_model, prior_selection_model, on_reset, on_selection_changed = prior
        prior_model.modelAboutToBeReset.disconnect(on_reset)
        prior_selection_model.selectionChanged.disconnect(on_selection_changed)

    model = sourceView.model()
    selectionModel = sourceView.selectionModel()

    # reattach button to new table on modelAboutToBeReset, ex when we load new candidates
    def on_reset():
        button.setEnabled(False)
        onlyEnableWhenItemsSelected(button, sourceView)

    def on_selection_changed():
        button.setEnabled(bool(len(sourceView.selectedIndexes())))

    model.modelAboutToBeReset.connect(on_reset)
    selectionModel.selectionChanged.connect(on_selection_changed)
    button.enableWhenSelectedWatch = (model, selectionModel, on_reset, on_selection_changed)
    


def get_maestro_git_hash():
    import subprocess
    try:
        git_hash = subprocess.check_output(['git', 'rev-parse','--short', 'HEAD'],cwd=abspath(dirname(__file__))).decode('ascii').strip()
    except Exception as e:
        git_hash = None
    return git_hash