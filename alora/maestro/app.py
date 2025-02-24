# Sage Santomenna 2023-2025

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
    import sys, os, traceback
    PYTHON_PATH = sys.executable
    import time
    from pathlib import Path
    import pandas as pd
    import numpy as np
    import pytz
    import astroplan

    from PyQt6 import QtGui, QtCore
    from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QTableWidget, \
        QTableWidgetItem as QTableItem, QLineEdit, QListView, QDockWidget, QComboBox, \
              QPushButton, QMessageBox, QHBoxLayout, QVBoxLayout, QCheckBox, QLabel, QListWidgetItem, \
                QSizePolicy, QSpinBox, QSpacerItem, QTextEdit, QDoubleSpinBox, QScrollArea
    from PyQt6.QtCore import Qt, QItemSelectionModel, QDateTime, QSortFilterProxyModel, QTimer
    import PyQt6.QtWidgets as QtWidgets
    import MaestroCore
    from MaestroCore.GUI.MainWindow import Ui_MainWindow
    from MaestroCore.addCandidateDialog import AddCandidateDialog
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase, validFields
    from MaestroCore.utils.processes import ProcessModel, Process
    from MaestroCore.utils.tableModel import CandidateTableModel, FlexibleTableModel
    from MaestroCore.utils.listModel import FlexibleListModel, DateTimeRangeListModel, ModuleListEntry
    from MaestroCore.utils.buttons import FileSelectionButton, ModelRemoveButton
    from MaestroCore.utils.noscroll import NoScrollQComboBox, NoScrollQSpinBox, NoScrollQDoubleSpinBox
    from MaestroCore.utils.windows import ScrollMessageBox
    from datetime import datetime, timedelta
    from MaestroCore.utils.utilityFunctions import getSelectedFromTable, addLineContentsToList, loadDfInTable, onlyEnableWhenItemsSelected, comboValToIndex, datetimeToQDateTime, updateTableDisplay
    import astropy.units as u

    from scheduleLib.genUtils import inputToAngle, Config
    from scheduleLib.module_loader import ModuleManager

    # VAL_DISPLAY_TYPES = {
    #     "float":QLineEdit,
    #     "int":QSpinBox,
    #     "str":QLineEdit,
    #     "bool":QCheckBox,
    #     "longstr":QTextEdit
    # }

    # set up logger
    try:
        with open(PATH_TO("logging.json"), 'r') as log_cfg:
            logging.config.dictConfig(json.load(log_cfg))
        logger = logging.getLogger(__name__)
        # set the out logfile to a new path
    except Exception as e:
        print(f"Can't load logging config ({e}). Using default config.")
        logger = logging.getLogger(__name__)
        file_handler = logging.FileHandler(os.path.abspath("main.log"),mode="a+")
        logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)

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
    
    def clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                clear_layout(item.layout())

    def copy_button(text_to_copy):
        def copy_to_clipboard():
            clipboard = QApplication.clipboard()
            clipboard.setText(text_to_copy)

        button = QPushButton()
        button.setIcon(QtGui.QIcon(LOGO_PATH("clipboard--plus.png")))
        button.clicked.connect(copy_to_clipboard)
        button.clicked.connect(lambda: button.setIcon(QtGui.QIcon(LOGO_PATH("clipboard-task.png"))))
        button.clicked.connect(lambda: QTimer.singleShot(1000, lambda: button.setIcon(QtGui.QIcon(LOGO_PATH("clipboard--plus.png")))))
        return button
    
    def log_button_press(e):
        logger.debug(f"Button Pressed: {e}")
    
    def log_tab_change(e,title):
        if e.isVisible():
            logger.debug(f"Tab Changed: {title}")

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

    class TOMLSettings:
        def __init__(self, fpath):
            self.path = fpath
            self._settings = {}
            self._linkBacks = []  # (settingName, writeFunction) tuples
            self.cfg = None

        def loadSettings(self):
            self.cfg = Config(self.path)

        def saveSettings(self):
            self.cfg.save(trim=True)

        def query(self, key):
            """!
            Get the (value, type) pair associated with the setting with name key if such a pair exists, else None
            @param key:
            @return: tuple(value of setting,type of setting (string))
            """
            return self.cfg.get(key)

        def add(self, key, value):
            self.cfg.add(key, value)
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
                func(datatype(self.cfg[key]))

        def set(self, key, value, datatype):
            if callable(value):
                value = value()
            if self.cfg.get(key) is not None:
                self.cfg[key] = datatype(value)
                self.saveSettings()
                return
            raise ValueError(f"No such setting {key}")

        def asDict(self):
            return {k: v for k, [v, _] in self.cfg.items()}


    class MainWindow(QMainWindow, Ui_MainWindow):
        def __init__(self, parent=None):
            super(MainWindow, self).__init__(parent)
            self.setWindowIcon(QtGui.QIcon(LOGO_PATH("windowIcon.ico")))  # ----
            self.setupUi(self)

            self.warnings_to_show_after_load = []
            # self.blacklistLabel.setMinimumWidth(self.blacklistView.width())

            with open(PATH_TO("version.txt"), "r") as f:
                self.version = f.readline()

            #icons
            self.set_scheduler_icon(STATUS_IDLE)
            self.set_candidates_icon(STATUS_IDLE)
            self.set_database_icon(STATUS_IDLE)
            self.set_ephemeris_icon(STATUS_IDLE)
            self.set_modules_icon(STATUS_IDLE)
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
            
            if self.connect_db():
                self.startDbUpdater()
                self.startDbOperator()

            self.processesTreeView.setModel(self.processModel)
            self.ephemListView.setModel(self.ephemListModel)
            self.blacklistView.setModel(self.blacklistModel)
            self.whitelistView.setModel(self.whitelistModel)
            self.excludeListView.setModel(self.excludeListModel)

            self.current_module_index = 0

            self.setConnections()

            self.excludeStartEdit.setDateTime(self.scheduleStartTimeEdit.dateTime())
            self.excludeEndEdit.setDateTime(self.scheduleEndTimeEdit.dateTime())

            self.candidatesTabIndex = self.tabWidget.indexOf(self.candidatesTab)
            
            self.cfg_display_types = {
                "float":self.add_float_cfg,
                "int":self.add_int_cfg,
                "str":self.add_str_cfg,
                "bool":self.add_bool_cfg,
                "longstr":self.add_longstr_cfg,
                "choice":self.add_choice_cfg
            }

            # begin usage logging
            for i in self.__dict__.values():
                if isinstance(i, QPushButton):
                    i.clicked.connect(lambda _, x=i.text(): log_button_press(x))
            self.tabWidget.currentChanged.connect(lambda: log_tab_change(self.tabWidget.currentWidget(), self.tabWidget.currentIndex()))
            self.module_manager = ModuleManager()
            self.set_up_modules()
            # schedule load errors to be displayed at the end of loading
            QTimer.singleShot(0, self.show_load_errors)

        def connect_db(self):
            try:
                self.dbConnection = CandidateDatabase(self.settings.query("candidateDbPath")[0], "Maestro")
                self.set_database_icon(STATUS_DONE)
                return True
            except FileNotFoundError:
                self.set_database_icon(STATUS_ERROR)
                emsg = "Couldn't find database file. To use Maestro, choose a database under Database > Target Database Location, then press 'Request Restart'"
                self.warnings_to_show_after_load.append(("Database Not Found",emsg))
                self.statusBar().showMessage(emsg, 10000)
                return False
            except Exception as e:
                emsg = f"Unable to start database coordinator: {repr(e)}"
                logger.error(emsg)
                self.warnings_to_show_after_load.append(("Database Error",emsg))
                self.statusBar().showMessage(emsg, 10000)
                self.set_database_icon(STATUS_ERROR)
                return False
        
        def show_load_errors(self):
            if len(self.warnings_to_show_after_load):
                title, msg = self.warnings_to_show_after_load.pop()
                msg = self.warning_popup(title, msg,return_box=True)
                # connect a timer to show the next warning to the msg ok button
                msg.finished.connect(lambda: QTimer.singleShot(0, self.show_load_errors))
                msg.exec()

        def set_sunrise_sunset(self,dt=None):
            self.sunriseUTC, self.sunsetUTC = genUtils.get_sunrise_sunset(dt=dt, verbose=True)
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

            # scheduler exclude time range limits
            # exclude start must be before exclude end:
            # self.excludeEndEdit.dateTimeChanged.connect(lambda Qdt: self.excludeStartEdit.setMaximumDateTime(Qdt))

            # retry our db connection after the user chooses a new db file
            self.databasePathChooseButton.chosen.connect(lambda: QTimer.singleShot(100,self.connect_db))

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
            self.reloadModulesButton.clicked.connect(self.set_up_modules)

        def warning_popup(self, title, msg, return_box=False):
            msgBox = QMessageBox()
            # msgBox = ScrollMessageBox(title,msg,None)
            msgBox.setWindowTitle(title)
            msgBox.setWindowIcon(QtGui.QIcon(LOGO_PATH("windowIcon.ico")))
            msgBox.setIcon(QMessageBox.Icon.Warning)
            # scroll.setWidget(QLabel(msg))
            msgBox.setText(msg)
            if return_box:
                return msgBox
            msgBox.exec()

        def write_default_module_settings(self,mod_dir):
            try:
                if not os.path.exists(join(mod_dir,"cfg.schema")):
                    return
                with open(join(mod_dir,"cfg.schema"),"r") as f:
                    cfg_schema = json.load(f)
                Path(join(mod_dir,"config.toml")).touch()
                cfg = Config(join(mod_dir,"config.toml"))
                for k,v in cfg_schema.items():
                    cfg.set(k,v["DefaultValue"])
                cfg.save(trim=True)
            except Exception as e:
                # trigger a crash report but dont crash
                exception_hook(type(e), e, e.__traceback__)

        def set_up_modules(self):
            self.module_manager.update_modules()
            self.mod_info = self.module_manager.list_modules()
            # clear the mod list 
            if self.moduleList.count() > 0:
                self.current_module_index = self.moduleList.currentRow()
            self.moduleList.clear()
            self.module_entries = {}
            self.module_exceptions = {}
            nerrors = 0
            for name, info in self.mod_info.items():
                mod = None
                if not os.path.exists(join(info["dir"],"config.json")):
                    self.write_default_module_settings(info["dir"])
                # icon = None
                if info["active"]:
                    mod, self.module_exceptions[name] = self.module_manager.load_module(name, return_trace=True)
                    if mod is not None:
                        icon_path = STATUS_DONE
                        tooltip = "Module is active"
                    else:
                        icon_path = STATUS_ERROR
                        tooltip = "Module failed to load"
                        nerrors += 1
                else:
                    icon_path = STATUS_IDLE
                    tooltip = "Module is inactive"

                module_entry = ModuleListEntry(name,info["active"],icon_path)
                module_entry.checkbox.stateChanged.connect(lambda state,n=name: self.handle_module_change(state,n))
                module_entry.checkbox.setToolTip("Activate/deactivate module")
                self.module_entries[name] = module_entry
                item = QListWidgetItem(self.moduleList)
                item.setSizeHint(module_entry.sizeHint())
                self.moduleList.addItem(item)
                self.moduleList.setItemWidget(item,module_entry)
                self.module_entries[name].change_icon_tooltip(tooltip)

            if nerrors > 0:
                err_msg = f"{nerrors} module{'s' if nerrors>1 else ''} failed to load. Check the Modules tab for more information."
                # self.warning_popup(err_msg)
                self.warnings_to_show_after_load.append(("Module Failed to Load", err_msg))
                self.statusBar().showMessage(err_msg,10000)
                self.set_modules_icon(STATUS_ERROR)
            else:
                self.set_modules_icon(STATUS_DONE)
                self.statusBar().showMessage("Modules loaded successfully.",2000)
            self.moduleList.itemClicked.connect(lambda item: self.display_module(self.moduleList.itemWidget(item).name))
            self.display_module(list(self.mod_info.keys())[self.current_module_index])
            self.moduleList.setCurrentRow(self.current_module_index)

        def handle_module_change(self,state,name):
            self.module_exceptions[name] = None
            if state == 2:
                print(f"activating {name}")
                self.module_manager.activate_module(name)
                mod, exc = self.module_manager.load_module(name,return_trace=True)
                if mod is not None:
                    icon = STATUS_DONE
                    tooltip = "Module is active"
                else:
                    self.module_exceptions[name] = exc
                    icon = STATUS_ERROR
                    tooltip = "Module failed to load"
            else:
                print(f"deactivating {name}")
                icon = STATUS_IDLE
                tooltip = "Module is inactive"
                self.module_manager.deactivate_module(name)
            self.module_entries[name].change_icon(icon)
            self.module_entries[name].change_icon_tooltip(tooltip)
            self.display_module(name)
            modidx = dict(zip(self.module_entries.keys(),range(len(self.module_entries))))[name]
            self.moduleList.setCurrentRow(modidx)

        def add_float_cfg(self,name,item,modulecfg):
            spin = NoScrollQDoubleSpinBox()
            current_val = modulecfg.query(name)
            if "Min" in item:
                spin.setMinimum(item["Min"])
            elif current_val < spin.minimum():
                spin.setMinimum(current_val*2)
            if "Max" in item:
                spin.setMaximum(item["Max"])
            elif current_val > spin.maximum():
                spin.setMaximum(current_val*2)
            if "Step" in item:
                spin.setSingleStep(item["Step"])
            spin.setValue(current_val)
            modulecfg.linkWatch(spin.valueChanged, name, spin.value, spin.setValue, float)
            return spin
        
        def add_int_cfg(self,name,item,modulecfg):
            spin = NoScrollQSpinBox()
            current_val = modulecfg.query(name)
            if "Min" in item:
                spin.setMinimum(item["Min"])
            elif current_val < spin.minimum():
                spin.setMinimum(current_val*2)
            if "Max" in item:
                spin.setMaximum(item["Max"])
            elif current_val > spin.maximum():
                spin.setMaximum(current_val*2)
            if "Step" in item:
                spin.setSingleStep(item["Step"])
            spin.setValue(current_val)
            modulecfg.linkWatch(spin.valueChanged, name, spin.value, spin.setValue, int)
            return spin
        
        def add_str_cfg(self,name,item,modulecfg):
            line_edit = QLineEdit()
            current_val = modulecfg.query(name)
            line_edit.setText(current_val)
            modulecfg.linkWatch(line_edit.textChanged, name, line_edit.text, line_edit.setText, str)
            return line_edit
        
        def add_bool_cfg(self,name,item,modulecfg):
            check_box = QCheckBox()
            current_val = modulecfg.query(name)
            check_box.setChecked(current_val)
            modulecfg.linkWatch(check_box.stateChanged, name, check_box.isChecked, check_box.setChecked, bool)
            return check_box
        
        def add_longstr_cfg(self,name,item,modulecfg):
            text_edit = QTextEdit()
            current_val = modulecfg.query(name)
            text_edit.setText(current_val)
            modulecfg.linkWatch(text_edit.textChanged, name, text_edit.toPlainText, text_edit.setText, str)
            return text_edit
        
        def add_choice_cfg(self,name,item,modulecfg):
            combo = NoScrollQComboBox()
            current_val = modulecfg.query(name)
            combo.addItems(item["Choices"])
            combo.setCurrentText(current_val)
            modulecfg.linkWatch(self.intervalComboBox.currentTextChanged, name,
                                    lambda: comboValToIndex(self.intervalComboBox, self.intervalComboBox.currentText),
                                    self.intervalComboBox.setCurrentIndex, int)
            return combo

        def display_module(self,name):
            # clear the module display
            # print("displaying",name)
            # w = self.moduleContentScroll.widget()
            self.moduleContentScroll.setWidget(QWidget())
            # w.deleteLater()
            # print("deleted children")
            content = QWidget()
            clayout = QVBoxLayout()
            clayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            # add a little vertical space at the top
            clayout.addSpacing(10)
            title = QLabel(name)
            title.setFont(QtGui.QFont("Segoe UI", 20,weight=QtGui.QFont.Weight.Bold))  # ok so the rest of the app is probably in Sego UI but i like Segoe UI
            title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            title.setWordWrap(True)
            clayout.addWidget(title)
            content.setLayout(clayout)

            author = QLabel(f"Author(s): {self.mod_info[name]['author']}")
            author.setFont(QtGui.QFont("Segoe UI", 12, italic=True))
            author.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            author.setWordWrap(True)
            clayout.addWidget(author)

            description = QLabel(f"{self.mod_info[name]['description']}")
            description.setFont(QtGui.QFont("Segoe UI", 12))
            description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            description.setWordWrap(True)
            clayout.addWidget(description)

            # if the module failed to load, include an error message here
            exc = self.module_exceptions.get(name)
            if exc:
                err_widget = QWidget()
                err_widget.setAutoFillBackground(True)
                palette = err_widget.palette()
                palette.setColor(err_widget.backgroundRole(), QtGui.QColor('lightcoral'))
                err_widget.setPalette(palette)
                err_layout = QVBoxLayout()
                err_h_layout = QHBoxLayout()
                err_label = QLabel(f"Module Failed to Load")
                err_label.setFont(QtGui.QFont("Segoe UI", 14,weight=QtGui.QFont.Weight.Bold))
                err_h_layout.addWidget(err_label)
                err_h_layout.addSpacerItem(QSpacerItem(1,1,QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Minimum))
                err_h_layout.addWidget(copy_button(str(exc)))
                err_layout.addLayout(err_h_layout)
                err_label = QLabel(exc)
                err_label.setFont(QtGui.QFont("Segoe UI", 12))
                err_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                err_label.setWordWrap(True)
                err_layout.addWidget(err_label)
                err_widget.setLayout(err_layout)
                clayout.addWidget(err_widget)
            
            clayout.addSpacing(10)
            cfg_title = QLabel("Configuration")
            cfg_title.setFont(QtGui.QFont("Segoe UI", 16,weight=QtGui.QFont.Weight.Bold))
            clayout.addWidget(cfg_title)

            # this isnt actually the config but instead the description of the config
            cfg_desc_path = join(self.mod_info[name]["dir"],"cfg.schema")
            try:
                with open(cfg_desc_path,"r") as f:
                    cfg_desc = json.load(f)
                cfg = TOMLSettings(join(self.mod_info[name]["dir"],"config.toml"))
                cfg.loadSettings()

                for k,v in cfg_desc.items():
                    if v.get("Hidden",False):
                        continue
                    item_widget = QWidget()
                    item_layout = QVBoxLayout()
                    item_label = QLabel(k)
                    item_label.setFont(QtGui.QFont("Segoe UI", 14, weight=QtGui.QFont.Weight.Bold))
                    item_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                    item_label.setWordWrap(True)
                    item_layout.addWidget(item_label)

                    item_description = QLabel(v["Description"])
                    item_description.setFont(QtGui.QFont("Segoe UI", 12, italic=True))
                    item_description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                    item_description.setWordWrap(True)
                    item_layout.addWidget(item_description)

                    edit_layout = QHBoxLayout()
                    edit_box = self.cfg_display_types[v["ValDisplayType"]](k,v,cfg)
                    edit_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                    edit_box.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
                    edit_layout.addWidget(edit_box)
                    if v["Units"]:
                        unit_label = QLabel(v["Units"])
                        unit_label.setFont(QtGui.QFont("Segoe UI", 12))
                        unit_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
                        edit_layout.addWidget(unit_label)
                    if v["ValDisplayType"] != "longstr":
                        edit_layout.addSpacerItem(QSpacerItem(1,1,QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Minimum))

                    item_layout.addLayout(edit_layout)
                    item_widget.setLayout(item_layout)
                    clayout.addWidget(item_widget)

            except FileNotFoundError as e:
                cfg_label = QLabel(f"No configuration file found.")
                cfg_label.setFont(QtGui.QFont("Segoe UI", 14))
                clayout.addWidget(cfg_label)
            except Exception as e:
                cfg_label = QLabel(f"Error loading configuration:")
                cfg_label.setFont(QtGui.QFont("Segoe UI", 14))
                clayout.addWidget(cfg_label)
                err_label = QLabel(traceback.format_exc())
                err_label.setFont(QtGui.QFont("Segoe UI", 12))
                clayout.addWidget(err_label)

            # print("adding content to scroll")
            self.moduleContentScroll.setWidget(content)
            # print("added")

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
        
        def set_modules_icon(self,img_path):
            self.tabWidget.setTabIcon(4,QtGui.QIcon(img_path))
        
        def set_processes_icon(self,img_path):
            self.tabWidget.setTabIcon(5,QtGui.QIcon(img_path))


        def updateTables(self, index):
            # tables = {self.candidatesTabIndex: self.candidateView}
            tables = {}
            if index in tables.keys():
                updateTableDisplay(tables[index])

        # start the database update process
        def startDbUpdater(self):
            if not os.path.exists(self.settings.query("candidateDbPath")[0]):
                emsg = "Couldn't find database file. To use Maestro, choose a database under Database > Target Database Location, then press 'Request Restart'"
                self.warning_popup("No Database", emsg)
                self.statusBar().showMessage(emsg,10000)
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
            if not self.settings.query("scheduleSaveDir")[0]:
                self.warning_popup("No Save Directory Selected", "Please choose a save directory for the schedule using the button in the Schedule tab.")
                return
            if self.dbConnection is None:
                self.warning_popup("No Database Connection", "Please ensure the database is connected and try again.")
                return
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
            self.scheduleProcess.failed.connect(lambda: self.setSchedError(True))
            self.scheduleProcess.failed.connect(lambda: self.set_scheduler_icon(STATUS_ERROR))
            self.scheduleProcess.failed.connect(lambda m: self.warning_popup("Scheduler Failed",m))
            # self.scheduleProcess.failed.connect(lambda m: self.warning_popup("Scheduler Failed",m) if self.sched_error_occurred else None)
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
                self.set_sunrise_sunset(dt=None)
                if self.sunriseUTC - timedelta(hours=1) < datetime.now(pytz.utc):
                    # print("It's after end time for tonight. moving to tomorrow.")
                    self.set_sunrise_sunset(dt=datetime.now(pytz.utc)+timedelta(days=1))
                # print("Auto setting scheduler times. Sunrise: ", self.sunriseUTC, " Sunset: ", self.sunsetUTC," current UTC: ",datetime.now(pytz.utc))
                start = datetimeToQDateTime(max(self.sunsetUTC, datetime.now(pytz.utc)))
                # print(f"Setting start to the max of sunset ({self.sunsetUTC}) and current time ({datetime.now(pytz.utc)}): {max(self.sunsetUTC, datetime.now(pytz.utc))}")
                end = datetimeToQDateTime(self.sunriseUTC-timedelta(hours=1))
                # print(f"Setting end to sunrise - 1 hour: {self.sunriseUTC-timedelta(hours=1)}")

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
            print("selected candidates for whitelist: ", candidates)
            for candidate in candidates:
                if candidate not in self.whitelistModel._data:
                    self.blacklistModel.removeItem(candidate)
                    print(type(candidate))
                    self.whitelistModel.addItem(candidate)
                    print("whitelisted candidate: ", candidate)

        def resetCandidateTable(self):
            oldModel = self.candidateTable
            self.candidateTable = CandidateTableModel(pd.DataFrame())
            self.candidateView.setModel(self.candidateTable)
            oldModel.beginResetModel()
            oldModel.endResetModel()

        def requestDbCycle(self):
            if self.databaseProcess is None:
                self.startDbUpdater()
                return
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
            try:
                if self.settings.query("showAllCandidates")[0]:
                    self.candidates = self.dbConnection.table_query("Candidates", "*", "1=1", [], returnAsCandidates=True,skip_errors=True)
                else:
                    logger.info("Showing select")
                    self.candidates = self.dbConnection.candidatesForTimeRange(self.sunsetUTC, self.sunriseUTC, 0.01,skip_errors=True)
            except AttributeError as e:
                logger.error(f"Couldn't get candidates: {repr(e)} (probably no database)")
                emsg = "Couldn't find database file. To use Maestro, choose a database under Database > Target Database Location, then press 'Request Restart'"
                self.warning_popup("No Database", emsg)
                self.statusBar().showMessage(emsg, 10000)
                self.set_candidates_icon(STATUS_ERROR)
                return self
            except Exception as e:
                exception_hook(type(e), e, e.__traceback__)
                logger.error(f"Couldn't get candidates: {repr(e)}")
                self.statusBar().showMessage(f"ERROR: Couldn't get candidates: {repr(e)}", 10000)
                self.set_candidates_icon(STATUS_ERROR)
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

            # order the df columns by the order of the validFields list
            numbered_fields = dict(zip(validFields,np.arange(len(validFields))))
            c = list(self.candidateDf.columns)
            c.sort(key = lambda x: numbered_fields[x])
            self.candidateDf = self.candidateDf.reindex(columns=c)
            
            self.candidatesByID = {c.ID: c for c in self.candidates}
            self.candidateDict = {c.CandidateName: c for c in self.candidates}
            print(self.candidateDf.columns)
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
                emsg = "Couldn't find database file. To use Maestro, choose a database under Database > Target Database Location, then press 'Request Restart'"
                self.warning_popup("No Database", emsg)
                self.statusBar().showMessage(emsg,10000)
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