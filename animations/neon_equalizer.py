import math
import random
import pygame

from .base import BaseAnimation
from PyQt6.QtWidgets import QLabel, QSlider, QCheckBox, QHBoxLayout
from PyQt6.QtCore import Qt
from widgets.color_picker import ColorPickerWidget


class NeonEqualizer(BaseAnimation):
    """
    Barras neon tipo visualizador musical abstracto.
    Diseñado para verse bien en matrices pequeñas, especialmente 9 px de alto,
    pero escala a cualquier resolución.
    """

    def __init__(self, engine):
        super().__init__(engine)
        self.props.setdefault("speed", 14)          # 1 - 40
        self.props.setdefault("bars", 7)            # 2 - 32
        self.props.setdefault("intensity", 90)      # 10 - 100
        self.props.setdefault("trail", 45)          # 0 - 100
        self.props.setdefault("mirror", True)
        self.props.setdefault("sparkles", True)
        self.props.setdefault("sparkle_amount", 6)  # 0 - 40
        self.props.setdefault("color_a", "#00f5ff")
        self.props.setdefault("color_b", "#ff00d4")
        self.props.setdefault("color_c", "#fff200")

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

        add_slider("Velocidad:", "speed", 1, 40)
        add_slider("Cantidad de barras:", "bars", 2, 32)
        add_slider("Intensidad:", "intensity", 10, 100)
        add_slider("Estela / glow:", "trail", 0, 100)
        add_slider("Destellos:", "sparkle_amount", 0, 40)

        chk_mirror = QCheckBox("Modo espejo desde el centro")
        chk_mirror.setChecked(bool(self.props["mirror"]))

        def update_mirror(state):
            self.props["mirror"] = (state == 2)
            self.save_props()

        chk_mirror.stateChanged.connect(update_mirror)
        layout.addWidget(chk_mirror)

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

    def _bar_height(self, bar_index, t, bar_count, max_h):
        speed = self.props.get("speed", 14) / 11.0
        time = t * speed

        # Mezcla ondas senoidales para simular música sin audio real.
        a = math.sin(time * 0.11 + bar_index * 1.37)
        b = math.sin(time * 0.057 + bar_index * 0.63 + math.sin(time * 0.023))
        c = math.sin(time * 0.17 - bar_index * 0.91)
        v = (a * 0.45 + b * 0.35 + c * 0.20 + 1.0) / 2.0

        # Pequeños acentos para que no se vea plano.
        pulse = 0.18 * abs(math.sin(time * 0.19 + bar_index * 2.1))
        v = max(0.0, min(1.0, v + pulse))

        # Mínimo 1 pixel visible para matrices de 9 px de alto.
        return max(1, int(round(1 + v * (max_h - 1))))

    def render(self, t):
        w = self.engine.width
        h = self.engine.height
        if w <= 0 or h <= 0:
            return

        intensity = max(0.10, min(1.0, self.props.get("intensity", 90) / 100.0))
        trail = max(0.0, min(1.0, self.props.get("trail", 45) / 100.0))
        mirror = bool(self.props.get("mirror", True))

        color_a = self._safe_color(self.props.get("color_a", "#00f5ff"), "#00f5ff")
        color_b = self._safe_color(self.props.get("color_b", "#ff00d4"), "#ff00d4")
        color_c = self._safe_color(self.props.get("color_c", "#fff200"), "#fff200")

        # Fondo con respiración azul muy oscura para que en escenario no se vea muerto.
        bg = int(4 + 5 * abs(math.sin(t * 0.035)))
        self.engine.surface.fill((0, 0, bg))

        bar_count = max(2, min(int(self.props.get("bars", 7)), max(2, w)))
        bar_w = w / bar_count
        max_h = h if not mirror else max(1, math.ceil(h / 2))
        center_y = (h - 1) / 2.0

        for i in range(bar_count):
            x0 = int(round(i * bar_w))
            x1 = int(round((i + 1) * bar_w))
            if x1 <= x0:
                x1 = x0 + 1

            bh = self._bar_height(i, t, bar_count, max_h)
            hue_mix = i / max(1, bar_count - 1)
            if hue_mix < 0.5:
                base = self._mix(color_a, color_b, hue_mix * 2.0)
            else:
                base = self._mix(color_b, color_c, (hue_mix - 0.5) * 2.0)

            for x in range(x0, min(x1, w)):
                for y in range(h):
                    if mirror:
                        dist = abs(y - center_y)
                        level = max(0.0, 1.0 - (dist / max(1, bh)))
                    else:
                        level = max(0.0, 1.0 - ((h - 1 - y) / max(1, bh)))
                        if y < h - bh:
                            level = 0.0

                    if level <= 0.0:
                        # Estela tenue alrededor de barras altas.
                        if trail <= 0:
                            continue
                        if mirror:
                            glow_dist = abs(y - center_y) - bh
                        else:
                            glow_dist = (h - bh) - y
                        if 0 < glow_dist <= max(1, h * 0.35):
                            level = (1.0 - glow_dist / max(1, h * 0.35)) * trail * 0.35
                        else:
                            continue

                    # Más brillante en el centro/punta de la barra.
                    power = min(1.0, (level ** 0.65) * intensity)
                    r = int(base[0] * power)
                    g = int(base[1] * power)
                    b = int(base[2] * power)
                    self.engine.surface.set_at((x, y), (r, g, b))

            # Pico blanco/amarillo muy pequeño: importante en 9 px de alto.
            peak_color = self._mix(color_c, pygame.Color("white"), 0.55)
            if mirror:
                top = max(0, int(round(center_y - bh)))
                bottom = min(h - 1, int(round(center_y + bh)))
                peak_rows = {top, bottom}
            else:
                peak_rows = {max(0, h - bh)}

            for x in range(x0, min(x1, w)):
                for py in peak_rows:
                    self.engine.surface.set_at((x, py), peak_color)

        if self.props.get("sparkles", True):
            amount = int(self.props.get("sparkle_amount", 6))
            rng = random.Random(t // 3)
            for _ in range(amount):
                if rng.random() < 0.45:
                    sx = rng.randrange(0, max(1, w))
                    sy = rng.randrange(0, max(1, h))
                    sparkle = int(150 + 105 * abs(math.sin(t * 0.21 + sx + sy)))
                    self.engine.surface.set_at((sx, sy), (sparkle, sparkle, sparkle))

    def get_name(self):
        return "Neon Equalizer"
