import pygame
import mss
import json
import io
import os
import shutil
import subprocess
import tempfile
import time
from .base import BaseAnimation
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGroupBox
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor, QGuiApplication
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

    def showEvent(self, event):
        super().showEvent(event)
        # Reforzar "always on top" al mostrarse.
        self.raise_()
        self.activateWindow()

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
                # Preferir arrastre nativo del SO para mejorar compatibilidad.
                wh = self.windowHandle()
                if wh is not None and wh.startSystemMove():
                    self._dragging = False
                    return
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
        self._is_wayland = (
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or bool(os.environ.get("WAYLAND_DISPLAY"))
        )
        self._grim_path = shutil.which("grim")
        self._spectacle_path = shutil.which("spectacle")
        self._prefer_external_capture = False
        self._grim_failed = False
        self._spectacle_failed = False
        self._capture_errors_reported = set()
        self._last_external_capture_at = 0.0
        self._external_capture_interval = 1.0 / 8.0
        self._last_external_monitor = None
        self._last_external_surface = None
        self._spectacle_tmp_path = os.path.join(
            tempfile.gettempdir(), f"nice_wled_capture_{os.getpid()}.png"
        )

        capture = self.config.get("capture", {})
        self.setdefault("pos_x", capture.get("x", 100))
        self.setdefault("pos_y", capture.get("y", 100))
        self.setdefault("width", capture.get("w", 300))
        self.setdefault("height", capture.get("h", 200))

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
        self.frame_window.raise_()
        self.frame_window.activateWindow()

    def on_inactive(self):
        """ Hides the widget gracefully and forces save. """
        if self.frame_window is not None:
            self.frame_window._sync_props()
            self.frame_window.hide()

    def _log_capture_error_once(self, key, message):
        if key not in self._capture_errors_reported:
            self._capture_errors_reported.add(key)
            print(f"[ScreenCaptureAnim] {message}")

    def _capture_with_mss(self, monitor):
        sct_img = self.sct.grab(monitor)
        rgb = sct_img.rgb
        surface = pygame.image.frombuffer(rgb, sct_img.size, "RGB")
        return surface.copy(), not any(rgb)

    def _surface_is_black(self, surface):
        try:
            return not any(pygame.image.tostring(surface, "RGB", False))
        except Exception:
            return False

    def _capture_with_grim(self, monitor):
        if not self._grim_path or self._grim_failed:
            return None

        geometry = f"{monitor['left']},{monitor['top']} {monitor['width']}x{monitor['height']}"
        try:
            proc = subprocess.run(
                [self._grim_path, "-g", geometry, "-t", "ppm", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1.0,
                check=False,
            )
        except Exception as e:
            self._grim_failed = True
            self._log_capture_error_once("grim_exception", f"grim no pudo capturar: {e}")
            return None

        if proc.returncode != 0 or not proc.stdout:
            self._grim_failed = True
            err = proc.stderr.decode("utf-8", errors="ignore").strip()
            self._log_capture_error_once("grim_failed", f"grim no esta disponible para este compositor: {err}")
            return None

        try:
            return pygame.image.load(io.BytesIO(proc.stdout), "capture.ppm")
        except Exception as e:
            self._grim_failed = True
            self._log_capture_error_once("grim_decode", f"No se pudo decodificar la captura de grim: {e}")
            return None

    def _virtual_desktop_geometry(self):
        screens = QGuiApplication.screens()
        if not screens:
            return 0, 0, 1, 1

        left = min(screen.geometry().left() for screen in screens)
        top = min(screen.geometry().top() for screen in screens)
        right = max(screen.geometry().right() for screen in screens) + 1
        bottom = max(screen.geometry().bottom() for screen in screens) + 1
        return left, top, max(1, right - left), max(1, bottom - top)

    def _crop_fullscreen_capture(self, surface, monitor):
        virtual_left, virtual_top, virtual_w, virtual_h = self._virtual_desktop_geometry()
        scale_x = surface.get_width() / virtual_w
        scale_y = surface.get_height() / virtual_h

        rect = pygame.Rect(
            int(round((monitor["left"] - virtual_left) * scale_x)),
            int(round((monitor["top"] - virtual_top) * scale_y)),
            int(round(monitor["width"] * scale_x)),
            int(round(monitor["height"] * scale_y)),
        ).clip(surface.get_rect())

        if rect.width < 1 or rect.height < 1:
            return None
        return surface.subsurface(rect).copy()

    def _capture_with_spectacle(self, monitor):
        if not self._spectacle_path or self._spectacle_failed:
            return None

        try:
            proc = subprocess.run(
                [self._spectacle_path, "-b", "-n", "-f", "-o", self._spectacle_tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2.0,
                check=False,
            )
        except Exception as e:
            self._spectacle_failed = True
            self._log_capture_error_once("spectacle_exception", f"Spectacle no pudo capturar: {e}")
            return None

        if proc.returncode != 0 or not os.path.exists(self._spectacle_tmp_path):
            self._spectacle_failed = True
            err = proc.stderr.decode("utf-8", errors="ignore").strip()
            self._log_capture_error_once("spectacle_failed", f"Spectacle fallo al capturar: {err}")
            return None

        try:
            full = pygame.image.load(self._spectacle_tmp_path)
            return self._crop_fullscreen_capture(full, monitor)
        except Exception as e:
            self._spectacle_failed = True
            self._log_capture_error_once("spectacle_decode", f"No se pudo leer la captura de Spectacle: {e}")
            return None

    def _capture_with_external_backend(self, monitor):
        monitor_key = (monitor["left"], monitor["top"], monitor["width"], monitor["height"])
        now = time.monotonic()
        if (
            self._last_external_surface is not None
            and self._last_external_monitor == monitor_key
            and now - self._last_external_capture_at < self._external_capture_interval
        ):
            return self._last_external_surface

        surface = self._capture_with_grim(monitor)
        if surface is None:
            surface = self._capture_with_spectacle(monitor)

        if surface is not None:
            self._last_external_surface = surface
            self._last_external_monitor = monitor_key
            self._last_external_capture_at = time.monotonic()
        return surface

    def _capture_surface(self, monitor):
        if self._prefer_external_capture:
            surface = self._capture_with_external_backend(monitor)
            if surface is not None:
                return surface

        try:
            surface, is_black = self._capture_with_mss(monitor)
            if is_black and self._is_wayland:
                fallback = self._capture_with_external_backend(monitor)
                if fallback is not None:
                    if not self._surface_is_black(fallback):
                        self._prefer_external_capture = True
                    return fallback
            return surface
        except Exception as e:
            self._log_capture_error_once("mss_failed", f"mss no pudo capturar la region: {e}")
            surface = self._capture_with_external_backend(monitor)
            if surface is not None:
                self._prefer_external_capture = True
                return surface
            return None

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

        img = self._capture_surface(monitor)
        if img is None:
            return

        try:
            scaled = pygame.transform.smoothscale(img, (self.engine.width, self.engine.height))
            self.engine.surface.blit(scaled, (0, 0))
        except Exception as e:
            self._log_capture_error_once("scale_failed", f"No se pudo escalar la captura: {e}")

    def get_name(self):
        return "Capturar Pantalla"
