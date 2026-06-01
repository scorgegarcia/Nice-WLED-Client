import pygame
import math
from .base import BaseAnimation

class TestPattern(BaseAnimation):
    def __init__(self, engine):
        super().__init__(engine)
        
    def build_ui(self, layout):
        pass

    def render(self, t):
        w = self.engine.width
        h = self.engine.height
        
        # Paleta de 7 colores fundamentales para calibrar RGB LEDs
        colors = [
            (255, 0, 0),     # 1. Rojo puro
            (0, 255, 0),     # 2. Verde puro
            (0, 0, 255),     # 3. Azul puro
            (255, 255, 0),   # 4. Amarillo (R+G)
            (0, 255, 255),   # 5. Cian (G+B)
            (255, 0, 255),   # 6. Magenta (R+B)
            (255, 255, 255)  # 7. Blanco puro (R+G+B)
        ]
        
        col_w = w / len(colors)
        
        if col_w < 1:
            # Si el matrix no puede renderizar al menos 7 lineas de píxeles, se pinta de blanco
            self.engine.surface.fill((255, 255, 255))
            return

        # Dibujar bloques en secuencia matemática sin huecos
        for i, color in enumerate(colors):
            x_start = int(i * col_w)
            w_block = int((i + 1) * col_w) - x_start
            
            rect = pygame.Rect(x_start, 0, max(1, w_block), h)
            pygame.draw.rect(self.engine.surface, pygame.Color(*color), rect)
        
    def get_name(self):
        return "Patrón de Calibración 7 Colores (RGB / CMY / W)"
