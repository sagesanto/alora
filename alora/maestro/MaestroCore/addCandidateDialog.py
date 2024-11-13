import re

import MaestroCore.utils.tableModel
from MaestroCore.GUI.raw_add_candidate_dialog import Ui_Dialog

import sys
from MaestroCore.utils.utilityFunctions import *
from MaestroCore.utils.tableModel import CandidateTableModel
from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow, QPushButton
from scheduleLib.genUtils import inputToAngle


class AddCandidateDialog(QDialog, Ui_Dialog):
    @staticmethod
    def tempSaveFile():
        return "files/temp_addcandidates.csv"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.candidateTable = CandidateTableModel(pd.DataFrame())
        self.ui.candidatePreviewTableView.setModel(self.candidateTable)
        self.setConnections()

    def setConnections(self):
        self.ui.buttonBox.accepted.connect(lambda: self.candidateTable._data.to_csv(self.tempSaveFile(),index=None))  # save the candidates to be added
        self.ui.chooseCSVButton.chosen.connect(lambda path: self.loadCSV(path))

    def loadCSV(self, filepath):
        try:
            df = pd.read_csv(filepath)
            oldModel = self.candidateTable
            self.candidateTable = CandidateTableModel(df)
            self.ui.candidatePreviewTableView.setModel(self.candidateTable)
            # this will try to trigger the remove button to connect to the new table model:
            oldModel.beginResetModel()
            oldModel.endResetModel()
            self.ui.removeAddedCandidateButton.connectList(self.ui.candidatePreviewTableView)
            updateTableDisplay(self.ui.candidatePreviewTableView)
        except:
            raise
            return
