import io
import os
import shutil
import subprocess
import tempfile
import threading
import time

import mss
import pygame
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QGroupBox

from .base import BaseAnimation
from widgets.slider_spinbox import SliderSpinBox


class ScreenCaptureAnim(BaseAnimation):
    def __init__(self, engine):
        super().__init__(engine)
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
        self._mss_black_streak = 0
        self._external_capture_interval = 1.0 / 10.0
        self._last_external_monitor = None
        self._last_external_surface = None
        self._external_requested_monitor = None
        self._external_worker = None
        self._external_stop = None
        self._external_lock = threading.Lock()
        self._spectacle_tmp_path = os.path.join(
            tempfile.gettempdir(), f"nice_wled_capture_{os.getpid()}.png"
        )

        capture = self.config.get("capture", {})
        self.setdefault("pos_x", capture.get("x", 100))
        self.setdefault("pos_y", capture.get("y", 100))
        self.setdefault("width", capture.get("w", 300))
        self.setdefault("height", capture.get("h", 200))

    def _update_capture_config(self):
        self.config["capture"] = {
            "x": int(self.props.get("pos_x", 100)),
            "y": int(self.props.get("pos_y", 100)),
            "w": int(self.props.get("width", 300)),
            "h": int(self.props.get("height", 200)),
        }

    def build_ui(self, layout):
        from PyQt6.QtWidgets import QHBoxLayout

        def make_param_row(label_text, key, min_val, max_val):
            group = QGroupBox(label_text)
            row = QHBoxLayout(group)
            row.setContentsMargins(8, 6, 8, 6)

            widget = SliderSpinBox(min_val, max_val, int(self.props[key]))

            def on_change(v):
                self.props[key] = int(v)
                self._update_capture_config()
                self.save_props()

            widget.valueChanged.connect(on_change)
            row.addWidget(widget)
            layout.addWidget(group)
            return widget

        self.ui_pos_x = make_param_row("Posicion X", "pos_x", 0, 3840)
        self.ui_pos_y = make_param_row("Posicion Y", "pos_y", 0, 2160)
        self.ui_width = make_param_row("Ancho", "width", 50, 3840)
        self.ui_height = make_param_row("Alto", "height", 50, 2160)

    def on_active(self):
        self._update_capture_config()

    def on_inactive(self):
        self._stop_external_worker()

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
            self._log_capture_error_once(
                "grim_failed", f"grim no esta disponible para este compositor: {err}"
            )
            return None

        try:
            return pygame.image.load(io.BytesIO(proc.stdout), "capture.ppm")
        except Exception as e:
            self._grim_failed = True
            self._log_capture_error_once(
                "grim_decode", f"No se pudo decodificar la captura de grim: {e}"
            )
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
            self._log_capture_error_once(
                "spectacle_exception", f"Spectacle no pudo capturar: {e}"
            )
            return None

        if proc.returncode != 0 or not os.path.exists(self._spectacle_tmp_path):
            self._spectacle_failed = True
            err = proc.stderr.decode("utf-8", errors="ignore").strip()
            self._log_capture_error_once(
                "spectacle_failed", f"Spectacle fallo al capturar: {err}"
            )
            return None

        try:
            full = pygame.image.load(self._spectacle_tmp_path)
            return self._crop_fullscreen_capture(full, monitor)
        except Exception as e:
            self._spectacle_failed = True
            self._log_capture_error_once(
                "spectacle_decode", f"No se pudo leer la captura de Spectacle: {e}"
            )
            return None

    def _start_external_worker(self):
        if self._external_worker is not None and self._external_worker.is_alive():
            return
        self._external_stop = threading.Event()
        self._external_worker = threading.Thread(
            target=self._external_capture_loop,
            args=(self._external_stop,),
            daemon=True,
        )
        self._external_worker.start()

    def _stop_external_worker(self):
        if self._external_stop is not None:
            self._external_stop.set()
        with self._external_lock:
            self._external_requested_monitor = None
            self._last_external_monitor = None
            self._last_external_surface = None

    def _external_capture_loop(self, stop_event):
        while not stop_event.is_set():
            with self._external_lock:
                monitor = (
                    dict(self._external_requested_monitor)
                    if self._external_requested_monitor
                    else None
                )

            if monitor is None:
                time.sleep(0.05)
                continue

            started_at = time.monotonic()
            surface = self._capture_with_grim(monitor)
            if surface is None:
                surface = self._capture_with_spectacle(monitor)

            if surface is not None and not stop_event.is_set():
                monitor_key = (
                    monitor["left"],
                    monitor["top"],
                    monitor["width"],
                    monitor["height"],
                )
                with self._external_lock:
                    self._last_external_surface = surface
                    self._last_external_monitor = monitor_key

            elapsed = time.monotonic() - started_at
            wait_for = max(0.01, self._external_capture_interval - elapsed)
            stop_event.wait(wait_for)

    def _capture_with_external_backend(self, monitor):
        monitor_key = (
            monitor["left"],
            monitor["top"],
            monitor["width"],
            monitor["height"],
        )
        self._start_external_worker()
        with self._external_lock:
            self._external_requested_monitor = dict(monitor)
            if self._last_external_monitor == monitor_key:
                return self._last_external_surface
        return None

    def _capture_surface(self, monitor):
        if self._prefer_external_capture:
            surface = self._capture_with_external_backend(monitor)
            if surface is not None:
                return surface

        try:
            surface, is_black = self._capture_with_mss(monitor)
            if not is_black:
                self._mss_black_streak = 0
                self._prefer_external_capture = False
                return surface

            if self._is_wayland:
                self._mss_black_streak += 1
                if self._mss_black_streak >= 4:
                    fallback = self._capture_with_external_backend(monitor)
                    if fallback is not None and not self._surface_is_black(fallback):
                        self._prefer_external_capture = True
                        return fallback
            return surface
        except Exception as e:
            self._log_capture_error_once("mss_failed", f"mss no pudo capturar la region: {e}")
            self._prefer_external_capture = True
            surface = self._capture_with_external_backend(monitor)
            if surface is not None:
                return surface
            return None

    def render(self, t):
        left = int(self.props.get("pos_x", 100))
        top = int(self.props.get("pos_y", 100))
        width = int(self.props.get("width", 300))
        height = int(self.props.get("height", 200))

        monitor = {
            "top": top,
            "left": left,
            "width": max(1, width),
            "height": max(1, height),
        }

        if monitor["width"] < 10 or monitor["height"] < 10:
            return

        img = self._capture_surface(monitor)
        if img is None:
            return

        try:
            scaled = pygame.transform.scale(img, (self.engine.width, self.engine.height))
            self.engine.surface.blit(scaled, (0, 0))
        except Exception as e:
            self._log_capture_error_once("scale_failed", f"No se pudo escalar la captura: {e}")

    def get_name(self):
        return "Capturar Pantalla"
