# Sage Santomenna 2023-2025
# For use in asynchronous computing
# Process(QProcess) - represents one asynchronous process. manages Process status and communication.
# ProcessModel(QAbstractItemModel) - stores Processes and information about them in a tree-like form
# TreeItem - node of the ProcessModel tree model

# this is probably the sketchiest part of the whole system. unfortunate, considering its pretty important

import logging
import os
import signal
from datetime import datetime, timedelta

import pytz
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QProcess
from PyQt6.QtWidgets import QLayout

logger = logging.getLogger(__name__)

def generateTimestampString():
    return datetime.now().strftime("%m/%d %H:%M:%S") + " local / " + datetime.now(pytz.UTC).strftime(
        "%m/%d %H:%M:%S") + " UTC"


def decodeStdOut(p: QProcess):
    # print("decoding std out from",p)
    return bytes(p.readAllStandardOutput()).decode("utf-8")


def decodeStdErr(p: QProcess):
    # print("decoding std err from",p)
    return bytes(p.readAllStandardError()).decode("utf-8")


def interpretState(state):
    states = {
        QProcess.ProcessState.NotRunning: 'Not running',
        QProcess.ProcessState.Starting: 'Starting',
        QProcess.ProcessState.Running: 'Running',
    }
    return states[state]


class TreeItem(QtWidgets.QLabel):
    updated = pyqtSignal(QtCore.QModelIndex)

    # updated = pyqtSignal()

    def __init__(self, data, parent=None, tags=None):
        super().__init__()
        self.parentItem = parent
        self.itemData = data
        self.index = None
        self.childItems = []
        self.tags = tags or {}
        self.destroyed.connect(self.deleteLater)
        self.toolTip = None
        # self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def __repr__(self):
        return "Tree Item" + (": Root: " if self.parentItem is None else " ") + str(self.itemData)

    def setToolTip(self, text):
        self.toolTip = text

    def setIndex(self, index: QtCore.QModelIndex):  # don't think this is very pythonic
        self.index = index

    def addTag(self, key, value):
        self.tags[key] = value

    def appendChild(self, item):
        self.childItems.insert(0, item)
        return self

    def child(self, row):
        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def columnCount(self):
        return len(self.itemData)

    def data(self, column):
        try:
            return self.itemData[column]
        except IndexError:
            return None

    @QtCore.pyqtSlot()
    def updateData(self, column, data):
        try:
            self.itemData[column] = data
            self.updated.emit(self.index)
        except RuntimeError as e:
            print(f"Caught runtime error in updateData: {e}")

    def parent(self):
        return self.parentItem

    def row(self):
        if self.parentItem:
            return self.parentItem.childItems.index(self)
        return 0


