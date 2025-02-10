from PyQt6.QtWidgets import QMessageBox, QScrollArea, QWidget, QVBoxLayout, QLabel, QSizePolicy

# from https://stackoverflow.com/a/47346376
class ScrollMessageBox(QMessageBox):
    def __init__(self, title, msg, *args, **kwargs):
        QMessageBox.__init__(self, *args, **kwargs)
        self.setWindowTitle(title)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.content = QWidget()
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self.content)
        
        msg_label = QLabel(msg, self)
        msg_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        lay.addWidget(msg_label)
        scroll.setWidget(self.content)
        self.layout().addWidget(scroll, 0, 0, 1, self.layout().columnCount())
        
        # self.setStyleSheet("QScrollArea{min-width:600 px; min-height: 750px}")