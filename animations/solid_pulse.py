from .base import BaseAnimation
import math

class PulseColor(BaseAnimation):
    def render(self, t):
        # Animación sencilla de parpadeo suave pulsante usando seno
        v = int((math.sin(t * 0.1) + 1.0) * 127) # 0 a 254
        
        # Color cyan pulsante
        self.engine.surface.fill((0, v, v))
        
    def get_name(self):
        return "Cian Pulsante"
