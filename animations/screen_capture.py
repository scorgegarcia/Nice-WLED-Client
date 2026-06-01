import pygame
import mss
import json
from .base import BaseAnimation
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGroupBox
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor
from widgets.slider_spinbox import SliderSpinBox


class CaptureFrameWindow(QWidget):
    def __init__(self, config, props=None):
        super().__init__()
        self.config = config
        self.props = props

        # Frameless, Always on Top, interactuable
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        # Background completely transparent to the OS
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Load geometry from props (or config.json fallback)
        px = self.props.get("pos_x", 100) if self.props else 100
        py = self.props.get("pos_y", 100) if self.props else 100
        pw = self.props.get("width", 300) if self.props else 300
        ph = self.props.get("height", 200) if self.props else 200
        self.setGeometry(px, py, pw, ph)

        self.margin = 20
        self.top_bar_height = 30
        self.border_t = 4

        self._resizing = False
        self._dragging = False
        self._drag_pos = QPoint()

    def paintEvent(self, event):
        painter = QPainter(self)

        # Barra superior para arrastrar
        painter.fillRect(0, 0, self.width(), self.top_bar_height, QColor(200, 0, 0, 220))

        # Barra inferior completa donde vivira el Grip
        painter.fillRect(0, self.height() - self.margin, self.width(), self.margin, QColor(200, 0, 0, 220))

        # Borde lateral
        pen = QPen(QColor(200, 0, 0, 220), self.border_t)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width()-1, self.height()-1)

        # Grip para escalar en esquina inferior derecha
        painter.fillRect(self.width()-self.margin, self.height()-self.margin, self.margin, self.margin, QColor(150, 0, 0, 255))

        # Texto de ayuda
        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawText(10, 20, "← Arrastrar | Escalar ↘")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            # Scale
            if pos.x() > self.width() - self.margin and pos.y() > self.height() - self.margin:
                self._resizing = True
            # Drag
            elif pos.y() <= self.top_bar_height or pos.x() <= self.border_t or pos.x() >= self.width() - self.border_t or pos.y() >= self.height() - self.border_t:
                self._dragging = True
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            self._sync_props()
        elif self._resizing:
            pos = event.pos()
            self.resize(max(100, pos.x()), max(100, pos.y()))
            self._sync_props()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._resizing = False
        self._sync_props()

    def _sync_props(self):
        """Sincroniza la geometria de la ventana con los props del plugin."""
        g = self.geometry()
        if self.props is not None:
            self.props["pos_x"] = g.x()
            self.props["pos_y"] = g.y()
            self.props["width"] = g.width()
            self.props["height"] = g.height()
        # Tamben guardar en config.json para compatibilidad con la ventana
        self.config["capture"] = {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()}
        try:
            with open("config.json", "w") as f:
                json.dump(self.config, f, indent=4)
        except: pass

    def update_from_props(self):
        """Actualiza la posicion/tamano de la ventana cuando los props cambian desde fuera."""
        if self.props is None: return
        px = self.props.get("pos_x", self.x())
        py = self.props.get("pos_y", self.y())
        pw = self.props.get("width", self.width())
        ph = self.props.get("height", self.height())
        self.setGeometry(px, py, pw, ph)


class ScreenCaptureAnim(BaseAnimation):
    def __init__(self, engine):
        super().__init__(engine)
        self.frame_window = None
        self.sct = mss.mss()

        self.setdefault("pos_x", 100)
        self.setdefault("pos_y", 100)
        self.setdefault("width", 300)
        self.setdefault("height", 200)

    def build_ui(self, layout):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy

        def make_param_row(label_text, key, min_val, max_val):
            group = QGroupBox(label_text)
            row = QHBoxLayout(group)
            row.setContentsMargins(8, 6, 8, 6)

            widget = SliderSpinBox(min_val, max_val, self.props[key])
            widget.valueChanged.connect(
                lambda v: (self.props.update({key: v}), self.save_props(), self._apply_prop_to_window())
            )
            row.addWidget(widget)
            layout.addWidget(group)
            return widget

        self.ui_pos_x = make_param_row("Posicion X", "pos_x", 0, 3840)
        self.ui_pos_y = make_param_row("Posicion Y", "pos_y", 0, 2160)
        self.ui_width = make_param_row("Ancho", "width", 50, 3840)
        self.ui_height = make_param_row("Alto", "height", 50, 2160)

    def _apply_prop_to_window(self):
        """Aplica los props actuales a la ventana de captura si existe."""
        if self.frame_window is not None:
            self.frame_window.update_from_props()

    def on_active(self):
        """ Spawns the transparent floating frame widget. """
        if self.frame_window is None:
            self.frame_window = CaptureFrameWindow(self.config, self.props)
        else:
            self.frame_window.props = self.props
            self.frame_window.update_from_props()
        self.frame_window.show()

    def on_inactive(self):
        """ Hides the widget gracefully and forces save. """
        if self.frame_window is not None:
            self.frame_window._sync_props()
            self.frame_window.hide()

    def render(self, t):
        if self.frame_window is None or not self.frame_window.isVisible():
            return

        g = self.frame_window.geometry()

        # Ignorar barras y bordes para captura 100% hueca
        top_offset = self.frame_window.top_bar_height
        bottom_offset = self.frame_window.margin
        border = self.frame_window.border_t

        monitor = {
            "top": g.y() + top_offset,
            "left": g.x() + border,
            "width": g.width() - (border * 2),
            "height": g.height() - top_offset - bottom_offset
        }

        if monitor["width"] < 10 or monitor["height"] < 10:
            return

        try:
            sct_img = self.sct.grab(monitor)
            img = pygame.image.frombuffer(sct_img.bgra, sct_img.size, "BGRA")

            scaled = pygame.transform.smoothscale(img, (self.engine.width, self.engine.height))
            self.engine.surface.blit(scaled, (0, 0))
        except Exception as e:
            pass

    def get_name(self):
        return "Capturar Pantalla"
