import io
import os
import shutil
import subprocess
import tempfile
import threading
import time

try:
    import dbus
except Exception:
    dbus = None

try:
    from pipewire_capture import (
        CaptureStream as PipeWireCaptureStream,
        PortalCapture as PipeWirePortalCapture,
        is_available as pipewire_is_available,
    )
except Exception:
    PipeWireCaptureStream = None
    PipeWirePortalCapture = None
    pipewire_is_available = None

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
        self._prefer_external_capture = self._is_wayland
        self._grim_failed = False
        self._spectacle_failed = False
        self._capture_errors_reported = set()
        self._mss_black_streak = 0
        self._external_capture_interval = 1.0 / 20.0
        self._last_external_monitor = None
        self._last_external_surface = None
        self._external_requested_monitor = None
        self._external_worker = None
        self._external_stop = None
        self._external_lock = threading.Lock()
        self._external_backend_logged = set()
        self._kwin_dbus = dbus
        self._kwin_bus = None
        self._kwin_iface = None
        self._kwin_failed = False
        self._pipewire_failed = False
        self._pipewire_portal = None
        self._pipewire_session = None
        self._pipewire_stream = None
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
        if self._is_wayland:
            self._prefer_external_capture = True
            self._start_external_worker()

    def on_inactive(self):
        self._stop_external_worker()

    def _log_capture_error_once(self, key, message):
        if key not in self._capture_errors_reported:
            self._capture_errors_reported.add(key)
            print(f"[ScreenCaptureAnim] {message}")

    def _log_backend_once(self, backend_name):
        key = f"backend_{backend_name}"
        if key not in self._external_backend_logged:
            self._external_backend_logged.add(key)
            print(f"[ScreenCaptureAnim] usando backend: {backend_name}")

    def _cleanup_pipewire(self):
        if self._pipewire_stream is not None:
            try:
                self._pipewire_stream.stop()
            except Exception:
                pass
            self._pipewire_stream = None

        if self._pipewire_session is not None:
            try:
                self._pipewire_session.close()
            except Exception:
                pass
            self._pipewire_session = None

        if self._pipewire_portal is not None:
            try:
                close_fn = getattr(self._pipewire_portal, "close", None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                pass
        self._pipewire_portal = None

    def _init_pipewire_stream(self):
        if (
            self._pipewire_failed
            or not self._is_wayland
            or PipeWirePortalCapture is None
            or PipeWireCaptureStream is None
            or pipewire_is_available is None
        ):
            return False

        try:
            if not pipewire_is_available():
                self._pipewire_failed = True
                self._log_capture_error_once(
                    "pipewire_unavailable",
                    "PipeWire no disponible para captura en esta sesion.",
                )
                return False

            print(
                "[ScreenCaptureAnim] Abriendo selector de captura PipeWire (elige pantalla/ventana)..."
            )
            self._pipewire_portal = PipeWirePortalCapture()
            self._pipewire_session = self._pipewire_portal.select_window()
            if self._pipewire_session is None:
                self._pipewire_failed = True
                self._log_capture_error_once(
                    "pipewire_select_cancelled",
                    "No se selecciono una fuente en el portal de PipeWire.",
                )
                self._cleanup_pipewire()
                return False

            self._pipewire_stream = PipeWireCaptureStream(
                self._pipewire_session.fd,
                self._pipewire_session.node_id,
                self._pipewire_session.width,
                self._pipewire_session.height,
                1.0 / 60.0,
            )
            self._pipewire_stream.start()
            self._log_backend_once("pipewire")
            return True
        except Exception as e:
            self._pipewire_failed = True
            self._log_capture_error_once(
                "pipewire_init_failed",
                f"No se pudo iniciar backend PipeWire: {e}",
            )
            self._cleanup_pipewire()
            return False

    def _capture_with_pipewire(self, monitor):
        if self._pipewire_stream is None and not self._init_pipewire_stream():
            return None

        try:
            if getattr(self._pipewire_stream, "window_invalid", False):
                self._cleanup_pipewire()
                if not self._init_pipewire_stream():
                    return None

            frame = self._pipewire_stream.get_frame()
            if frame is None:
                return None
            if len(frame.shape) != 3 or frame.shape[2] < 3:
                return None

            height, width = int(frame.shape[0]), int(frame.shape[1])
            if width < 1 or height < 1:
                return None

            bgr = frame[:, :, :3]
            bgr_data = bgr.tobytes()
            surface = pygame.image.frombuffer(bgr_data, (width, height), "BGR").copy()

            rect = pygame.Rect(
                monitor["left"], monitor["top"], monitor["width"], monitor["height"]
            ).clip(surface.get_rect())
            if rect.width < 1 or rect.height < 1:
                return surface
            if rect == surface.get_rect():
                return surface
            return surface.subsurface(rect).copy()
        except Exception as e:
            self._log_capture_error_once(
                "pipewire_capture_failed",
                f"Fallo captura PipeWire: {e}",
            )
            return None

    def _capture_with_mss(self, monitor):
        sct_img = self.sct.grab(monitor)
        rgb = sct_img.rgb
        surface = pygame.image.frombuffer(rgb, sct_img.size, "RGB")
        return surface.copy(), not any(rgb)

    def _ensure_kwin_interface(self):
        if self._kwin_failed or not self._is_wayland or self._kwin_dbus is None:
            return None
        if self._kwin_iface is not None:
            return self._kwin_iface
        try:
            self._kwin_bus = self._kwin_dbus.SessionBus()
            obj = self._kwin_bus.get_object("org.kde.KWin", "/org/kde/KWin/ScreenShot2")
            self._kwin_iface = self._kwin_dbus.Interface(
                obj, "org.kde.KWin.ScreenShot2"
            )
            return self._kwin_iface
        except Exception as e:
            self._kwin_failed = True
            self._log_capture_error_once(
                "kwin_iface_failed", f"No se pudo inicializar captura D-Bus de KWin: {e}"
            )
            return None

    def _capture_with_kwin_dbus(self, monitor):
        iface = self._ensure_kwin_interface()
        if iface is None:
            return None

        r_fd, w_fd = os.pipe()
        try:
            options = self._kwin_dbus.Dictionary(
                {"native-resolution": self._kwin_dbus.Boolean(True)}, signature="sv"
            )
            results = iface.CaptureArea(
                self._kwin_dbus.Int32(monitor["left"]),
                self._kwin_dbus.Int32(monitor["top"]),
                self._kwin_dbus.UInt32(monitor["width"]),
                self._kwin_dbus.UInt32(monitor["height"]),
                options,
                self._kwin_dbus.types.UnixFd(w_fd),
            )
        except Exception as e:
            self._kwin_failed = True
            self._log_capture_error_once(
                "kwin_capture_failed", f"KWin ScreenShot2 no pudo capturar: {e}"
            )
            return None
        finally:
            try:
                os.close(w_fd)
            except Exception:
                pass

        try:
            results = dict(results or {})
            img_type = str(results.get("type", ""))
            width = int(results.get("width", monitor["width"]))
            height = int(results.get("height", monitor["height"]))
            stride = int(results.get("stride", width * 4))
            if img_type != "raw" or width < 1 or height < 1 or stride < width * 4:
                return None

            expected = stride * height
            raw = bytearray()
            while len(raw) < expected:
                chunk = os.read(r_fd, min(65536, expected - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            if len(raw) < expected:
                return None

            if stride == width * 4:
                packed = bytes(raw)
            else:
                packed_bytes = bytearray(width * height * 4)
                src = memoryview(raw)
                dst = memoryview(packed_bytes)
                row_size = width * 4
                for y in range(height):
                    src_start = y * stride
                    dst_start = y * row_size
                    dst[dst_start : dst_start + row_size] = src[src_start : src_start + row_size]
                packed = bytes(packed_bytes)

            surface = pygame.image.frombuffer(packed, (width, height), "BGRA")
            return surface.copy()
        except Exception as e:
            self._log_capture_error_once(
                "kwin_decode_failed", f"No se pudo decodificar captura de KWin: {e}"
            )
            return None
        finally:
            try:
                os.close(r_fd)
            except Exception:
                pass

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
        self._cleanup_pipewire()

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
            surface = self._capture_with_pipewire(monitor)
            if surface is not None:
                self._log_backend_once("pipewire")
            if surface is None:
                surface = self._capture_with_kwin_dbus(monitor)
            if surface is not None:
                self._log_backend_once("kwin_dbus")
            if surface is None:
                surface = self._capture_with_grim(monitor)
                if surface is not None:
                    self._log_backend_once("grim")
            if surface is None:
                surface = self._capture_with_spectacle(monitor)
                if surface is not None:
                    self._log_backend_once("spectacle")

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
        if self._is_wayland:
            surface = self._capture_with_external_backend(monitor)
            if surface is not None:
                return surface

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
