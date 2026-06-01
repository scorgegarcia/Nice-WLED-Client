import sys
import os
import json
import importlib
import inspect
import pygame
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QFormLayout, QMessageBox, QGroupBox,
    QComboBox, QScrollArea, QSlider, QCheckBox
)
from PyQt6.QtCore import QTimer, Qt, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QPixmap

from widgets.color_picker import ColorPickerWidget
from ddp_sender import DDPSender
from matrix_engine import MatrixEngine
from animations.base import BaseAnimation
from color_correction import ColorCorrector, ProfileManager
from web_server import start_web_server
import queue

def load_config(path="config.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {"wled": {"ip": "192.168.1.100", "port": 4048}, "matrix": {"width": 16, "height": 16}, "app": {"fps": 30}}

def save_config(config, path="config.json"):
    try:
        with open(path, "w") as f:
            json.dump(config, f, indent=4)
    except: pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WLED Animador y Capturador")
        
        self.config = load_config()
        self.config.setdefault("app", {})["preview"] = False
        
        self.engine = MatrixEngine(self.config)
        self.sender = DDPSender(
             self.config.get("wled", {}).get("ip", "192.168.1.100"), 
             self.config.get("wled", {}).get("port", 4048)
        )
        
        self.t = 0 
        self.is_paused = False
        self.is_blackout = False
        self.all_animations = []
        self.active_animations = []
        self.current_anim_index = 0
        
        self.command_queue = queue.Queue()
        self.corrector = ColorCorrector()
        self.profile_mgr = ProfileManager()

        self.web_state = {
            "is_paused": False,
            "is_blackout": False,
            "current_anim_index": 0,
            "animations": [],
            "master_dimmer": 100,
            "connection": {
                "ip": self.config.get("wled", {}).get("ip", "192.168.1.100"),
                "width": self.config.get("matrix", {}).get("width", 16),
                "height": self.config.get("matrix", {}).get("height", 16),
            },
            "color_correction": dict(self.config.get("color_correction", {"r":255, "g":255, "b":255, "bri":0, "cont":100, "gam":100})),
            "anim_props": {},
            "active_plugins": dict(self.config.get("active_plugins", {})),
            "color_profiles": self.profile_mgr.get_profiles(),
        }
        
        c_cfg = self.config.get("color_correction", {"r": 255, "g": 255, "b": 255, "bri": 0, "cont": 100, "gam": 100})
        self.corrector.set_levels(
            c_cfg.get("r", 255), c_cfg.get("g", 255), c_cfg.get("b", 255), 
            c_cfg.get("bri", 0)/100.0, c_cfg.get("cont", 100)/100.0, c_cfg.get("gam", 100)/100.0
        )
        
        self._init_ui()
        self.load_animations()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(int(1000 / self.config.get("app", {}).get("fps", 30)))
        
        start_web_server(self.command_queue, self.web_state, lambda: getattr(self, '_web_preview_qimg', None))
        
    def load_animations(self):
        self.all_animations.clear()
        self.active_animations.clear()
        self.anim_combo.blockSignals(True)
        self.anim_combo.clear()
        
        # Load active preferences
        active_prefs = self.config.setdefault("active_plugins", {})
        
        if not os.path.exists("animations"):
            os.makedirs("animations")
            
        # 1. Cargar e instanciar TODOS los plugins
        for item in os.listdir("animations"):
            if item.endswith(".py") and item not in ["__init__.py", "base.py"]:
                mod_name = f"animations.{item[:-3]}"
                try:
                    mod = importlib.import_module(mod_name)
                    importlib.reload(mod)
                    
                    for name, obj in inspect.getmembers(mod, inspect.isclass):
                        if issubclass(obj, BaseAnimation) and obj is not BaseAnimation:
                            instance = obj(self.engine)
                            self.all_animations.append(instance)
                except Exception as e:
                    print(f"Error cargando plugin {item}: {e}")

        # 2. Filtrar solo los ACTIVOS al combo y a la lista de reproducción
        for anim in self.all_animations:
            cls_name = anim.__class__.__name__
            is_active = active_prefs.get(cls_name, True)
            if is_active:
                self.active_animations.append(anim)
                self.anim_combo.addItem(anim.get_name())

        self.anim_combo.blockSignals(False)
        
        if len(self.active_animations) > 0:
            if self.current_anim_index >= len(self.active_animations):
                self.current_anim_index = 0
            self.anim_combo.setCurrentIndex(self.current_anim_index)
            self.active_animations[self.current_anim_index].on_active()
            self.instantiate_plugin_ui()
            
        self.refresh_plugin_manager_tab()

    def _init_ui(self):
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # ==========================================
        # Panel Izquierdo: Vista Previa y Transporte
        # ==========================================
        left_panel = QVBoxLayout()
        
        # 1. Preview
        preview_group = QGroupBox("Vista Previa (Matriz WLED)")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_display = QLabel()
        self.preview_display.setFixedSize(300, 300)
        self.preview_display.setStyleSheet("background-color: #000; border: 1px solid #555;")
        self.preview_display.setScaledContents(True)
        self.preview_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_display)
        left_panel.addWidget(preview_group)
        
        # 2. Global Transports
        transport_group = QGroupBox("Controles Globales")
        transport_layout = QVBoxLayout(transport_group)
        
        nav_layout = QHBoxLayout()
        btn_prev = QPushButton("◀")
        btn_prev.clicked.connect(self.prev_anim)
        btn_next = QPushButton("▶")
        btn_next.clicked.connect(self.next_anim)
        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(btn_next)
        transport_layout.addLayout(nav_layout)
        
        ctrl_layout = QHBoxLayout()
        self.btn_pause = QPushButton("⏸ Pausa")
        self.btn_pause.setCheckable(True)
        self.btn_pause.clicked.connect(self.toggle_pause)
        
        self.btn_blackout = QPushButton("⚫ Blackout")
        self.btn_blackout.setCheckable(True)
        self.btn_blackout.clicked.connect(self.toggle_blackout)
        self.btn_blackout.setStyleSheet("QPushButton:checked { background-color: #333; color: white; }")
        
        ctrl_layout.addWidget(self.btn_pause)
        ctrl_layout.addWidget(self.btn_blackout)
        transport_layout.addLayout(ctrl_layout)
        
        dimmer_layout = QHBoxLayout()
        dimmer_layout.addWidget(QLabel("☀️ Brillo:"))
        self.sl_master_dimmer = QSlider(Qt.Orientation.Horizontal)
        self.sl_master_dimmer.setRange(0, 100)
        self.sl_master_dimmer.setValue(100)
        self.sl_master_dimmer.valueChanged.connect(self.update_master_dimmer)
        dimmer_layout.addWidget(self.sl_master_dimmer)
        transport_layout.addLayout(dimmer_layout)
        
        left_panel.addWidget(transport_group)
        left_panel.addStretch()
        
        # ==========================================
        # Panel Derecho: Pestañas de Configuración
        # ==========================================
        self.tabs = QTabWidget()
        
        # Tab 1: Config general
        config_tab = QWidget()
        config_layout = QFormLayout(config_tab)
        
        self.input_ip = QLineEdit(self.config.get("wled", {}).get("ip", "192.168.1.100"))
        self.input_w = QLineEdit(str(self.config.get("matrix", {}).get("width", 16)))
        self.input_h = QLineEdit(str(self.config.get("matrix", {}).get("height", 16)))
        
        btn_save = QPushButton("Guardar y Conectar")
        btn_save.clicked.connect(self.save_and_apply)
        
        config_layout.addRow("Dirección IP (WLED):", self.input_ip)
        config_layout.addRow("Ancho de Matriz (X):", self.input_w)
        config_layout.addRow("Alto de Matriz (Y):", self.input_h)
        config_layout.addRow("", btn_save)
        
        # Tab 2: Control Plugins y Parámetros
        mode_tab = QWidget()
        mode_layout = QVBoxLayout(mode_tab)
        
        h_sel = QHBoxLayout()
        self.anim_combo = QComboBox()
        self.anim_combo.currentIndexChanged.connect(self.anim_changed)
        h_sel.addWidget(QLabel("<b>Seleccionar Motor:</b>"))
        h_sel.addWidget(self.anim_combo)
        
        btn_reload = QPushButton("↻")
        btn_reload.setToolTip("Recargar plugins python")
        btn_reload.clicked.connect(self.load_animations)
        h_sel.addWidget(btn_reload)
        mode_layout.addLayout(h_sel)
        
        # Contenedor Dinámico para las Propiedades del plugin!
        self.plugin_prop_group = QGroupBox("Parámetros del Efecto")
        self.plugin_layout = QVBoxLayout(self.plugin_prop_group)
        self.plugin_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.plugin_prop_group)
        
        mode_layout.addWidget(scroll)
        
        # Tab 3: Calibración de Color Profesional
        calib_tab = QWidget()
        calib_layout = QVBoxLayout(calib_tab)
        
        tut_label = QLabel(
            "<b>🎨 Ajustes Físicos y Científicos de Tira LED</b><br/>"
            "• <b>Límites Base (R, G, B):</b> Las tiras baratas tienen un blanco feo (un diodo resalta más). Emite 'Patrón RGBW', ajusta lentamente tu peor canal aquí (ej, baja el Verde/Azul) hasta que la escala blanca parezca Nieve en TÚ electrónica.<br/>"
            "• <b>Brillo (-100% a 100%):</b> Introduce o quita voltajes de electricidad básicos en todos los píxeles independientemente del tono.<br/>"
            "• <b>Contraste (0% a 200%):</b> Extiende luces y oscurece sombras. Las matrices WLED suelen ser muy planas; ¡subirlo embellece las grabaciones y colores vivos!<br/>"
            "• <b>Gamma (Hardware Visión):</b> El ser humano percibe los degradados y destellos de forma *logarítmica*, las cintas LED linealmente.<br/>Sube esto a <b>~2.2 (220%)</b> para simular un degradado realista ultra-suave natural. En `100%` ves un comportamiento lineal de robot sin procesamiento."
        )
        tut_label.setWordWrap(True)
        tut_label.setStyleSheet("border-radius: 8px; border: 1px solid #777; padding: 6px;")
        
        scroll_tut = QScrollArea()
        scroll_tut.setWidgetResizable(True)
        tut_label.setMaximumHeight(200) # Prevenir usar demasiado la pantalla
        scroll_tut.setWidget(tut_label)
        calib_layout.addWidget(scroll_tut)
        
        sl_layout = QFormLayout()
        
        def make_slider(name, range_min, range_max, val_init, suffix=""):
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(range_min, range_max)
            sl.setValue(val_init)
            lbl = QLabel(str(val_init) + suffix)
            lbl.setMinimumWidth(35)
            row = QHBoxLayout()
            row.addWidget(sl)
            row.addWidget(lbl)
            sl_layout.addRow(name, row)
            sl.valueChanged.connect(self.update_color_preview)
            return sl, lbl
            
        c_cfg = self.config.get("color_correction", {"r":255, "g":255, "b":255, "bri":0, "cont":100, "gam":100})
        
        self.sl_r, self.lbl_r_val = make_slider("Límite ROJO:", 0, 255, c_cfg.get("r",255))
        self.sl_g, self.lbl_g_val = make_slider("Límite VERDE:", 0, 255, c_cfg.get("g",255))
        self.sl_b, self.lbl_b_val = make_slider("Límite AZUL:", 0, 255, c_cfg.get("b",255))
        
        self.sl_bri, self.lbl_bri_val = make_slider("Brillo %:", -100, 100, c_cfg.get("bri",0), "%")
        self.sl_cont, self.lbl_cont_val = make_slider("Contraste %:", 0, 200, c_cfg.get("cont",100), "%")
        self.sl_gam, self.lbl_gam_val = make_slider("Optic Gamma (x 100):", 10, 300, c_cfg.get("gam",100))

        calib_layout.addLayout(sl_layout)
        
        prof_group = QGroupBox("Perfiles de Calibración Guardados")
        prof_layout = QHBoxLayout(prof_group)
        self.cb_profiles = QComboBox()
        self.cb_profiles.addItems(["-- Seleccionar --"] + self.profile_mgr.get_profiles())
        prof_layout.addWidget(self.cb_profiles)
        
        btn_load_prof = QPushButton("Cargar")
        btn_load_prof.clicked.connect(self.load_color_profile)
        prof_layout.addWidget(btn_load_prof)
        
        self.txt_prof_name = QLineEdit()
        self.txt_prof_name.setPlaceholderText("Nombre Perfil Nuevo")
        prof_layout.addWidget(self.txt_prof_name)
        
        btn_save_prof = QPushButton("Guardar")
        btn_save_prof.clicked.connect(self.save_color_profile)
        prof_layout.addWidget(btn_save_prof)
        calib_layout.addWidget(prof_group)
        
        calib_layout.addStretch()
        
        # Tab 4: Gestor de Plugins
        plugins_tab = QWidget()
        plugins_layout = QVBoxLayout(plugins_tab)
        plugins_layout.addWidget(QLabel("<b>🔌 Administrador Global de Plugins y Animaciones</b><br>Marca los plugins que quieres que estén disponibles en el Panel de Efecto."))
        
        self.plugins_scroll_content = QWidget()
        self.plugins_scroll_layout = QVBoxLayout(self.plugins_scroll_content)
        self.plugins_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        p_scroll = QScrollArea()
        p_scroll.setWidgetResizable(True)
        p_scroll.setWidget(self.plugins_scroll_content)
        
        plugins_layout.addWidget(p_scroll)

        self.tabs.addTab(config_tab, "Ajustes Conexión")
        self.tabs.addTab(mode_tab, "Panel del Efecto")
        self.tabs.addTab(calib_tab, "Corrección de Color")
        self.tabs.addTab(plugins_tab, "Gestor Plugins")
        
        main_layout.addLayout(left_panel, stretch=0)
        main_layout.addWidget(self.tabs, stretch=1)
        
        self.setCentralWidget(central_widget)
        self.resize(850, 480)
        
    def refresh_plugin_manager_tab(self):
        # Limpiar Layout
        self.clear_layout(self.plugins_scroll_layout)
        active_prefs = self.config.setdefault("active_plugins", {})
        
        for anim in self.all_animations:
            cls_name = anim.__class__.__name__
            name = anim.get_name()
            
            chk = QCheckBox(f"{name} ({cls_name})")
            chk.setChecked(active_prefs.get(cls_name, True))
            
            def make_toggle(c_name):
                return lambda state: self.toggle_plugin_active(c_name, state)
                
            chk.stateChanged.connect(make_toggle(cls_name))
            self.plugins_scroll_layout.addWidget(chk)
            
    def toggle_plugin_active(self, cls_name, state):
        self.config.setdefault("active_plugins", {})[cls_name] = (state == 2)
        save_config(self.config)
        self.web_state["active_plugins"] = dict(self.config.get("active_plugins", {}))
        # Recargar para refrescar la lista
        if hasattr(self, 'active_animations') and len(self.active_animations) > self.current_anim_index:
            self.active_animations[self.current_anim_index].on_inactive()
        self.load_animations()

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())
                    
    def instantiate_plugin_ui(self):
        self.clear_layout(self.plugin_layout)
        if hasattr(self, 'active_animations') and len(self.active_animations) > self.current_anim_index:
            try:
                self.active_animations[self.current_anim_index].build_ui(self.plugin_layout)
            except Exception as e:
                print(f"Error renderizando IU del plugin: {e}")
    
    # --- Controles ---
    def prev_anim(self):
        if len(self.active_animations) == 0: return
        new_index = (self.current_anim_index - 1) % len(self.active_animations)
        self.anim_combo.setCurrentIndex(new_index)

    def next_anim(self):
        if len(self.active_animations) == 0: return
        new_index = (self.current_anim_index + 1) % len(self.active_animations)
        self.anim_combo.setCurrentIndex(new_index)
        
    def anim_changed(self, index):
        if index >= 0 and index < len(self.active_animations):
            if hasattr(self, 'active_animations') and len(self.active_animations) > self.current_anim_index:
                self.active_animations[self.current_anim_index].on_inactive()
            self.current_anim_index = index
            self.t = 0
            self.active_animations[self.current_anim_index].on_active()
            self.instantiate_plugin_ui()

    def closeEvent(self, event):
        if len(self.active_animations) > 0 and self.current_anim_index < len(self.active_animations):
            self.active_animations[self.current_anim_index].on_inactive()
        super().closeEvent(event)

    def toggle_pause(self, checked):
        self.is_paused = checked
        self.btn_pause.setText("▶ Reanudar" if checked else "⏸ Pausa")
        
    def toggle_blackout(self, checked):
        self.is_blackout = checked
        if checked:
            self.btn_blackout.setText("🔴 Blackout ON")
        else:
            self.btn_blackout.setText("⚫ Blackout OFF")

    def save_and_apply(self):
        new_ip = self.input_ip.text()
        try:
            new_w = int(self.input_w.text())
            new_h = int(self.input_h.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Deben ser números.")
            return
            
        self.config["wled"]["ip"] = new_ip
        self.config["matrix"]["width"] = new_w
        self.config["matrix"]["height"] = new_h
        save_config(self.config)
        
        self.web_state["connection"] = {
            "ip": new_ip,
            "width": new_w,
            "height": new_h,
        }
        
        self.engine = MatrixEngine(self.config)
        self.sender = DDPSender(
            self.config.get("wled", {}).get("ip", "192.168.1.100"), 
            self.config.get("wled", {}).get("port", 4048)
        )
        self.load_animations()
        QMessageBox.information(self, "Listos", "Motor reconectado.")

    def update_color_preview(self, ignored=None):
        r, g, b = self.sl_r.value(), self.sl_g.value(), self.sl_b.value()
        bri, cont, gam = self.sl_bri.value(), self.sl_cont.value(), self.sl_gam.value()
        
        # Actualizar Etiquetas
        self.lbl_r_val.setText(str(r)); self.lbl_g_val.setText(str(g)); self.lbl_b_val.setText(str(b))
        self.lbl_bri_val.setText(f"{bri}%")
        self.lbl_cont_val.setText(f"{cont}%")
        self.lbl_gam_val.setText(str(gam))
        
        self.corrector.set_levels(r, g, b, bri/100.0, cont/100.0, gam/100.0)
        
        self.config["color_correction"] = {
            "r": r, "g": g, "b": b,
            "bri": bri, "cont": cont, "gam": gam,
            "last_profile": self.config.get("color_correction", {}).get("last_profile", "")
        }
        save_config(self.config)
        
        self.web_state["color_correction"] = {
            "r": r, "g": g, "b": b,
            "bri": bri, "cont": cont, "gam": gam,
            "last_profile": self.config.get("color_correction", {}).get("last_profile", "")
        }
        
    def load_color_profile(self):
        prof = self.cb_profiles.currentText()
        if prof and prof != "-- Seleccionar --":
            r, g, b, bri, cont, gam = self.profile_mgr.load(prof)
            
            # Detener temporalmente los triggers masivos 
            self.sl_r.blockSignals(True); self.sl_g.blockSignals(True); self.sl_b.blockSignals(True)
            self.sl_bri.blockSignals(True); self.sl_cont.blockSignals(True); self.sl_gam.blockSignals(True)
            
            self.sl_r.setValue(r); self.sl_g.setValue(g); self.sl_b.setValue(b)
            self.sl_bri.setValue(bri); self.sl_cont.setValue(cont); self.sl_gam.setValue(gam)
            
            self.sl_r.blockSignals(False); self.sl_g.blockSignals(False); self.sl_b.blockSignals(False)
            self.sl_bri.blockSignals(False); self.sl_cont.blockSignals(False); self.sl_gam.blockSignals(False)
            
            self.config["color_correction"]["last_profile"] = prof
            self.update_color_preview() # Manually trigger after load
            self.web_state["color_correction"] = dict(self.config.get("color_correction", {}))
            QMessageBox.information(self, "Cargado", f"Perfil '{prof}' cargado exitosamente.")
            
    def save_color_profile(self):
        name = self.txt_prof_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Introduce un nombre para guardar el perfil.")
            return
        
        r, g, b = self.sl_r.value(), self.sl_g.value(), self.sl_b.value()
        bri, cont, gam = self.sl_bri.value(), self.sl_cont.value(), self.sl_gam.value()
        
        self.profile_mgr.save(name, r, g, b, bri, cont, gam)
        
        self.cb_profiles.clear()
        self.cb_profiles.addItems(["-- Seleccionar --"] + self.profile_mgr.get_profiles())
        idx = self.cb_profiles.findText(name)
        if idx >= 0: self.cb_profiles.setCurrentIndex(idx)
        
        self.config["color_correction"]["last_profile"] = name
        save_config(self.config)
        self.web_state["color_profiles"] = self.profile_mgr.get_profiles()
        QMessageBox.information(self, "Guardado", f"Perfil '{name}' guardado.")
        
    def update_master_dimmer(self, val=None):
        if val is None:
            val = self.sl_master_dimmer.value()
        self.corrector.set_master_dimmer(val / 100.0)
        self.web_state["master_dimmer"] = val
        
    def update_frame(self):
        # Process Web Commands
        while not self.command_queue.empty():
            try:
                cmd = self.command_queue.get_nowait()
                action = cmd.get("action")
                if action == "set_anim":
                    idx = cmd.get("index", 0)
                    if 0 <= idx < len(self.active_animations):
                        self.anim_combo.setCurrentIndex(idx)
                elif action == "toggle_pause":
                    self.btn_pause.setChecked(not self.btn_pause.isChecked())
                    self.toggle_pause(self.btn_pause.isChecked())
                elif action == "toggle_blackout":
                    self.btn_blackout.setChecked(not self.btn_blackout.isChecked())
                    self.toggle_blackout(self.btn_blackout.isChecked())
                elif action == "set_dimmer":
                    val = cmd.get("value", 100)
                    self.sl_master_dimmer.setValue(int(val))
                elif action == "set_connection":
                    new_ip = cmd.get("ip", "")
                    new_w = cmd.get("width", 16)
                    new_h = cmd.get("height", 16)
                    if new_ip:
                        self.config["wled"]["ip"] = new_ip
                    self.config["matrix"]["width"] = int(new_w)
                    self.config["matrix"]["height"] = int(new_h)
                    save_config(self.config)
                    self.engine = MatrixEngine(self.config)
                    self.sender = DDPSender(
                        self.config.get("wled", {}).get("ip", "192.168.1.100"),
                        self.config.get("wled", {}).get("port", 4048)
                    )
                    self.load_animations()
                    self.web_state["connection"] = {
                        "ip": self.config["wled"]["ip"],
                        "width": self.config["matrix"]["width"],
                        "height": self.config["matrix"]["height"],
                    }
                elif action == "set_color_correction":
                    cc = self.config.get("color_correction", {})
                    cc["r"] = int(cmd.get("r", cc.get("r", 255)))
                    cc["g"] = int(cmd.get("g", cc.get("g", 255)))
                    cc["b"] = int(cmd.get("b", cc.get("b", 255)))
                    cc["bri"] = int(cmd.get("bri", cc.get("bri", 0)))
                    cc["cont"] = int(cmd.get("cont", cc.get("cont", 100)))
                    cc["gam"] = int(cmd.get("gam", cc.get("gam", 100)))
                    self.config["color_correction"] = cc
                    save_config(self.config)
                    self.corrector.set_levels(cc["r"], cc["g"], cc["b"], cc["bri"]/100.0, cc["cont"]/100.0, cc["gam"]/100.0)
                    self.web_state["color_correction"] = dict(cc)
                elif action == "set_anim_props":
                    plugin_name = cmd.get("plugin")
                    prop_key = cmd.get("key")
                    prop_value = cmd.get("value")
                    if plugin_name and prop_key and prop_value is not None:
                        for i, anim in enumerate(self.active_animations):
                            if anim.__class__.__name__ == plugin_name:
                                anim.props[prop_key] = prop_value
                                anim.save_props()
                                if i == self.current_anim_index:
                                    self.instantiate_plugin_ui()
                                    if hasattr(anim, "_apply_prop_to_window"):
                                        anim._apply_prop_to_window()
                                break
                elif action == "toggle_plugin":
                    cls_name = cmd.get("plugin")
                    state = cmd.get("active", True)
                    if cls_name:
                        self.config.setdefault("active_plugins", {})[cls_name] = state
                        save_config(self.config)
                        if hasattr(self, 'active_animations') and len(self.active_animations) > self.current_anim_index:
                            self.active_animations[self.current_anim_index].on_inactive()
                        self.load_animations()
                        self.web_state["active_plugins"] = dict(self.config.get("active_plugins", {}))
                elif action == "save_color_profile":
                    name = cmd.get("name", "").strip()
                    if name:
                        cc = self.config.get("color_correction", {})
                        self.profile_mgr.save(name, cc.get("r",255), cc.get("g",255), cc.get("b",255), cc.get("bri",0), cc.get("cont",100), cc.get("gam",100))
                        self.web_state["color_profiles"] = self.profile_mgr.get_profiles()
                elif action == "load_color_profile":
                    prof = cmd.get("name", "")
                    if prof:
                        r, g, b, bri, cont, gam = self.profile_mgr.load(prof)
                        cc = self.config.get("color_correction", {})
                        cc["r"], cc["g"], cc["b"] = r, g, b
                        cc["bri"], cc["cont"], cc["gam"] = bri, cont, gam
                        self.config["color_correction"] = cc
                        save_config(self.config)
                        self.corrector.set_levels(r, g, b, bri/100.0, cont/100.0, gam/100.0)
                        self.web_state["color_correction"] = dict(cc)
            except queue.Empty:
                pass
            except Exception as e:
                print(f"Error procesando comando web: {e}")
                
        # Update Web State
        self.web_state["is_paused"] = self.is_paused
        self.web_state["is_blackout"] = self.is_blackout
        self.web_state["current_anim_index"] = self.current_anim_index
        self.web_state["animations"] = [a.get_name() for a in self.active_animations]

        # Build anim_props from live plugin instances
        props_dict = {}
        for anim in self.active_animations:
            props_dict[anim.__class__.__name__] = dict(anim.props)
        self.web_state["anim_props"] = props_dict

        # Capture region info for screen capture preview on web
        sc_props = props_dict.get("ScreenCaptureAnim", {})
        if sc_props:
            self.web_state["capture_region"] = {
                "x": sc_props.get("pos_x", 0),
                "y": sc_props.get("pos_y", 0),
                "w": sc_props.get("width", 300),
                "h": sc_props.get("height", 200),
            }

        if not self.is_paused:
            self.t += 1
            
        self.engine.clear()
        
        if len(self.active_animations) > 0 and self.current_anim_index < len(self.active_animations):
            try:
                self.active_animations[self.current_anim_index].render(self.t)
            except Exception as e: pass
            
        pixel_data = self.engine.get_pixel_data()
        
        # Math-intensive Color Correction Pass
        corrected_data = self.corrector.process(pixel_data)
        
        if self.is_blackout:
            black_data = b'\x00' * len(corrected_data)
            self.sender.send_frame(black_data)
        else:
            self.sender.send_frame(corrected_data)
            
        w, h = self.engine.width, self.engine.height
        qimg = QImage(pixel_data, w, h, w * 3, QImage.Format.Format_RGB888)
        self.preview_display.setPixmap(QPixmap.fromImage(qimg).scaled(
            self.preview_display.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        ))
        
        # Store QImage for web preview
        self._web_preview_qimg = qimg.copy()
        
        pygame.event.pump()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: app.setStyle("Fusion") 
    except: pass
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
