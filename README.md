# Nice WLED Client

Cliente avanzado para **WLED** orientado a matrices LED 2D, con interfaz de escritorio en **PyQt6**, servidor de control web en **Flask** y motor gráfico en **Pygame**.

El proyecto permite:
- Reproducir animaciones en tiempo real sobre una matriz LED.
- Enviar frames por red usando **DDP (UDP)** hacia WLED.
- Ajustar color físicamente (RGB, brillo, contraste, gamma, dimmer maestro).
- Cargar/desactivar plugins de animación dinámicamente.
- Controlar el estado desde navegador (pausa, blackout, escena, parámetros, perfiles).
- Capturar región de pantalla y convertirla en contenido para la matriz LED.

## ¿Para quién es este repositorio?

- Personas que tienen una instalación WLED y quieren controlarla desde PC con más flexibilidad.
- Makers/creadores que quieren prototipar efectos personalizados en Python.
- Usuarios que necesitan calibración fina de color para escenarios reales (tiras con dominantes, brillo irregular, etc.).

## Funcionalidades principales

- **Salida DDP a WLED**: envía bytes RGB en chunks para respetar MTU de red.
- **Motor de matriz desacoplado**: representación lógica del panel (`width x height`) y render por frame.
- **Sistema de plugins**: cada animación es una clase Python basada en `BaseAnimation`.
- **Persistencia por plugin**: cada efecto guarda sus propiedades en `animations/<Plugin>.props.json`.
- **Corrección de color por LUT**: procesamiento rápido por canal usando tablas precalculadas.
- **Perfiles de color**: guardado/carga de presets en `color_profiles/*.json`.
- **Control local y remoto simultáneo**:
  - UI de escritorio (PyQt6).
  - API web + preview PNG/stream en `http://localhost:9020`.

## Arquitectura del proyecto

- `main.py`: aplicación principal (UI, ciclo de render, carga de plugins, envío a WLED).
- `matrix_engine.py`: superficie lógica de la matriz y utilidades de frame.
- `ddp_sender.py`: implementación de envío DDP por UDP.
- `color_correction.py`: corrección de color (LUT) y gestión de perfiles.
- `web_server.py`: servidor Flask para estado, comandos y preview remoto.
- `animations/`: plugins de animación.
- `widgets/`: widgets reutilizables para UI de plugins.
- `templates/index.html`: interfaz web básica de control.
- `config.json`: configuración global (WLED, matriz, FPS, corrección, plugins activos).

## Flujo de ejecución

1. Se carga `config.json`.
2. Se inicializa matriz lógica y emisor DDP.
3. Se cargan plugins de `animations/*.py`.
4. En cada frame:
   - Se procesa cola de comandos web.
   - Se renderiza animación activa.
   - Se aplica corrección de color.
   - Se envía frame a WLED por DDP.
   - Se actualiza preview local y web.

## Requisitos

- Python 3.10+ recomendado.
- WLED accesible por red local.
- Dependencias de `requirements.txt`:
  - `pygame`
  - `mss`
  - `mido`
  - `python-rtmidi`
  - `PyQt6`
  - `flask`

## Instalación

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuración inicial

Edita `config.json` según tu instalación:

- `wled.ip`: IP de tu dispositivo WLED.
- `wled.port`: puerto DDP (normalmente `4048`).
- `matrix.width` y `matrix.height`: resolución real de tu matriz.
- `app.fps`: tasa de actualización.

Ejemplo:

```json
{
  "wled": { "ip": "192.168.0.110", "port": 4048 },
  "matrix": { "width": 96, "height": 10 },
  "app": { "fps": 30, "preview": false, "preview_scale": 30 }
}
```

## Uso

### 1) Interfaz de escritorio

```bash
python main.py
```

Desde la app puedes:
- Cambiar animación activa.
- Pausar/reanudar.
- Activar blackout.
- Ajustar dimmer maestro.
- Configurar conexión y tamaño de matriz.
- Editar parámetros del plugin actual.
- Administrar plugins activos.
- Calibrar color y guardar/cargar perfiles.

### 2) Control web

Al ejecutar `main.py`, también se levanta un servidor Flask en:

- `http://localhost:9020`

APIs relevantes:
- `GET /api/state`: estado completo actual.
- `POST /api/command`: acciones globales (set_anim, pause, blackout, dimmer, etc.).
- `POST /api/connection`: actualizar IP/dimensiones.
- `POST /api/color_correction`: ajustar calibración.
- `POST /api/anim_props`: editar props de un plugin.
- `POST /api/toggle_plugin`: activar/desactivar plugin.
- `GET /api/preview`: último frame PNG.
- `GET /api/preview/stream`: stream tipo SSE en base64.

## Plugins de animación

El repositorio incluye plugins como:
- `TestPattern` (calibración RGB/CMY/W)
- `Rainbow`
- `PulseColor`
- `ScreenCaptureAnim`
- `MidiKeyboard`
- `NeonEqualizer`
- `AuroraBoreal`
- `HitannaNeonWave`

### Crear un plugin nuevo

1. Crea archivo en `animations/mi_plugin.py`.
2. Hereda de `BaseAnimation`.
3. Implementa al menos:
   - `render(self, t)`
   - `get_name(self)` (recomendado)
4. Opcional:
   - `build_ui(self, layout)` para controles en PyQt.
   - `on_active()` / `on_inactive()` para ciclo de vida.

El sistema lo detecta al recargar plugins desde la UI.

## Notas importantes

- El orden y mapeo físico de LEDs debe coincidir con cómo WLED interpreta la matriz 2D.
- Si ves colores incorrectos, usa la pestaña de corrección y el patrón de test.
- `ScreenCaptureAnim` utiliza coordenadas de pantalla reales del sistema operativo.
- Si no hay plugins activos, no habrá render útil hasta activar alguno.

## Estado actual del README

Este README fue generado a partir del código real del repositorio para reflejar su comportamiento actual y servir como documentación de entrada para cualquier colaborador.
