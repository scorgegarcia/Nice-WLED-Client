import pygame
import mido
import random
import math
from .base import BaseAnimation
from PyQt6.QtWidgets import QLabel, QSpinBox, QHBoxLayout, QComboBox, QCheckBox
from PyQt6.QtCore import Qt
from widgets.color_picker import ColorPickerWidget

class MidiKeyboard(BaseAnimation):
    def __init__(self, engine):
        super().__init__(engine)
        self.props.setdefault("port", "")
        self.props.setdefault("start_key", 36)
        self.props.setdefault("end_key", 84)
        self.props.setdefault("random_color", False)
        
        self.props.setdefault("rows", 1)
        self.props.setdefault("start_top", False)
        
        self.props.setdefault("bg_color", "#000000")
        self.props.setdefault("press_color", "#ff0000")
        self.props.setdefault("white_color", "#aaaaaa")
        self.props.setdefault("black_color", "#333333")
        
        self.port = None
        self.keys_pressed = {}
        
    def open_port(self):
        if self.port:
            self.port.close()
            self.port = None
        
        inputs = mido.get_input_names()
        target = self.props.get("port", "")
        
        best_match = None
        if target:
            for p in inputs:
                if target in p:
                    best_match = p
                    break
                    
        if best_match:
            try:
                self.port = mido.open_input(best_match, callback=self.midi_callback)
            except Exception as e:
                print("Error abriendo puerto MIDI:", e)

    def midi_callback(self, message):
        if message.type == 'note_on':
            if message.velocity > 0:
                if self.props["random_color"]:
                    c = pygame.Color(0)
                    c.hsva = (random.randint(0, 359), 100, 100, 100)
                else:
                    try: c = pygame.Color(self.props["press_color"])
                    except: c = pygame.Color("white")
                self.keys_pressed[message.note] = c
            else:
                self.keys_pressed.pop(message.note, None)
                
        elif message.type == 'note_off':
            self.keys_pressed.pop(message.note, None)

    def on_active(self):
        self.open_port()

    def on_inactive(self):
        if self.port:
            self.port.close()
            self.port = None
        self.keys_pressed.clear()

    def build_ui(self, layout):
        # Puerto MIDI
        layout.addWidget(QLabel("Puerto Entrada MIDI:"))
        cb_ports = QComboBox()
        cb_ports.addItem("Ninguno")
        for p in mido.get_input_names(): cb_ports.addItem(p)
            
        current = self.props.get("port", "")
        idx = cb_ports.findText(current, Qt.MatchFlag.MatchContains)
        if idx >= 0: cb_ports.setCurrentIndex(idx)
        
        def update_port(text):
            self.props["port"] = "" if text == "Ninguno" else text
            self.save_props()
            self.open_port()
        cb_ports.currentTextChanged.connect(update_port)
        layout.addWidget(cb_ports)
        
        # Mapeo de Teclas
        h_keys = QHBoxLayout()
        h_keys.addWidget(QLabel("Nota Inicio:"))
        sp_start = QSpinBox()
        sp_start.setRange(0, 127)
        sp_start.setValue(self.props["start_key"])
        h_keys.addWidget(sp_start)
        
        h_keys.addWidget(QLabel("Nota Fin:"))
        sp_end = QSpinBox()
        sp_end.setRange(0, 127)
        sp_end.setValue(self.props["end_key"])
        h_keys.addWidget(sp_end)
        layout.addLayout(h_keys)
        
        def update_start(v): self.props["start_key"] = v; self.save_props()
        def update_end(v): self.props["end_key"] = v; self.save_props()
        sp_start.valueChanged.connect(update_start)
        sp_end.valueChanged.connect(update_end)
        
        # Capas (Teclados Verticales)
        h_rows = QHBoxLayout()
        h_rows.addWidget(QLabel("Teclados Verticales (Filas):"))
        sp_rows = QSpinBox()
        sp_rows.setRange(1, 10)
        sp_rows.setValue(self.props["rows"])
        def update_rows(v): self.props["rows"] = v; self.save_props()
        sp_rows.valueChanged.connect(update_rows)
        h_rows.addWidget(sp_rows)
        layout.addLayout(h_rows)
        
        chk_top = QCheckBox("Empezar primera nota desde la Cima (Top)")
        chk_top.setChecked(self.props["start_top"])
        def update_top(state): self.props["start_top"] = (state == 2); self.save_props()
        chk_top.stateChanged.connect(update_top)
        layout.addWidget(chk_top)
        
        # Colores Pintura
        h_col1 = QHBoxLayout()
        h_col1.addWidget(QLabel("Tecla Blanca:"))
        picker_w = ColorPickerWidget(self.props["white_color"])
        picker_w.valueChanged.connect(lambda v: (self.props.update({"white_color": v}), self.save_props()))
        h_col1.addWidget(picker_w)

        h_col1.addWidget(QLabel("Tecla Negra:"))
        picker_b = ColorPickerWidget(self.props["black_color"])
        picker_b.valueChanged.connect(lambda v: (self.props.update({"black_color": v}), self.save_props()))
        h_col1.addWidget(picker_b)
        layout.addLayout(h_col1)

        h_col2 = QHBoxLayout()
        h_col2.addWidget(QLabel("Presionada:"))
        picker_p = ColorPickerWidget(self.props["press_color"])
        picker_p.valueChanged.connect(lambda v: (self.props.update({"press_color": v}), self.save_props()))
        h_col2.addWidget(picker_p)

        h_col2.addWidget(QLabel("Fondo:"))
        picker_bg = ColorPickerWidget(self.props["bg_color"])
        picker_bg.valueChanged.connect(lambda v: (self.props.update({"bg_color": v}), self.save_props()))
        h_col2.addWidget(picker_bg)
        layout.addLayout(h_col2)
        
        chk_rnd = QCheckBox("Usar Color de Disparo Aleatorio por Tecla")
        chk_rnd.setChecked(self.props["random_color"])
        def update_rnd(state): self.props["random_color"] = (state == 2); self.save_props()
        chk_rnd.stateChanged.connect(update_rnd)
        layout.addWidget(chk_rnd)

    def render(self, t):
        try: c_bg = pygame.Color(self.props["bg_color"])
        except: c_bg = pygame.Color("black")
        try: c_w = pygame.Color(self.props["white_color"])
        except: c_w = pygame.Color("#aaaaaa")
        try: c_b = pygame.Color(self.props["black_color"])
        except: c_b = pygame.Color("#333333")
            
        self.engine.surface.fill(c_bg)
        
        s = self.props["start_key"]
        e = self.props["end_key"]
        rows = max(1, self.props["rows"])
        start_top = self.props["start_top"]
        
        total_notes = max(1, e - s + 1)
        notes_per_row = math.ceil(total_notes / rows)
        if notes_per_row < 1: notes_per_row = 1
        
        strip_h = self.engine.height / rows
        note_w = self.engine.width / notes_per_row
        
        black_keys = {1, 3, 6, 8, 10}
        
        for note in range(s, e + 1):
            idx = note - s
            row = idx // notes_per_row
            col = idx % notes_per_row
            
            if start_top:
                y = row * strip_h
            else:
                y = (rows - 1 - row) * strip_h
                
            x = col * note_w
            
            # Check pattern for Black/White key
            is_black = (note % 12) in black_keys
            key_color = c_b if is_black else c_w
            
            # Check if active
            if note in self.keys_pressed:
                key_color = self.keys_pressed[note]
                
            if is_black:
                # Dibujar tecla negra en la mitad superior
                h_black = strip_h / 2
                rect_black = pygame.Rect(int(x), int(y), max(1, math.ceil(note_w)), max(1, math.ceil(h_black)))
                pygame.draw.rect(self.engine.surface, key_color, rect_black)
                
                # Rellenar la mitad inferior con la tecla blanca que está a su derecha (note + 1)
                right_color = c_w
                if (note + 1) in self.keys_pressed:
                    right_color = self.keys_pressed[note + 1]
                    
                rect_white_bottom = pygame.Rect(int(x), int(y + h_black), max(1, math.ceil(note_w)), max(1, math.ceil(h_black)))
                pygame.draw.rect(self.engine.surface, right_color, rect_white_bottom)
            else:
                # Tecla blanca entera
                rect = pygame.Rect(int(x), int(y), max(1, math.ceil(note_w)), max(1, math.ceil(strip_h)))
                pygame.draw.rect(self.engine.surface, key_color, rect)

    def get_name(self):
        return "Teclado Piano Estructurado"
