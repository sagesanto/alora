# Sage Santomenna 2023/2024

import sys, os, traceback
from os.path import join, abspath, dirname

sys.path.append(abspath(dirname(__file__)))
from scheduleLib.crash_reports import run_with_crash_writing, write_crash_report

MAESTRO_DIR = abspath(dirname(__file__))
def PATH_TO(fname:str): return join(MAESTRO_DIR,fname)

def LOGO_PATH(fname:str): return PATH_TO(join("MaestroCore","logosAndIcons",fname))

def exception_hook(exctype, value, tb):
    write_crash_report("MaestroApp", value, tb=tb)
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = exception_hook

def _main():
    import json
    import logging
    import pathlib
    import random
    import re
    import sys, os
    PYTHON_PATH = sys.executable
    import time
    from pathlib import Path
    import pandas as pd
    import pytz
    import astroplan

    from PyQt6 import QtGui, QtCore
    from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QTableWidget, \
        QTableWidgetItem as QTableItem, QLineEdit, QListView, QDockWidget, QComboBox, QPushButton, QMessageBox
    from PyQt6.QtCore import Qt, QItemSelectionModel, QDateTime, QSortFilterProxyModel
    import MaestroCore
    from MaestroCore.GUI.MainWindow import Ui_MainWindow
    from MaestroCore.addCandidateDialog import AddCandidateDialog
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from MaestroCore.utils.processes import ProcessModel, Process
    from MaestroCore.utils.tableModel import CandidateTableModel, FlexibleTableModel
    from MaestroCore.utils.listModel import FlexibleListModel, DateTimeRangeListModel
    from MaestroCore.utils.buttons import FileSelectionButton, ModelRemoveButton
    from datetime import datetime, timedelta
    from MaestroCore.utils.utilityFunctions import getSelectedFromTable, addLineContentsToList, loadDfInTable, onlyEnableWhenItemsSelected, comboValToIndex, datetimeToQDateTime, updateTableDisplay
    import astropy.units as u

    from scheduleLib.genUtils import inputToAngle

    # set up logger
    try:
        with open(os.path.abspath("logging.json"), 'r') as log_cfg:
            logging.config.dictConfig(json.load(log_cfg))
        logger = logging.getLogger(__name__)
        # set the out logfile to a new path
    except Exception as e:
        print(f"Can't load logging config ({e}). Using default config.")
        logger = logging.getLogger(__name__)
        file_handler = logging.FileHandler(os.path.abspath("main.log"),mode="a+")
        logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    logger.info("--------- Starting Maestro....----------------------------")


    defaultSettings = {}  # don't know how this should be stored/managed/updated - should submodules be able to register their own settings? probably. that's annoying

    debug = True
    # debug = os.getenv("MAESTRO_DEBUG", False)

    CoordConvertFmat = {
        0: 'decimal',
        1: 'colonSep',
        2: 'hmsdms'
    }

    STATUS_DONE  = LOGO_PATH("status.png")
    STATUS_BUSY  = LOGO_PATH("status-away.png") # not a mistake
    STATUS_ERROR = LOGO_PATH("status-busy.png") # not a mistake
    STATUS_IDLE  = LOGO_PATH("status-offline.png")

    def test_error():
        raise ValueError("Test error")

    class Settings:
        def __init__(self, settingsFilePath):
            self.path = settingsFilePath
            self.defaultPath = PATH_TO(join("MaestroCore","defaultSettings.txt"))
            self._settings = {}
            self._linkBacks = []  # (settingName, writeFunction) tuples

        def loadSettings(self):
            path = self.path
            if not os.path.exists(self.path):
                path = self.defaultPath
            with open(path, "r") as settingsFile:
                self._settings = json.load(settingsFile)

        def saveSettings(self):
            with open(self.path, "w+") as settingsFile:
                json.dump(self._settings, settingsFile)

        def query(self, key):
            """!
            Get the (value, type) pair associated with the setting with name key if such a pair exists, else None
            @param key:
            @return: tuple(value of setting,type of setting (string))
            """
            return self._settings[key] if key in self._settings.keys() else None

        def add(self, key, value, settingType):
            self._settings[key] = (value, settingType)
            self.saveSettings()

        def linkWatch(self, signal, key, valueSource, linkBack, datatype):
            """!
            Link function signal to setting key such that setting key is set to the value from valueSource (can be a function) when signal is triggered
            @param signal: Qt signal
            @param key: string, name of existing setting
            @param valueSource: function or value

            """
            signal.connect(lambda: self.set(key, valueSource, datatype))
            self._linkBacks.append((key, (linkBack, datatype)))

        def update(self):
            for key, (func, datatype) in self._linkBacks:
                func(datatype(self._settings[key][0]))

        def set(self, key, value, datatype):
            if callable(value):
                value = value()
            if key in self._settings.keys():
                self._settings[key][0] = datatype(value)
                self.saveSettings()
                return
            raise ValueError(f"No such setting {key}")

        def reset(self):
            self._settings = defaultSettings
            self.saveSettings()

        def asDict(self):
            return {k: v for k, [v, _] in self._settings.items()}


    class MainWindow(QMainWindow, Ui_MainWindow):
        def __init__(self, parent=None):
            super(MainWindow, self).__init__(parent)
            self.setWindowIcon(QtGui.QIcon(LOGO_PATH("windowIcon.ico")))  # ----
            self.setupUi(self)

            # self.blacklistLabel.setMinimumWidth(self.blacklistView.width())

            with open(PATH_TO("version.txt"), "r") as f:
                self.version = f.readline()

            #icons
            self.set_scheduler_icon(STATUS_IDLE)
            self.set_candidates_icon(STATUS_IDLE)
            self.set_database_icon(STATUS_IDLE)
            self.set_ephemeris_icon(STATUS_IDLE)
            self.set_processes_icon(QtGui.QIcon(LOGO_PATH("system-monitor")))
            self.toggleRejectButton.setIcon(QtGui.QIcon(LOGO_PATH("cross")))
            self.removeToggleButton.setIcon(QtGui.QIcon(LOGO_PATH("cross-circle-frame")))
            self.addCandidateButton.setIcon(QtGui.QIcon(LOGO_PATH("plus-circle-frame")))
            self.blacklistCandidatesButton.setIcon(QtGui.QIcon(LOGO_PATH("cross-white")))
            self.whitelistCandidatesButton.setIcon(QtGui.QIcon(LOGO_PATH("tick-white")))

            self.ephem_error_occurred = False
            self.sched_error_occurred = False


            # initialize custom things
            self.settings = Settings(PATH_TO(join("MaestroCore","settings.txt")))
            self.processModel = ProcessModel(statusBar=self.statusBar())
            self.ephemListModel = FlexibleListModel()
            self.blacklistModel = FlexibleListModel()
            self.whitelistModel = FlexibleListModel()
            self.excludeListModel = DateTimeRangeListModel()
            self.candidateTable = CandidateTableModel(pd.DataFrame())
            self.candidateView.setModel(self.candidateTable)
            self.dbRuntimeErrorTable = FlexibleTableModel(["Time", "Process", "Message"])
            self.dbRuntimeErrorView.setModel(self.dbRuntimeErrorTable)
            self.dbRuntimeErrorView.setWordWrap(True)
            self.dbRuntimeErrorView.setTextElideMode(Qt.TextElideMode.ElideNone)
            self.dbRuntimeErrorView.horizontalHeader().setStretchLastSection(True)
            self.dbRuntimeErrorTable.rowsInserted.connect(self.dbRuntimeErrorView.resizeRowsToContents)
            self.dbRuntimeErrorTable.rowsInserted.connect(self.dbRuntimeErrorView.resizeColumnsToContents)
            self.chooseSchedSavePath.setPrompt("Choose Save Path").isDirectoryDialog(True)
            self.databasePathChooseButton.setPrompt("Select Database File").setPattern("Database File (*.db)")
            self.ephemChooseSaveButton.setPrompt("Choose Save Path").isDirectoryDialog(True)

            # initialize misc things
            self.candidateDict = None
            self.indexOfIDColumn = None
            self.indexOfNameColumn = None
            self.sunriseUTC, self.sunsetUTC = None, None
            self.set_sunrise_sunset()
            self.candidates = None
            self.candidateDf = None
            self.candidatesByID = None
            self.ephemProcess = None
            self.databaseProcess = None
            self.dbOperatorProcess = None
            self.scheduleProcess = None
            self.scheduleDf = None
            self.dbConnection = None

            # call setup functions
            self.settings.loadSettings()
            if os.path.exists(self.settings.query("candidateDbPath")[0]):
                try:
                    self.dbConnection = CandidateDatabase(self.settings.query("candidateDbPath")[0], "Maestro")
                    self.set_database_icon(STATUS_DONE)
                except Exception as e:
                    logger.error(f"Unable to start database coordinator: {repr(e)}")
                    self.statusBar().showMessage(f"Unable to start database coordinator: {repr(e)}", 10000)
                    self.set_database_icon(STATUS_ERROR)
                else:
                    self.startDbUpdater()
                    self.startDbOperator()

            self.processesTreeView.setModel(self.processModel)
            self.ephemListView.setModel(self.ephemListModel)
            self.blacklistView.setModel(self.blacklistModel)
            self.whitelistView.setModel(self.whitelistModel)
            self.excludeListView.setModel(self.excludeListModel)

            self.setConnections()

            self.excludeStartEdit.setDateTime(self.scheduleStartTimeEdit.dateTime())
            self.excludeEndEdit.setDateTime(self.scheduleEndTimeEdit.dateTime())

            self.candidatesTabIndex = self.tabWidget.indexOf(self.candidatesTab)

        def set_sunrise_sunset(self):
            self.sunriseUTC, self.sunsetUTC = genUtils.get_sunrise_sunset()
            self.sunriseUTC, self.sunsetUTC = genUtils.roundToTenMinutes(self.sunriseUTC), genUtils.roundToTenMinutes(
                self.sunsetUTC)

        def reportError(self, process_name, msg):
            self.dbRuntimeErrorTable.addItem([datetime.now(pytz.utc).strftime("%m/%d %H:%M:%S"), process_name, str(msg)])

        def initProcess(self, name, triggers=None, description=None, *args, **kwargs):
            triggers = triggers or []
            p = Process(name, triggers, description=description, *args, **kwargs)
            self.processModel.add(p)
            p.errorSignal.connect(lambda msg: self.reportError(name, msg))
            return p

        def setConnections(self):
            self.refreshCandButton.clicked.connect(lambda: self.getCandidates().displayCandidates())

            self.candidateEphemerisButton.clicked.connect(self.useCandidateTableEphemeris)
            self.blacklistCandidatesButton.clicked.connect(self.blacklistSelectedCandidates)
            self.whitelistCandidatesButton.clicked.connect(self.whitelistSelectedCandidates)

            self.addCandidateButton.clicked.connect(self.addCandidate)

            onlyEnableWhenItemsSelected(self.whitelistCandidatesButton, self.candidateView)
            onlyEnableWhenItemsSelected(self.blacklistCandidatesButton, self.candidateView)
            onlyEnableWhenItemsSelected(self.candidateEphemerisButton, self.candidateView)
            onlyEnableWhenItemsSelected(self.toggleRejectButton, self.candidateView)
            onlyEnableWhenItemsSelected(self.removeToggleButton, self.candidateView)

            self.toggleRejectButton.clicked.connect(self.toggleRejectSelectedCandidates)
            self.removeToggleButton.clicked.connect(self.toggleRemoveSelectedCandidates)
            self.getEphemsButton.clicked.connect(self.getEphemeris)
            # self.ephemRemoveSelected.clicked.connect(
            #     lambda: self.ephemListModel.removeSelectedItems(self.ephemListView))
            self.ephemNameEntry.returnPressed.connect(
                lambda: addLineContentsToList(self.ephemNameEntry, self.ephemListModel))

            self.whitelistAddButton.clicked.connect(
                lambda: addLineContentsToList(self.whitelistLineEdit, self.whitelistModel))
            self.blacklistAddButton.clicked.connect(
                lambda: addLineContentsToList(self.blacklistLineEdit, self.blacklistModel))
            self.whitelistLineEdit.returnPressed.connect(
                lambda: addLineContentsToList(self.whitelistLineEdit, self.whitelistModel))
            self.blacklistLineEdit.returnPressed.connect(
                lambda: addLineContentsToList(self.blacklistLineEdit, self.blacklistModel))

            self.removeWhitelistedButton.connectList(self.whitelistView)
            self.removeExcludeRangeButton.connectList(self.excludeListView)
            self.removeBlacklistedButton.connectList(self.blacklistView)
            self.ephemRemoveSelected.connectList(self.ephemListView)

            self.addToExcludeButton.clicked.connect(lambda: self.addToExcludeRange("MM/dd/yyyy hh:mm"))

            self.processesTreeView.selectionModel().selectionChanged.connect(self.toggleProcessButtons)
            self.processPauseButton.clicked.connect(self.pauseProcess)
            self.processResumeButton.clicked.connect(self.resumeProcess)
            self.processAbortButton.clicked.connect(self.abortProcess)
            self.processModel.rowsInserted.connect(lambda parent: self.processesTreeView.expandRecursively(parent))
            self.requestDbRestartButton.clicked.connect(self.startDbUpdater)
            self.genScheduleButton.clicked.connect(self.runScheduler)
            self.pingButton.clicked.connect(self.pingProcess)
            self.requestDbCycleButton.clicked.connect(self.requestDbCycle)
            self.hardModeButton.clicked.connect(self.hardMode)
            self.allCandidatesCheckbox.clicked.connect(lambda: self.getCandidates().displayCandidates())
            self.scheduleAutoTimeSetCheckbox.stateChanged.connect(lambda state: self.autoSetSchedulerTimes(state))
            self.scheduleAutoTimeSetCheckbox.stateChanged.connect(
                lambda state: self.scheduleStartTimeEdit.setDisabled(state))  # disable the time entry when auto is checked
            self.scheduleAutoTimeSetCheckbox.stateChanged.connect(lambda state: self.scheduleEndTimeEdit.setDisabled(state))
            # self.scheduleEndTimeEdit.dateTimeChanged.connect(
            #     lambda Qdt: self.scheduleStartTimeEdit.setMaximumDateTime(Qdt))  # so start is always < end

            # # scheduler exclude time range limits
            # # exclude start must be before exclude end:
            # self.excludeEndEdit.dateTimeChanged.connect(lambda Qdt: self.excludeStartEdit.setMaximumDateTime(Qdt))

            # misc
            self.debugInfoButton.clicked.connect(self.displayInfo)
            self.tabWidget.currentChanged.connect(self.updateTables)

            # coord converter
            self.coordConvertButton.clicked.connect(self.doCoordConversion)
            self.coordConvertRAInput.returnPressed.connect(self.doCoordConversion)
            self.coordConvertDecInput.returnPressed.connect(self.doCoordConversion)
            self.convertInsertButton.clicked.connect(self.swapCoordTexts)
            self.coordConvertResetButton.clicked.connect(self.resetCoordConverter)


            # attach settings to widgets (and vice versa)
            self.settings.linkWatch(self.intervalComboBox.currentTextChanged, "ephemInterval",
                                    lambda: comboValToIndex(self.intervalComboBox, self.intervalComboBox.currentText),
                                    self.intervalComboBox.setCurrentIndex, int)
            self.settings.linkWatch(self.obsCodeLineEdit.textChanged, "ephemsObsCode", self.obsCodeLineEdit.text,
                                    self.obsCodeLineEdit.setText, str)
            self.settings.linkWatch(self.ephemStartDelayHrsSpinBox.valueChanged, "ephemStartDelayHrs",
                                    self.ephemStartDelayHrsSpinBox.value, self.ephemStartDelayHrsSpinBox.setValue, int)
            self.settings.linkWatch(self.formatComboBox.currentTextChanged, "ephemFormat",
                                    lambda: comboValToIndex(self.formatComboBox, self.formatComboBox.currentText),
                                    self.formatComboBox.setCurrentIndex, int)
            self.settings.linkWatch(self.minutesBetweenCyclesSpinBox.valueChanged, "databaseWaitTimeMinutes",
                                    self.minutesBetweenCyclesSpinBox.value, self.minutesBetweenCyclesSpinBox.setValue, int)
            self.settings.linkWatch(self.scheduleStartTimeEdit.dateTimeChanged, "scheduleStartTimeSecs",
                                    lambda: self.scheduleStartTimeEdit.dateTime().toSecsSinceEpoch(),
                                    lambda secs: self.scheduleStartTimeEdit.setDateTime(QDateTime.fromSecsSinceEpoch(secs)),
                                    int)
            self.settings.linkWatch(self.scheduleEndTimeEdit.dateTimeChanged, "scheduleEndTimeSecs",
                                    lambda: self.scheduleEndTimeEdit.dateTime().toSecsSinceEpoch(),
                                    lambda secs: self.scheduleEndTimeEdit.setDateTime(QDateTime.fromSecsSinceEpoch(secs)),
                                    int)

            self.settings.linkWatch(self.chooseSchedSavePath.chosen, "scheduleSaveDir", self.chooseSchedSavePath.getPath,
                                    self.chooseSchedSavePath.updateFilePath, str)
            self.settings.linkWatch(self.ephemChooseSaveButton.chosen, "ephemsSavePath", self.ephemChooseSaveButton.getPath,
                                    self.ephemChooseSaveButton.updateFilePath, str)
            self.settings.linkWatch(self.databasePathChooseButton.chosen, "candidateDbPath",
                                    self.databasePathChooseButton.getPath,
                                    self.databasePathChooseButton.updateFilePath, str)
            self.settings.linkWatch(self.allCandidatesCheckbox.stateChanged, "showAllCandidates",
                                    self.allCandidatesCheckbox.isChecked, self.allCandidatesCheckbox.setChecked, bool)
            self.settings.linkWatch(self.schedulerSaveEphemsBox.stateChanged, "schedulerSaveEphems",
                                    self.schedulerSaveEphemsBox.isChecked, self.schedulerSaveEphemsBox.setChecked, bool)
            self.settings.linkWatch(self.scheduleAutoTimeSetCheckbox.stateChanged, "autoSetScheduleTimes",
                                    self.scheduleAutoTimeSetCheckbox.isChecked, self.scheduleAutoTimeSetCheckbox.setChecked,
                                    bool)
            self.settings.linkWatch(self.numRunsSpinbox.valueChanged, "schedulerRuns",
                                    self.numRunsSpinbox.value, self.numRunsSpinbox.setValue,
                                    int)
            self.settings.linkWatch(self.tempSpinbox.valueChanged, "temperature",
                                    self.tempSpinbox.value, self.tempSpinbox.setValue,
                                    int)
            self.settings.update()

        def closeEvent(self, a0: QtGui.QCloseEvent):
            logger.info("----------- Closing Maestro -----------------")
            self.processModel.terminateAllProcesses()
            super().closeEvent(a0)

        def set_scheduler_icon(self,img_path):
            self.tabWidget.setTabIcon(0,QtGui.QIcon(img_path))

        def set_candidates_icon(self,img_path):
            self.tabWidget.setTabIcon(1,QtGui.QIcon(img_path))
        
        def set_database_icon(self,img_path):
            self.tabWidget.setTabIcon(2,QtGui.QIcon(img_path))
        
        def set_ephemeris_icon(self,img_path):
            self.tabWidget.setTabIcon(3,QtGui.QIcon(img_path))
        
        def set_processes_icon(self,img_path):
            self.tabWidget.setTabIcon(4,QtGui.QIcon(img_path))


        def updateTables(self, index):
            # tables = {self.candidatesTabIndex: self.candidateView}
            tables = {}
            if index in tables.keys():
                updateTableDisplay(tables[index])

        # start the database update process
        def startDbUpdater(self):
            if not os.path.exists(self.settings.query("candidateDbPath")[0]):
                self.statusBar().showMessage(
                    "To run database coordination, choose a database in the Database tab, then press 'Request Restart'",
                    10000)
                return
            if self.databaseProcess is not None:
                if self.databaseProcess.isActive:  # run a restart
                    if debug:
                        logger.info("Restarting database coordinator.")
                    self.databaseProcess.abort()
                    time.sleep(1) # ew
                    self.databaseProcess = None
                    self.startDbUpdater()
                    return
            self.databaseProcess = self.initProcess("DbUpdater", ["DbUpdater: Status:", "DbUpdater: Result:", "DbUpdater: Error:", "DbUpdater: Finished:"], description="The DbUpdater process is responsible for periodically updating the target database, adding new targets, and removing old ones.")
            if debug:
                self.databaseProcess.msg.connect(lambda message: print(message))
            self.databaseProcess.triggered.connect(self.dbStatusChecker)
            self.databaseProcess.succeeded.connect(self.getCandidates)
            self.databaseProcess.succeeded.connect(lambda: self.set_candidates_icon(STATUS_DONE))
            # TODO: make this work     
            self.databaseProcess.errorSignal.connect(lambda: self.set_candidates_icon(STATUS_ERROR))
            self.databaseProcess.start(PYTHON_PATH, [PATH_TO(join('MaestroCore','database.py')), json.dumps(self.settings.asDict())])
            self.set_candidates_icon(STATUS_BUSY)


        def toggleRejectSelectedCandidates(self):
            if self.dbOperatorProcess is None or not self.dbOperatorProcess.isActive:
                logger.error("DbOps program is not active! This is bad!")
                return
            candidates = [self.candidatesByID[int(i)] for i in
                        getSelectedFromTable(self.candidateView, self.indexOfIDColumn)]
            rejectIDs = [c.ID for c in candidates if not c.hasField("RejectedReason")]
            unrejectIDs = [c.ID for c in candidates if c.hasField("RejectedReason")]
            if rejectIDs:
                jobDict = {"jobType": "reject", "arguments": [rejectIDs], "retries": 3}
                jobStr = f"DbOps: NewJob: {json.dumps(jobDict)} \n"
                logger.debug(f"JobStr: {jobStr}")
                self.dbOperatorProcess.write(jobStr)
            if unrejectIDs:
                jobDict = {"jobType": "unreject", "arguments": [unrejectIDs], "retries": 3}
                jobStr = f"DbOps: NewJob: {json.dumps(jobDict)} \n"
                logger.debug(f"JobStr: {jobStr}")
                self.dbOperatorProcess.write(jobStr)
            else:
                logger.info("No IDs to reject.")

        def toggleRemoveSelectedCandidates(self):
            if self.dbOperatorProcess is None or not self.dbOperatorProcess.isActive:
                logger.error("DbOps program is not active! This is bad!")
                return
            candidates = [self.candidatesByID[int(i)] for i in
                        getSelectedFromTable(self.candidateView, self.indexOfIDColumn)]
            removeIDs = [c.ID for c in candidates if not c.hasField("RemovedReason")]
            unremoveIDs = [c.ID for c in candidates if c.hasField("RemovedReason")]
            if removeIDs:
                jobDict = {"jobType": "remove", "arguments": [removeIDs], "retries": 3}
                jobStr = f"DbOps: NewJob: {json.dumps(jobDict)} \n"
                logger.debug(f"JobStr: {jobStr}")
                self.dbOperatorProcess.write(jobStr)
            if unremoveIDs:
                jobDict = {"jobType": "unremove", "arguments": [unremoveIDs], "retries": 3}
                jobStr = f"DbOps: NewJob: {json.dumps(jobDict)} \n"
                logger.debug(f"JobStr: {jobStr}")
                self.dbOperatorProcess.write(jobStr)
            else:
                logger.debug(f"JobStr: {jobStr}")

        def setSchedError(self,val):
            self.sched_error_occurred = val

        def runScheduler(self):
            self.genScheduleButton.setDisabled(True)
            self.genScheduleButton.setText("Generating")

            if self.scheduleAutoTimeSetCheckbox.isChecked():
                self.autoSetSchedulerTimes()
            self.scheduleProcess = self.initProcess("Scheduler", ["Status:Schedule visualized."], "The Scheduler process is responsible for generating a schedule of observations based on the current target database and user settings.")
            blacklistedCandidateDesigs = ",".join(self.getEntriesAsStrings(self.blacklistModel._data))
            whitelistedCandidateDesigs = ",".join(self.getEntriesAsStrings(self.whitelistModel._data))
            excludedTimeRanges = ",".join(
                [(str(dat[0].toSecsSinceEpoch()) + "/" + str(dat[1].toSecsSinceEpoch())) for dat in
                self.excludeListModel._data])

            if debug:
                self.scheduleProcess.msg.connect(lambda msg: print("Scheduler: ", msg))
            self.scheduleProcess.start(PYTHON_PATH, [PATH_TO("scheduler.py"), json.dumps(self.settings.asDict()),
                                                str(blacklistedCandidateDesigs), str(whitelistedCandidateDesigs),
                                                excludedTimeRanges])
            self.set_scheduler_icon(STATUS_BUSY)
            self.sched_error_occurred = False
            self.scheduleProcess.ended.connect(lambda: self.genScheduleButton.setDisabled(False))
            self.scheduleProcess.ended.connect(lambda: self.genScheduleButton.setText("Generate Schedule"))
            self.scheduleProcess.errorOccurred.connect(lambda: self.setSchedError(True))
            self.scheduleProcess.errorOccurred.connect(lambda: self.set_scheduler_icon(STATUS_ERROR))
            self.scheduleProcess.ended.connect(lambda: self.set_scheduler_icon(STATUS_DONE if not self.sched_error_occurred else STATUS_ERROR))
            self.scheduleProcess.triggered.connect(self.displaySchedule)
            self.scheduleProcess.triggered.connect(lambda: self.genScheduleButton.setText("Writing text file"))
            # self.scheduleProcess.ended.connect(self.displaySchedule)

        def addToExcludeRange(self, timeDisplayFormat):
            if self.excludeStartEdit.dateTime() < self.excludeEndEdit.dateTime():
                self.excludeListModel.addItem(self.excludeStartEdit.dateTime(), self.excludeEndEdit.dateTime(),
                                            timeDisplayFormat)
            else:
                self.statusbar.showMessage("Start time cannot be after end time.", 5000)

        def hardMode(self):
            buttons = [attr for attr in self.__dict__.values() if
                    isinstance(attr, QPushButton) and not isinstance(attr, FileSelectionButton)]
            displayTexts = [button.text() for button in buttons]
            for b in buttons:
                while True:
                    t = random.choice(displayTexts)
                    if t != b.text() or len(displayTexts) == 1:
                        b.setText(t)
                        displayTexts.remove(t)
                        break

        def displaySchedule(self):
            basepath = self.settings.query("scheduleSaveDir")[0] + os.sep + "schedule"
            imgPath = basepath + ".png"
            csvPath = basepath + ".csv"

            if os.path.isfile(csvPath):
                self.scheduleDf = pd.read_csv(csvPath).drop(labels='Tags', axis="columns")
                # self.scheduleDf
                loadDfInTable(self.scheduleDf, self.scheduleTable)
                self.schedTabWidget.setCurrentWidget(self.schedViewTab)
                self.scheduleTable.resizeColumnsToContents()
                self.scheduleTable.resizeRowsToContents()
                self.scheduleTable.update()
            if os.path.isfile(imgPath):
                imgProfile = QtGui.QImage(imgPath)  # QImage object
                imgProfile = imgProfile.scaled(self.scheduleImageDisplay.width(), self.scheduleImageDisplay.height(),
                                            aspectRatioMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                            transformMode=QtCore.Qt.TransformationMode.SmoothTransformation)
                self.scheduleImageDisplay.setPixmap(QtGui.QPixmap.fromImage(imgProfile))
                self.schedTabWidget.setCurrentWidget(self.schedViewTab)
            else:
                self.statusbar.showMessage(
                    "Can't find saved scheduler image. If and only if it reports that it ran correctly, please report this.")
                logger.error("Can't find saved scheduler image. *If and only if* the scheduler reports that it ran correctly, please report this.")

        def autoSetSchedulerTimes(self, run=True):
            if run:
                self.set_sunrise_sunset()
                start = datetimeToQDateTime(max(self.sunsetUTC, datetime.now(pytz.utc)))
                end = datetimeToQDateTime(self.sunriseUTC-timedelta(hours=1))

                self.scheduleStartTimeEdit.setDateTime(start)
                self.scheduleEndTimeEdit.setDateTime(end)

        def blacklistSelectedCandidates(self):
            candidates = [self.candidateDict[d] for d in getSelectedFromTable(self.candidateView, self.indexOfNameColumn)]
            for candidate in candidates:
                if candidate not in self.blacklistModel._data:
                    self.whitelistModel.removeItem(candidate)
                    self.blacklistModel.addItem(candidate)

        def whitelistSelectedCandidates(self):
            candidates = [self.candidateDict[d] for d in getSelectedFromTable(self.candidateView, self.indexOfNameColumn)]
            for candidate in candidates:
                if candidate not in self.whitelistModel._data:
                    self.blacklistModel.removeItem(candidate)
                    self.whitelistModel.addItem(candidate)

        def resetCandidateTable(self):
            self.candidateTable = CandidateTableModel(pd.DataFrame())
            self.candidateView.setModel(self.candidateTable)

        def requestDbCycle(self):
            logger.debug("Requesting")
            self.databaseProcess.write("DbUpdater: Cycle\n")

        def dbStatusChecker(self, phrase, msg):
            if phrase == "DbUpdater: Result:":
                clean = msg.replace("DbUpdater: Result:", "")
                self.statusBar().showMessage(clean, 15000)
                self.databaseProcess.log.append(clean)
            if phrase == "DbUpdater: Error:":
                logger.error(f"DB ERROR IN DB STATUS CHECKER: {msg}")
                self.statusBar().showMessage(f"DbUpdater error: {msg, 10000}")
                self.databaseProcess.errorSignal.emit(msg)
            # db updater stays alive after finishing so we need to manually check if it's done and emit finished if so
            if phrase == "DbUpdater: Finished:": 
                if debug:
                    logger.info(f"Db finished: {msg}")
                self.databaseProcess.ended.emit(msg.replace("DbUpdater: Finished:", ""))

        def toggleProcessButtons(self):
            self.processesTreeView.selectionModel().blockSignals(True)
            for button in [self.processAbortButton, self.processPauseButton, self.processResumeButton, self.pingButton]:
                button.setDisabled(not bool(len(self.processesTreeView.selectedIndexes())))
            processItems = []
            for index in self.processesTreeView.selectedIndexes():
                if self.processModel.data(index.parent(), Qt.ItemDataRole.DisplayRole) is not None:
                    if index.parent() not in processItems:
                        processItems.append(index.parent())
                    continue
                processItems.append(index)
            self.processesTreeView.clearSelection()
            for index in processItems:
                self.processesTreeView.selectionModel().select(index,
                                                            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            self.processesTreeView.selectionModel().blockSignals(False)

        def addCandidate(self):
            dlg = AddCandidateDialog(self)
            if dlg.exec():
                logger.info("Adding user candidates!")
                if os.path.exists(AddCandidateDialog.tempSaveFile()):
                    jobDict = {"jobType": "csvAdd", "arguments": [AddCandidateDialog.tempSaveFile()], "retries": 0}
                    jobStr = f"DbOps: NewJob: {json.dumps(jobDict)} \n"
                    logger.debug(f"Add candidate JobStr: {jobStr}")
                    self.dbOperatorProcess.write(jobStr)
                else:
                    logger.error("Couldn't find or couldn't open candidate csv!")
            else:
                logger.warn("No candidates to add.")

        def pauseProcess(self):
            if "win" not in sys.platform:
                for index in self.processesTreeView.selectedIndexes():
                    index.internalPointer().tags["Process"].pause()
                return
            self.statusBar().showMessage("Not supported on Windows.", 5000)

        def resumeProcess(self):
            if "win" not in sys.platform:
                for index in self.processesTreeView.selectedIndexes():
                    index.internalPointer().tags["Process"].resume()
                return
            self.statusBar().showMessage("Not supported on Windows.", 5000)

        def abortProcess(self):
            for index in self.processesTreeView.selectedIndexes():
                index.internalPointer().tags["Process"].abort()

        def pingProcess(self):
            for index in self.processesTreeView.selectedIndexes():
                index.internalPointer().tags["Process"].ping()

        def useCandidateTableEphemeris(self):
            """!
            Add the desigs of all selected candidates in the candidate table to the ephems list, then set the ephem tab as the active tab
            """
            candidates = [self.candidateDict[d] for d in getSelectedFromTable(self.candidateView, self.indexOfNameColumn)]
            for candidate in candidates:
                self.ephemListModel.addItem(candidate)
            self.tabWidget.setCurrentWidget(self.ephemsTab)

        def getCandidates(self):
            if self.settings.query("showAllCandidates")[0]:
                self.candidates = self.dbConnection.table_query("Candidates", "*", "1=1", [], returnAsCandidates=True)
            else:
                logger.info("Showing select")
                try:
                    self.candidates = self.dbConnection.candidatesForTimeRange(self.sunsetUTC, self.sunriseUTC, 0.01)
                except AttributeError as e:
                    logger.error(f"Couldn't get candidates: {repr(e)} (probably no database)")
                    self.statusBar().showMessage("ERROR: invalid database path. To show targets, choose a database under Database > Control, then press 'Request Restart'", 10000)
                    return self
            if not self.candidates:
                self.resetCandidateTable()
                if debug:
                    logger.warning("No candidates")
                return self
            priorityCandidates = [c for c in self.candidates if c.CandidateType == "MPC NEO" and c.isValid() and (
                    c.CandidateName.startswith("ST") or c.CandidateName.startswith("LS"))]
            for candidate in priorityCandidates:
                if candidate.CandidateName not in [c.CandidateName for c in
                                                self.whitelistModel._data] and candidate.CandidateName not in [
                    c.CandidateName for c in self.blacklistModel._data]:
                    self.blacklistModel.removeItem(candidate)
                    self.whitelistModel.addItem(candidate)
            self.candidateDf = Candidate.candidatesToDf(self.candidates)
            self.candidatesByID = {c.ID: c for c in self.candidates}
            self.candidateDict = {c.CandidateName: c for c in self.candidates}
            self.indexOfIDColumn = self.candidateDf.columns.get_loc("ID")
            self.indexOfNameColumn = self.candidateDf.columns.get_loc("CandidateName")

            return self

        def getEntriesAsCandidates(self, entries, handleErrorFunc=None):
            # strings is a list of strings that can be resolved in this way
            candidates = []
            for i in entries:
                try:
                    if isinstance(i, Candidate):
                        candidates.append(i)
                        continue
                    candidates.append(self.candidateDict[i])
                except KeyError:
                    # TODO: Handle this
                    if handleErrorFunc:
                        handleErrorFunc(f"Couldn't find candidate for entry {i}")
            return candidates

        def doCoordConversion(self):
            if self.coordConvertRAInput.text():
                self.convertRAOut()
            else:
                self.raOutLine.clear()
            if self.coordConvertDecInput.text():
                self.convertDecOut()
            else:
                self.decOutLine.clear()

        def swapCoordTexts(self):
            raOut = self.raOutLine.text()
            if raOut and raOut != "PBCAK":
                self.coordConvertRAInput.setText(raOut)
            decOut = self.decOutLine.text()
            if decOut and decOut != "PBCAK":
                self.coordConvertDecInput.setText(decOut)

        def resetCoordConverter(self):
            for line in (self.raOutLine, self.decOutLine, self.coordConvertRAInput, self.coordConvertDecInput):
                line.clear()
            self.coordOutFormatBox.setCurrentIndex(0)

        def convertRAOut(self):
            text = self.coordConvertRAInput.text()
            outf = self.coordOutFormatBox.currentIndex()
            try:
                angle = inputToAngle(text, hms=True)
                if outf:
                    self.raOutLine.setText(genUtils.angleToHMSString(angle, format=CoordConvertFmat[outf]))
                    return
                self.raOutLine.setText(str(round(angle.degree, 4)))
            except Exception as e:
                self.raOutLine.setText("PBCAK")
                logger.error(f"Couldn't convert angle: \'{repr(e)}\'")

        def convertDecOut(self):
            text = self.coordConvertDecInput.text()
            outf = self.coordOutFormatBox.currentIndex()
            try:
                angle = inputToAngle(text, hms=False)
                if outf:
                    self.decOutLine.setText(genUtils.angleToDMSString(angle, format=CoordConvertFmat[outf]))
                    return
                self.decOutLine.setText(str(round(angle.degree, 4)))
            except Exception as e:
                self.decOutLine.setText("PBCAK")
                logger.error(f"Couldn't convert angle: \'{repr(e)}\'")

        def getEntriesAsStrings(self, entries, handleErrorFunc=None):
            candidates = []
            for i in entries:
                try:
                    if isinstance(i, str):
                        candidates.append(i)
                        continue
                    candidates.append(i.CandidateName)
                except KeyError:
                    # TODO: Handle this
                    if handleErrorFunc:
                        handleErrorFunc(f"Couldn't find candidate for entry {i}")
            return candidates

        def displayCandidates(self):
            """!
            Load the stored candidates into the table. Fetches candidates if has None
            @return:
            """
            if self.candidates is None and os.path.exists(self.settings.query("candidateDbPath")[0]):
                self.getCandidates()
            if self.candidates:
                oldModel = self.candidateTable
                self.candidateTable = CandidateTableModel(self.candidateDf)
                self.candidateView.setModel(self.candidateTable)
                oldModel.beginResetModel()
                oldModel.endResetModel()
                updateTableDisplay(self.candidateView)
            return self

        def set_ephem_error_occurred(self,val):
            self.ephem_error_occurred = val

        def getEphemeris(self):
            if self.ephemProcess is not None:
                if self.ephemProcess.isActive:
                    if debug:
                        logger.info("Already getting ephems.")
                    return
                if debug:
                    logger.debug("EphemProcess is not None and not active")
                self.ephemProcess.reset()

            candidatesToRequest = self.getEntriesAsCandidates(self.ephemListModel._data)
            if len(candidatesToRequest) == 0:
                if debug:
                    logger.info("No ephems to get.")
                return

            self.getEphemsButton.setDisabled(True)
            self.ephem_error_occurred = False
            self.ephemProcess = self.initProcess("Ephemerides", description="The Ephemerides process is responsible for fetching ephemerides for the selected targets.")
            # if debug:
            #     # self.ephemProcess.ended.connect(lambda: print(self.processModel.rootItem.__dict__))
                # self.ephemProcess.msg.connect(lambda msg: print(msg))
            self.ephemProcess.errorOccurred.connect(lambda: self.set_ephem_error_occurred(True))
            self.ephemProcess.ended.connect(lambda: self.getEphemsButton.setDisabled(False))
            self.ephemProcess.ended.connect(lambda: self.set_ephemeris_icon(STATUS_DONE if not self.ephem_error_occurred else STATUS_ERROR))
            targetDict = {
                candidate.CandidateType: [c.CandidateName for c in candidatesToRequest if
                                        c.CandidateType == candidate.CandidateType] for
                candidate in candidatesToRequest}
            if debug:
                logger.debug(targetDict)
            self.ephemProcess.start(PYTHON_PATH, [PATH_TO(join('MaestroCore','ephemerides.py')), json.dumps(targetDict),
                                            json.dumps(self.settings.asDict())])
            self.set_ephemeris_icon(STATUS_BUSY)
            # launch waiting window
            # gather the candidates indicated
            # read the specified ephem parameters
            # sort candidates by config
            # fire off (asynchronously) to their respective configs to get ephems, en masse
            # collect the results (lists of strings, each list being its own file, each string being its own line)
            # launch save window
            # save the files to the indicated location

        def displayInfo(self):
            infoText = '\n'.join([
                "Sage Santomenna 2023, 2024",
                "Some icons by Yusuke Kamiyamane, CC Attribution 3.0 License.",
                "Version: " + self.version,
                "Working directory: " + os.path.join(os.path.dirname(__file__)),
                f"Package install: {pathlib.Path(pd.__file__).parent.parent.absolute()}"
            ])

            infoWindow = QMessageBox(self)
            error_button = infoWindow.addButton("Cause Error", QMessageBox.ButtonRole.ActionRole)
            error_button.clicked.connect(test_error)
            infoWindow.setWindowTitle("Debug Info")
            infoWindow.setText(infoText)
            infoWindow.exec()

        def startDbOperator(self):
            if not os.path.exists(self.settings.query("candidateDbPath")[0]):
                self.statusBar().showMessage(
                    "To run database operations, choose a database under Database > Control, then press 'Request Restart'",
                    10000)
                return
            if self.dbOperatorProcess is not None and self.dbOperatorProcess.isActive:
                logger.info("Restarting database operator.")
                self.dbOperatorProcess.abort()
                time.sleep(0.5)  # cringe
                self.dbOperatorProcess = None
                self.startDbOperator()
                return
            self.dbOperatorProcess = self.initProcess("DbOps", ["DbOps: Status:", "DbOps: Result:"], "The DbOps process is responsible for handling user-initiated database operations (such as adding, removing, and rejecting targets).")
            # if debug:
            #     self.dbOperatorProcess.msg.connect(lambda message: print(message))
            # self.dbOperatorProcess.triggered.connect(self.dbStatusChecker)
            self.dbOperatorProcess.ended.connect(self.getCandidates)
            self.dbOperatorProcess.start(PYTHON_PATH,
                                        [PATH_TO(join('MaestroCore','databaseOperations.py')), json.dumps(self.settings.asDict())])

    app = QApplication([])

    window = MainWindow()
    window.displayCandidates()
    window.show()

    # start event loop
    app.exec()

def main():
    run_with_crash_writing("MaestroApp", _main)

if __name__ == "__main__":
    main()