class Process(QProcess):
    deleted = pyqtSignal()
    logged = pyqtSignal(str)
    errorSignal = pyqtSignal(str) # emitted whenever an error occurs
    failed = pyqtSignal(str) # emitted whenever the process finishes with an error
    msg = pyqtSignal(str)
    lastLog = pyqtSignal(str)
    paused = pyqtSignal()
    resumed = pyqtSignal()
    ended = pyqtSignal(str)  # emitted whenever the process finishes (either successfully or with an error)
    succeeded = pyqtSignal(str)  # emitted when the process finishes successfully
    ponged = pyqtSignal(str)
    triggered = pyqtSignal(str, str)

    def __init__(self, name: str, triggerPhrases=None, description="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(self.parent(), QProcess):
            self.setInputChannelMode()
        triggerPhrases = triggerPhrases or []
        self.name = name
        self.fullName = self.parent().name + "/" + self.name if self.parent() else self.name
        self.startLocal = datetime.now()
        self.startUTC = datetime.now(pytz.UTC)
        self.startString = generateTimestampString()
        self.log = []
        self.errorLog = []
        self.isPaused = False
        self.triggerPhrases = triggerPhrases  # trigger phrases are phrases that, if recieved through stdout from our subprocess, will cause our "triggered" signal to be emitted.
        self.description = description
        self.connect()
        self.lastPing = None
        # self.logger = logging.getLogger(__file__)
        # self.logger.addHandler(loggingFileHandler)
        # self.logger.setLevel(logging.DEBUG)
        
        self.logger = logger
        # self.logger.setLevel(logging.DEBUG)
        self.errored = False

    def connect(self):
        self.readyReadStandardError.connect(lambda: self.writeToErrorLog(decodeStdErr(self)))
        self.readyReadStandardOutput.connect(lambda: self.writeToLog(decodeStdOut(self)))
        self.finished.connect(self.onFinished)
        self.errorOccurred.connect(self.onErrorOcurred)
        self.finished.connect(self.deleteLater)  # this might not be necessary
        # self.finished.connect(lambda exitCode: self.ended.emit("Finished" if not exitCode else "Error"))
        self.msg.connect(self.triggerFilter)
        self.errorSignal.connect(self.onErrorSignal)
        self.ended.connect(self.decideSuccess)

    def clear_error(self):
        self.errored = False

    def decideSuccess(self):
        # this is so cringe
        if not self.errored:
            self.succeeded.emit("Finished")

    def onErrorSignal(self, error):
        self.errored = True

    def start(self, *args, **kwargs):
        self.logger.info("Starting process " + self.fullName)
        super().start(*args, **kwargs)
    
    def startDetached(self, *args, **kwargs):
        self.logger.info("Starting detached process " + self.fullName)
        return super().startDetached(*args, **kwargs)

    def onFinished(self, exitCode, exitStatus: QProcess.ExitStatus):
        if exitStatus == QProcess.ExitStatus.CrashExit:
            self.logger.error(self.fullName + " experienced a fatal error")
            return  # handle in onErrorOccurred
        if not exitCode:  # good state
            self.logger.info(f"Good state: {self.fullName} finished with error code {exitCode}")
            self.clear_error()
            self.lastLog.emit(self.log[-1] if len(self.log) else "No message")
            self.ended.emit("Finished")
            self.succeeded.emit("Finished")
            return
        else:
            # self.onErrorOcurred(exitStatus)
            partialString = f"Error: finished with error {self.error().name} and exit code {exitCode}"
            self.ended.emit(partialString)
            self.errorSignal.emit(partialString) # nightmare. this error signal sets the error message in the model
            self.failed.emit("\n\n".join(self.errorLog))
            # self.failed.emit(partialString)
            self.logger.error(self.fullName + " got a non-zero exit code with error " + self.error().name + ".")
            self.logger.error(decodeStdErr(self))

    def onErrorOcurred(self, exitStatus: QProcess.ProcessError):
        self.errored = True
        self.errorSignal.emit("Error with error reason " + self.errorString())
        if exitStatus == QProcess.ExitStatus.CrashExit:
            self.logger.error(decodeStdErr(self))
            self.ended.emit("Crashed")
            return

        processErrorReason = exitStatus.name
        self.logger.error(
            "Error occurred:" + self.fullName + " got " + self.errorString() + " with error reason " + processErrorReason)
        self.logger.error(decodeStdErr(self))
        self.failed.emit(f"Error occurred in {self.fullName:} "+self.errorString())
        self.ended.emit("Error")

    def __del__(self):
        logger.info(f"Deleting process {self.name} with PID {self.processId()}")
        self.ended.emit("Deleted")
        self.kill()
        del self

    def reset(self):
        # print("Resetting")
        pass
        # self.deleted.emit()

    @property
    def status(self):
        return interpretState(self.state())

    @property
    def isActive(self):
        try:
            return self.state() != QProcess.ProcessState.NotRunning
        except RuntimeError as e:
            # terrible practice
            return False

    def pause(self):
        """!
        Attempt to pause this process. If it has subprocesses of its own, pausing may not acheive complete stoppage
        """
        if not self.isPaused and self.isActive:
            # print("Pausing", self.name)
            self.paused.emit()
            self.isPaused = True
            os.kill(self.processId(), signal.SIGSTOP)
            return

    def resume(self):
        if self.paused:
            # print("Resuming", self.name)
            self.resumed.emit()
            self.isPaused = False
            os.kill(self.processId(), signal.SIGCONT)

    def ping(self):
        self.write("{}: Ping!\n".format(self.name))
        self.lastPing = datetime.now()

    def write(self, msg: str):
        super().write(bytes(msg, "utf-8"))

    def triggerFilter(self, msg: str):  # emit the "triggered" signal if one of the phrases in the "triggered
        if "{}: Pong!".format(self.name) in msg:
            # print("Got pong: ", msg)
            logger.info(f"{self.name} got ponged!")
            self.ponged.emit(msg.replace("{}: ".format(self.name), ""))
            self.lastPing = None
            return
        if f"{self.name}: CLEAR_ERROR" in msg:
            self.clear_error()
            self.writeToLog(f"Error cleared at request of process {self.name}")
            logger.info(f"Error cleared at request of process {self.name}")
            return
        for phrase in self.triggerPhrases:
            if phrase in msg:
                # print("Got trigger",phrase,"in message",msg)
                self.triggered.emit(phrase, msg)

        if self.lastPing is not None and datetime.now() - self.lastPing > timedelta(seconds=1):
            self.lastPing = None  # prevents infinite loop?
            self.writeToErrorLog("Dead ping!")
        return

    def writeToErrorLog(self, error):
        error = "\n".join([c for c in error.split("\n") if c])
        error_msg = self.fullName + ", reading error: " + error
        self.logger.error(error_msg)
        self.errorLog.append(error_msg)
        self.errorSignal.emit(error)
        self.msg.emit(error_msg)

    def writeToLog(self, content):
        content = "\n".join([c for c in content.split("\n") if c])

        # not logging because it duplicates the log. processes should do their own logging
        # self.logger.info(self.fullName + ": " + content)

        for c in content.split("\n"):
            self.msg.emit(c)
            self.log.append(c)
            self.logged.emit(c)

    def abort(self):
        if self.isActive:
            self.setErrorString("Aborted")
            self.logger.info("User aborted" + self.fullName)
            self.writeToErrorLog("User Abort")
            self.ended.emit("Aborted")
            self.blockSignals(True)
            self.kill()

    def PID(self,state):
        if state != QProcess.ProcessState.NotRunning:
            return self.processId()
        return "Not running"

class ProcessModel(QtCore.QAbstractItemModel):
    updated = pyqtSignal()

    def __init__(self, processes=None, parent=None, statusBar=None):
        super(ProcessModel, self).__init__(parent)
        processes = processes or []
        self.rootItem = TreeItem(("Process", "Status"))
        for process in processes:
            self.add(process)
        self.statusBar = statusBar
        # connect the aboutToQuit signal to the killAllProcesses method
        QtCore.QCoreApplication.instance().aboutToQuit.connect(self.killAllProcesses)

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return None
        item = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            return item.data(index.column())
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.toolTip

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.rootItem.data(section)
        return None

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QtCore.QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        childItem = index.internalPointer()
        parentItem = childItem.parent()
        if parentItem == self.rootItem:
            return QtCore.QModelIndex()
        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        return parentItem.childCount()

    def emitDataChanged(self, index: QtCore.QModelIndex):
        self.dataChanged.emit(index, index)

    def setData(self, index: QtCore.QModelIndex, newData, state=None):
        # if state:
        #     print("State:",state)
        if index.isValid():
            item = index.internalPointer()
            item.updateData(1, newData)
            self.dataChanged.emit(index, index)  # <---


    def add(self, process: Process):
        self.beginInsertRows(QtCore.QModelIndex(), 0, 4)
        topItem = TreeItem([process.name, process.status], parent=self.rootItem, tags={"Process": process})
        startItem = TreeItem(["Start", process.startString], topItem)
        endItem = TreeItem(["End", ""], topItem)
        resultItem = TreeItem(["Result", ""], topItem)
        locItem = TreeItem(["PID", str(process.processId())], topItem)

        topItem.appendChild(locItem).appendChild(resultItem).appendChild(endItem).appendChild(startItem)
        self.rootItem.appendChild(topItem)

        topIndex = self.index(0, 0, QtCore.QModelIndex())
        topItem.setIndex(topIndex)
        topItem.updated.connect(self.emitDataChanged)

        if process.description:
            topItem.setToolTip(process.description)

        for i, item in enumerate([startItem, endItem, resultItem, locItem]):
            item.setIndex(self.index(i, 0, topIndex))
            item.updated.connect(self.emitDataChanged)

        process.ended.connect(lambda msg: self.setData(topItem.index, msg))
        process.stateChanged.connect(lambda state: self.setData(locItem.index, process.PID(state),state))
        process.stateChanged.connect(lambda state: self.setData(topItem.index, interpretState(state),state))
        process.paused.connect(lambda: self.setData(topItem.index, "Paused"))
        process.resumed.connect(lambda state: self.setData(topItem.index, interpretState(state)))

        process.ended.connect(lambda: self.setData(endItem.index, generateTimestampString()))

        process.lastLog.connect(lambda msg: self.setData(resultItem.index, msg))
        # process.ponged.connect(lambda msg: self.setData(resultItem.index, msg))
        process.errorOccurred.connect(lambda: self.setData(resultItem.index, process.error()))
        process.errorSignal.connect(lambda msg: self.setData(resultItem.index, msg))

        if self.statusBar is not None:
            process.ponged.connect(
                lambda msg: self.statusBar.showMessage("Process '{}': '{}'".format(process.name, msg),
                                                       750))
            process.ended.connect(
                lambda msg: self.statusBar.showMessage("Process '{}' ended with status '{}'".format(process.name, msg),
                                                       10000))
        self.endInsertRows()

    def terminateAllProcesses(self):
        for item in self.rootItem.childItems:
            try:
                item.tags["Process"].blockSignals(True)
                item.tags["Process"].terminate()
                item.tags["Process"].waitForFinished(1)
                logger.info(f"Terminated {item.tags['Process'].name}")
            except RuntimeError as e:
                pass
                # print(f"Failed to terminate {item.tags['Process'].name}: {e}")

    def killAllProcesses(self):
        for item in self.rootItem.childItems:
            try: 
                item.tags["Process"].kill()
                logger.info(f"Killed {item.tags['Process'].name}")
            except RuntimeError as e:
                pass
                # print(f"Failed to kill {item.tags['Process'].name}: {e}")