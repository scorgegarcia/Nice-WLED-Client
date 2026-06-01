from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSlider, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal


class SliderSpinBox(QWidget):
    """Slider horizontal con input numerico sincronizado."""

    valueChanged = pyqtSignal(int)

    def __init__(self, min_val=0, max_val=100, initial_value=0, parent=None):
        super().__init__(parent)
        self._suppress = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(initial_value)
        self.slider.sliderReleased.connect(self._on_slider_release)

        self.input = QLineEdit(str(initial_value))
        self.input.setFixedWidth(60)
        self.input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.input.setStyleSheet(
            "background: rgba(30,31,38,0.7); border: 1px solid rgba(255,255,255,0.1); "
            "border-radius: 6px; padding: 2px 6px; color: #c5c6c7; font-family: monospace;"
        )
        self.input.editingFinished.connect(self._on_text_edit)

        layout.addWidget(self.slider, stretch=1)
        layout.addWidget(self.input)

    def value(self):
        return self.slider.value()

    def setValue(self, val):
        self._suppress = True
        self.slider.setValue(val)
        self.input.setText(str(val))
        self._suppress = False

    def _on_slider_release(self):
        val = self.slider.value()
        self._suppress = True
        self.input.setText(str(val))
        self._suppress = False
        self.valueChanged.emit(val)

    def _on_text_edit(self):
        try:
            val = int(self.input.text())
            mn = self.slider.minimum()
            mx = self.slider.maximum()
            val = max(mn, min(mx, val))
            self._suppress = True
            self.slider.setValue(val)
            self._suppress = False
            self.valueChanged.emit(val)
        except ValueError:
            self.input.setText(str(self.slider.value()))
