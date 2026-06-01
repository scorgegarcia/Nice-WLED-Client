import math
import random
import pygame

from .base import BaseAnimation
from PyQt6.QtWidgets import QLabel, QSlider, QCheckBox, QHBoxLayout
from PyQt6.QtCore import Qt
from widgets.color_picker import ColorPickerWidget


class AuroraBoreal(BaseAnimation):
    """
    Animación tipo aurora: ondas suaves de color con destellos opcionales.
    Pensada para matrices pequeñas como 11x9, pero escala a cualquier tamaño.
    """

    def __init__(self, engine):
        super().__init__(engine)
        self.props.setdefault("speed", 6)          # 1 - 30
        self.props.setdefault("wave_size", 12)     # 1 - 30
        self.props.setdefault("brightness", 85)    # 5 - 100
        self.props.setdefault("sparkles", True)
        self.props.setdefault("sparkle_amount", 12) # 0 - 60
        self.props.setdefault("color_a", "#00ffaa")
        self.props.setdefault("color_b", "#7a00ff")
        self.props.setdefault("color_c", "#00aaff")

    def _safe_color(self, value, fallback):
        try:
            return pygame.Color(value)
        except Exception:
            return pygame.Color(fallback)

    def _mix(self, c1, c2, amount):
        amount = max(0.0, min(1.0, amount))
        inv = 1.0 - amount
        return (
            int(c1.r * inv + c2.r * amount),
            int(c1.g * inv + c2.g * amount),
            int(c1.b * inv + c2.b * amount),
        )

    def build_ui(self, layout):
        def add_slider(label, key, min_val, max_val):
            layout.addWidget(QLabel(label))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(min_val, max_val)
            slider.setValue(int(self.props[key]))

            def update(value):
                self.props[key] = int(value)
                self.save_props()

            slider.valueChanged.connect(update)
            layout.addWidget(slider)

        add_slider("Velocidad:", "speed", 1, 30)
        add_slider("Tamaño de onda:", "wave_size", 1, 30)
        add_slider("Brillo interno:", "brightness", 5, 100)
        add_slider("Cantidad de destellos:", "sparkle_amount", 0, 60)

        chk_sparkles = QCheckBox("Activar destellos")
        chk_sparkles.setChecked(bool(self.props["sparkles"]))

        def update_sparkles(state):
            self.props["sparkles"] = (state == 2)
            self.save_props()

        chk_sparkles.stateChanged.connect(update_sparkles)
        layout.addWidget(chk_sparkles)

        def add_color_input(label, key):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            picker = ColorPickerWidget(str(self.props[key]))
            picker.valueChanged.connect(lambda v: (self.props.update({key: v}), self.save_props()))
            row.addWidget(picker)
            layout.addLayout(row)

        add_color_input("Color A:", "color_a")
        add_color_input("Color B:", "color_b")
        add_color_input("Color C:", "color_c")

    def render(self, t):
        w = self.engine.width
        h = self.engine.height

        speed = self.props.get("speed", 6) / 18.0
        wave_size = max(1, self.props.get("wave_size", 12)) / 4.0
        brightness = max(0.05, min(1.0, self.props.get("brightness", 85) / 100.0))

        color_a = self._safe_color(self.props.get("color_a", "#00ffaa"), "#00ffaa")
        color_b = self._safe_color(self.props.get("color_b", "#7a00ff"), "#7a00ff")
        color_c = self._safe_color(self.props.get("color_c", "#00aaff"), "#00aaff")

        time = t * speed

        for y in range(h):
            for x in range(w):
                nx = x / max(1, w - 1)
                ny = y / max(1, h - 1)

                wave_1 = math.sin((nx * wave_size * 4.0) + (time * 0.16) + math.sin(ny * 4.0 + time * 0.07))
                wave_2 = math.sin((ny * wave_size * 5.5) - (time * 0.11) + math.cos(nx * 5.0 + time * 0.05))
                glow = (wave_1 + wave_2 + 2.0) / 4.0

                # Más luz hacia la zona central/baja, como cortinas de aurora.
                vertical_mask = 1.0 - abs((ny * 1.35) - 0.75)
                vertical_mask = max(0.0, min(1.0, vertical_mask))

                intensity = max(0.0, min(1.0, (glow * 0.75 + vertical_mask * 0.55) * brightness))

                if glow < 0.5:
                    base = self._mix(color_a, color_c, glow * 2.0)
                else:
                    base = self._mix(color_c, color_b, (glow - 0.5) * 2.0)

                # Fondo oscuro azulado para que no se vea apagado totalmente.
                r = int(base[0] * intensity)
                g = int(base[1] * intensity)
                b = int(base[2] * intensity + 8 * (1.0 - intensity))
                self.engine.surface.set_at((x, y), (r, g, b))

        if self.props.get("sparkles", True):
            amount = int(self.props.get("sparkle_amount", 12))
            rng = random.Random(t // 2)  # estable por frame par, evita parpadeo demasiado nervioso
            for _ in range(amount):
                if rng.random() < 0.55:
                    sx = rng.randrange(0, max(1, w))
                    sy = rng.randrange(0, max(1, h))
                    twinkle = int(120 + 135 * abs(math.sin(t * 0.2 + sx * 1.7 + sy * 2.3)))
                    self.engine.surface.set_at((sx, sy), (twinkle, twinkle, min(255, twinkle + 25)))

    def get_name(self):
        return "Aurora Boreal"
