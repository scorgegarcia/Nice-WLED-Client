from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QColorDialog
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor


class ColorPickerWidget(QWidget):
    """Widget con preview de color (cuadro clickeable) + texto hex editable + dialog de color."""

    valueChanged = pyqtSignal(str)

    def __init__(self, initial_color="#ffffff", parent=None):
        super().__init__(parent)
        self._value = initial_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.preview_btn = QPushButton()
        self.preview_btn.setFixedSize(28, 28)
        self.preview_btn.setStyleSheet("border-radius: 6px; border: 2px solid rgba(255,255,255,0.3);")
        self.preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_btn.setToolTip("Abrir selector de color")
        self.preview_btn.clicked.connect(self.open_color_dialog)

        self.hex_input = QLabel(initial_color)
        self.hex_input.setStyleSheet(
            "background: rgba(30,31,38,0.7); border: 1px solid rgba(255,255,255,0.1); "
            "border-radius: 6px; padding: 4px 8px; font-family: monospace; min-width: 70px;"
        )

        layout.addWidget(self.preview_btn)
        layout.addWidget(self.hex_input)

        self._apply_color(initial_color)

    def _apply_color(self, color_str):
        try:
            qc = QColor(color_str)
            if qc.isValid():
                self._value = color_str
                r, g, b = qc.red(), qc.green(), qc.blue()
                lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                text_color = "#000000" if lum > 0.55 else "#ffffff"
                self.preview_btn.setStyleSheet(
                    f"border-radius: 6px; border: 2px solid rgba(255,255,255,0.3); "
                    f"background-color: {color_str}; color: {text_color};"
                )
                self.hex_input.setText(color_str.upper())
        except Exception:
            pass

    def value(self):
        return self._value

    def setValue(self, color_str):
        self._value = color_str
        self._apply_color(color_str)

    def open_color_dialog(self):
        initial = QColor(self._value) if self._value else QColor("#ffffff")
        dialog = QColorDialog(initial, self)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        if dialog.exec() == 1:
            color = dialog.currentColor()
            hex_str = color.name()
            self.setValue(hex_str)
            self.valueChanged.emit(hex_str)
