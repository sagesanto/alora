from PyQt6 import QtGui, QtCore
from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QTableWidget, \
        QTableWidgetItem as QTableItem, QLineEdit, QListView, QDockWidget, QComboBox, \
              QPushButton, QMessageBox, QHBoxLayout, QVBoxLayout, QCheckBox, QLabel, QListWidgetItem, \
                QSizePolicy, QSpinBox, QSpacerItem, QTextEdit, QDoubleSpinBox
from PyQt6.QtCore import Qt, QItemSelectionModel, QDateTime, QSortFilterProxyModel
import PyQt6.QtWidgets as QtWidgets

class WheelEventMixin:
    def wheelEvent(self, event):
        if self.hasFocus():
            super(self.__class__, self).wheelEvent(event)
        else:
            event.ignore()

def add_wheel_event_mixin(cls):
    class NewClass(cls, WheelEventMixin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
    return NewClass

NoScrollQComboBox = add_wheel_event_mixin(QComboBox)
NoScrollQSpinBox = add_wheel_event_mixin(QSpinBox)
NoScrollQDoubleSpinBox = add_wheel_event_mixin(QDoubleSpinBox)
