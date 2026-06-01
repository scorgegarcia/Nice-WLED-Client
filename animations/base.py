import json
import os


class BaseAnimation:
    """
    Clase base para todos los plugins de animación en WLED.
    Cada plugin guarda sus props en su propio archivo:
      animations/<ClassName>.props.json
    """
    def __init__(self, engine):
        self.engine = engine
        self.config = engine.config

        self.props_file = os.path.join(
            "animations", f"{self.__class__.__name__}.props.json"
        )

        self.props = self._load_props()

        # Migración: si existían props viejos en config.json, importarlos
        # (solo si el archivo nuevo no tiene datos)
        if not self.props:
            self._migrate_from_config()

    def _load_props(self):
        """Carga props desde el archivo individual del plugin."""
        try:
            if os.path.exists(self.props_file):
                with open(self.props_file, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _migrate_from_config(self):
        """Intenta migrar props antiguos desde config.json."""
        try:
            anim_props = self.config.get("anim_props", {})
            old = anim_props.get(self.__class__.__name__, {})
            if old:
                self.props = dict(old)
                self.save_props()
        except Exception:
            pass

    def setdefault(self, key, default):
        """Equivalente a dict.setdefault, para uso en los plugins."""
        if key not in self.props:
            self.props[key] = default
        return self.props[key]

    def save_props(self):
        """Escribe los props actuales en el archivo individual del plugin."""
        try:
            with open(self.props_file, "w") as f:
                json.dump(self.props, f, indent=4)
        except Exception:
            pass

    def on_active(self):
        """Se llama cuando se selecciona esta animación en la interfaz."""
        pass

    def on_inactive(self):
        """Se llama cuando se cambia a otra animación o se cierra la aplicación."""
        pass

    def build_ui(self, layout):
        """
        Permite que el plugin inyecte PyQt6 Widgets al panel de la IU.
        :param layout: QVBoxLayout donde meter los controles.
        """
        pass

    def render(self, t):
        """
        Función que se llama en cada frame para dibujar sobre
        self.engine.surface. El parámetro 't' es el tiempo.
        """
        pass

    def get_name(self):
        return self.__class__.__name__
