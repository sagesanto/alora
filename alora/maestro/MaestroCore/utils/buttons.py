import os.path

from PyQt6.QtCore import pyqtSignal, QAbstractListModel
from PyQt6.QtWidgets import QPushButton, QFileDialog, QListView, QAbstractItemView, QApplication
from MaestroCore.utils.utilityFunctions import onlyEnableWhenItemsSelected
from MaestroCore.utils.listModel import FlexibleListModel


def getSelectedFromTable(table, colIndex):
    selected = []
    indexes = table.selectionModel().selectedRows()
    model = table.model()
    for index in indexes:
        selected.append(model.data(model.index(index.row(), colIndex)))
    return selected

def getSelectedFromList(list:QListView):
    selected = []
    indexes = list.selectionModel().selectedRows()
    model = list.model()
    for index in indexes:
        if isinstance(model, FlexibleListModel):
            selected.append(model.data(index, role=-1))  # -1 gets the whole data, not just display
        else:
            selected.append(model.data(index))
    return selected

class ModelRemoveButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.callbacks = []
        self.clicked.connect(self.on_click)
        self.source = None
        
    def connectList(self, list: QListView):
        self.source = list
        onlyEnableWhenItemsSelected(self, list)
    
    def on_click(self):
        targets = getSelectedFromList(self.source)
        if self.source is not None:
            self.source.model().removeSelectedItems(self.source)
        for callback in self.callbacks:
            callback(targets)

    def add_callback(self, f):
        self.callbacks.append(f)


class AddSelectedButton(QPushButton):
    """!
    When pressed, this button will get a list of the selected items in a column (indicated by colIndex) of a QTableView sourceTable. Call f with this list, and add the returned results to a recipient QListModel
    This button will be disabled when no items are selected in the table, and become enabled when items are selected
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = self.recipient = self.index = self.function = None
        self.callbacks = []

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
        for callback in self.callbacks:
            callback(ls)

    def add_callback(self, f):
        self.callbacks.append(f)


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
