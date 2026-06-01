import math
import random
import pygame

from .base import BaseAnimation
from PyQt6.QtWidgets import QLabel, QSlider, QCheckBox, QHBoxLayout
from PyQt6.QtCore import Qt
from widgets.color_picker import ColorPickerWidget


class HitannaNeonWave(BaseAnimation):
    """
    Efecto tipo escenario/sintetizador: una onda neón central con barras
    tipo ecualizador y destellos. Funciona muy bien en matrices pequeñas
    como 11x9 porque usa formas grandes y contrastadas.
    """

    def __init__(self, engine):
        super().__init__(engine)
        self.props.setdefault("speed", 12)          # 1 - 40
        self.props.setdefault("wave_height", 70)    # 10 - 100
        self.props.setdefault("thickness", 2)       # 1 - 5
        self.props.setdefault("bars", True)
        self.props.setdefault("bar_amount", 85)     # 0 - 100
        self.props.setdefault("glow", 55)           # 0 - 100
        self.props.setdefault("sparkles", True)
        self.props.setdefault("sparkle_amount", 8)  # 0 - 40
        self.props.setdefault("mirror", True)
        self.props.setdefault("beat", 70)           # 0 - 100
        self.props.setdefault("color_a", "#ff007a") # magenta
        self.props.setdefault("color_b", "#00eaff") # cyan
        self.props.setdefault("color_c", "#fff000") # amarillo
        self.props.setdefault("bg_color", "#020008")

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

    def _scale_color(self, color, amount):
        amount = max(0.0, min(1.0, amount))
        return (
            int(color[0] * amount),
            int(color[1] * amount),
            int(color[2] * amount),
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
        add_slider("Altura de onda:", "wave_height", 10, 100)
        add_slider("Grosor de línea:", "thickness", 1, 5)
        add_slider("Intensidad de barras:", "bar_amount", 0, 100)
        add_slider("Glow / resplandor:", "glow", 0, 100)
        add_slider("Pulso beat:", "beat", 0, 100)
        add_slider("Cantidad de destellos:", "sparkle_amount", 0, 40)

        def add_checkbox(label, key):
            chk = QCheckBox(label)
            chk.setChecked(bool(self.props[key]))

            def update(state):
                self.props[key] = (state == 2)
                self.save_props()

            chk.stateChanged.connect(update)
            layout.addWidget(chk)

        add_checkbox("Barras tipo ecualizador", "bars")
        add_checkbox("Modo espejo vertical", "mirror")
        add_checkbox("Destellos neón", "sparkles")

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
        add_color_input("Fondo:", "bg_color")

    def render(self, t):
        w = self.engine.width
        h = self.engine.height

        color_a = self._safe_color(self.props.get("color_a", "#ff007a"), "#ff007a")
        color_b = self._safe_color(self.props.get("color_b", "#00eaff"), "#00eaff")
        color_c = self._safe_color(self.props.get("color_c", "#fff000"), "#fff000")
        bg = self._safe_color(self.props.get("bg_color", "#020008"), "#020008")

        speed = self.props.get("speed", 12) / 12.0
        wave_height = self.props.get("wave_height", 70) / 100.0
        thickness = max(1, int(self.props.get("thickness", 2)))
        glow = self.props.get("glow", 55) / 100.0
        beat_amount = self.props.get("beat", 70) / 100.0
        bar_amount = self.props.get("bar_amount", 85) / 100.0

        time = t * 0.12 * speed
        beat = (math.sin(time * 2.15) + 1.0) / 2.0
        beat = 0.35 + beat * beat_amount

        self.engine.surface.fill(bg)

        # 1) Barras verticales tipo ecualizador sintético
        if self.props.get("bars", True):
            for x in range(w):
                nx = x / max(1, w - 1)
                v1 = math.sin(time * 1.4 + x * 0.9)
                v2 = math.sin(time * 2.1 - x * 0.45)
                v3 = math.sin(time * 0.7 + x * 1.7)
                level = (v1 + v2 * 0.55 + v3 * 0.35 + 1.9) / 3.8
                level = max(0.0, min(1.0, level * bar_amount * beat))
                bar_h = int(round(level * h))

                mix_amount = (math.sin(time + nx * math.pi * 2.0) + 1.0) / 2.0
                bar_color = self._mix(color_a, color_b, mix_amount)
                if level > 0.72:
                    bar_color = self._mix(pygame.Color(*bar_color), color_c, (level - 0.72) / 0.28)

                for yy in range(bar_h):
                    y = h - 1 - yy
                    fade = 1.0 - (yy / max(1, h)) * 0.65
                    self.engine.surface.set_at((x, y), self._scale_color(bar_color, fade * 0.75))

        # 2) Onda central neón, como señal de sintetizador
        center = (h - 1) / 2.0
        amp = center * wave_height
        for x in range(w):
            nx = x / max(1, w - 1)
            wave = math.sin((nx * math.pi * 2.0) + time * 1.65)
            wave += 0.45 * math.sin((nx * math.pi * 5.0) - time * 0.9)
            wave /= 1.45

            y_float = center + wave * amp
            y_main = int(round(y_float))

            mix_amount = (x / max(1, w - 1) + time * 0.08) % 1.0
            line_color = self._mix(color_a, color_b, mix_amount)
            if beat > 0.85:
                line_color = self._mix(pygame.Color(*line_color), color_c, min(1.0, (beat - 0.85) * 2.0))

            for dy in range(-thickness, thickness + 1):
                y = y_main + dy
                if 0 <= y < h:
                    dist = abs(dy) / max(1, thickness)
                    power = (1.0 - dist * 0.55) * beat
                    self.engine.surface.set_at((x, y), self._scale_color(line_color, power))

                if self.props.get("mirror", True):
                    my = int(round((h - 1) - y_float)) + dy
                    if 0 <= my < h:
                        dist = abs(dy) / max(1, thickness)
                        power = (1.0 - dist * 0.75) * beat * 0.65
                        self.engine.surface.set_at((x, my), self._scale_color(line_color, power))

            # Glow alrededor de la onda
            if glow > 0:
                for gy in range(h):
                    d = abs(gy - y_float)
                    if d <= 3.0:
                        current = self.engine.surface.get_at((x, gy))
                        amount = max(0.0, (1.0 - d / 3.0) * glow * 0.45)
                        glow_color = self._scale_color(line_color, amount)
                        mixed = (
                            min(255, current.r + glow_color[0]),
                            min(255, current.g + glow_color[1]),
                            min(255, current.b + glow_color[2]),
                        )
                        self.engine.surface.set_at((x, gy), mixed)

        # 3) Destellos controlados, estables por frame para que no se vea sucio
        if self.props.get("sparkles", True):
            amount = int(self.props.get("sparkle_amount", 8))
            rng = random.Random((t // 2) + 1337)
            for _ in range(amount):
                if rng.random() < 0.45 + beat * 0.25:
                    sx = rng.randrange(0, max(1, w))
                    sy = rng.randrange(0, max(1, h))
                    sparkle = self._mix(color_b, color_c, rng.random())
                    intensity = 0.55 + rng.random() * 0.45
                    self.engine.surface.set_at((sx, sy), self._scale_color(sparkle, intensity))

    def get_name(self):
        return "Hitanna Neon Wave"
