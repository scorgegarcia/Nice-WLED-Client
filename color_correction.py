import os
import json

class ColorCorrector:
    def __init__(self):
        self.r_max = 255
        self.g_max = 255
        self.b_max = 255
        
        self.brightness = 0.0  # -1.0 to 1.0 (adds direct constant baseline)
        self.contrast = 1.0    # 0.0 to 2.0 (multiplier scaling distance from mid-grey)
        self.gamma = 1.0       # 0.1 to 3.0 (power curve exponential mapping)
        self.master_dimmer = 1.0 # 0.0 to 1.0 (multiplies final output)
        
        self._cache_luts()
        
    def _cache_luts(self):
        def map_color(i, c_max):
            # Normalizar a 0.0 - 1.0
            c = i / 255.0
            
            # Contraste (Desplazamiento desde el punto central de exposición 0.5)
            c = (c - 0.5) * self.contrast + 0.5
            
            # Brillo (Desplazamiento base matemático total de la señal)
            c = c + self.brightness
            
            # Calibración nivel RGB puro
            c = c * (c_max / 255.0)
            
            # Clamp limits to stay in physical RGB scope
            c = max(0.0, min(1.0, c))
            
            # Master Dimmer
            c = c * self.master_dimmer
            
            # Corrección Gamma (Decaimiento exponencial de la curva óptica, ideal ~2.2)
            if self.gamma != 1.0 and c > 0:
                c = c ** self.gamma
                
            return int(c * 255)
            
        self.r_lut = bytes(map_color(i, self.r_max) for i in range(256))
        self.g_lut = bytes(map_color(i, self.g_max) for i in range(256))
        self.b_lut = bytes(map_color(i, self.b_max) for i in range(256))
        
    def set_levels(self, r, g, b, brightness=0.0, contrast=1.0, gamma=1.0):
        self.r_max = max(0, min(255, r))
        self.g_max = max(0, min(255, g))
        self.b_max = max(0, min(255, b))
        self.brightness = brightness
        self.contrast = contrast
        self.contrast = contrast
        self.gamma = gamma
        self._cache_luts()
        
    def set_master_dimmer(self, dimmer):
        self.master_dimmer = max(0.0, min(1.0, dimmer))
        self._cache_luts()
        
    def process(self, pixel_bytes):
        res = bytearray(len(pixel_bytes))
        res[0::3] = pixel_bytes[0::3].translate(self.r_lut)
        res[1::3] = pixel_bytes[1::3].translate(self.g_lut)
        res[2::3] = pixel_bytes[2::3].translate(self.b_lut)
        return bytes(res)

class ProfileManager:
    def __init__(self, dir_name="color_profiles"):
        self.dir_name = dir_name
        if not os.path.exists(self.dir_name):
            os.makedirs(self.dir_name)
            
    def get_profiles(self):
        profiles = []
        for f in os.listdir(self.dir_name):
            if f.endswith(".json"):
                profiles.append(f[:-5])
        return sorted(profiles)
        
    def save(self, name, r, g, b, bri=0, cont=100, gam=100):
        path = os.path.join(self.dir_name, f"{name}.json")
        with open(path, "w") as f:
            json.dump({"r": r, "g": g, "b": b, "bri": bri, "cont": cont, "gam": gam}, f, indent=4)
            
    def load(self, name):
        path = os.path.join(self.dir_name, f"{name}.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
                return (
                    data.get("r", 255), data.get("g", 255), data.get("b", 255),
                    data.get("bri", 0), data.get("cont", 100), data.get("gam", 100)
                )
        return 255, 255, 255, 0, 100, 100
