import pygame
from .base import BaseAnimation
from PyQt6.QtWidgets import QLabel, QSlider, QCheckBox
from PyQt6.QtCore import Qt

class Rainbow(BaseAnimation):
    def __init__(self, engine):
        super().__init__(engine)
        self.props.setdefault("speed", 5)
        self.props.setdefault("diagonal", True)
        
    def build_ui(self, layout):
        layout.addWidget(QLabel("Velocidad del Efecto:"))
        
        sl_speed = QSlider(Qt.Orientation.Horizontal)
        sl_speed.setRange(1, 40)
        sl_speed.setValue(self.props["speed"])
        def update_speed(val):
            self.props["speed"] = val
            self.save_props()
        sl_speed.valueChanged.connect(update_speed)
        layout.addWidget(sl_speed)
        
        chk_diag = QCheckBox("Dirección Diagonal")
        chk_diag.setChecked(self.props["diagonal"])
        def update_diag(state):
            self.props["diagonal"] = (state == 2)
            self.save_props()
        chk_diag.stateChanged.connect(update_diag)
        layout.addWidget(chk_diag)

    def render(self, t):
        s = self.props["speed"]
        diag = self.props["diagonal"]
        for y in range(self.engine.height):
            for x in range(self.engine.width):
                if diag:
                    hue = (x * 12 + y * 12 + t * s) % 360
                else:
                    hue = (x * 12 + t * s) % 360
                color = pygame.Color(0)
                color.hsva = (hue, 100, 100, 100)
                self.engine.surface.set_at((x, y), color)
                
    def get_name(self):
        return "Arcoíris Dinámico"
