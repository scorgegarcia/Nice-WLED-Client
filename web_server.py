import threading
import logging
import time
import base64
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

_command_queue = None
_state_dict = None
_state_lock = threading.Lock()
_cached_preview = None
_preview_cond = threading.Condition()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state')
def get_state():
    if _state_dict is None:
        return jsonify({})
    with _state_lock:
        state = {k: v for k, v in _state_dict.items() if k != 'preview_qimage'}
    return jsonify(state)

@app.route('/api/preview')
def get_preview():
    global _cached_preview
    with _preview_cond:
        data = _cached_preview
    if data is None:
        return ('', 204)
    return data, 200, {'Content-Type': 'image/png', 'Cache-Control': 'no-cache'}

@app.route('/api/preview/stream')
def get_preview_stream():
    def generate():
        last_preview = None
        while True:
            with _preview_cond:
                # Wait for a new frame, timeout after 1.0 second to allow checking loop/connection status
                _preview_cond.wait(timeout=1.0)
                data = _cached_preview
            if data is not None and data != last_preview:
                last_preview = data
                try:
                    b64_data = base64.b64encode(data).decode('utf-8')
                    yield f"data: {b64_data}\n\n"
                except (GeneratorExit, Exception):
                    break
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/command', methods=['POST'])
def handle_command():
    if _command_queue is None:
        return jsonify({"status": "error"}), 500
    cmd = request.json
    if cmd:
        _command_queue.put(cmd)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route('/api/connection', methods=['POST'])
def set_connection():
    if _state_dict is None:
        return jsonify({"status": "error"}), 500
    cmd = request.json
    if cmd:
        _command_queue.put({**cmd, "action": "set_connection"})
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route('/api/color_correction', methods=['POST'])
def set_color_correction():
    if _state_dict is None:
        return jsonify({"status": "error"}), 500
    cmd = request.json
    if cmd:
        _command_queue.put({**cmd, "action": "set_color_correction"})
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route('/api/anim_props', methods=['POST'])
def set_anim_props():
    if _state_dict is None:
        return jsonify({"status": "error"}), 500
    cmd = request.json
    if cmd:
        _command_queue.put({**cmd, "action": "set_anim_props"})
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route('/api/toggle_plugin', methods=['POST'])
def toggle_plugin():
    if _state_dict is None:
        return jsonify({"status": "error"}), 500
    cmd = request.json
    if cmd:
        _command_queue.put({**cmd, "action": "toggle_plugin"})
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route('/api/color_profiles', methods=['GET'])
def get_color_profiles():
    if _state_dict is None:
        return jsonify({"profiles": []})
    return jsonify({"profiles": _state_dict.get("color_profiles", [])})

@app.route('/api/color_profiles', methods=['POST'])
def save_color_profile():
    if _state_dict is None:
        return jsonify({"status": "error"}), 500
    cmd = request.json
    if cmd:
        _command_queue.put({**cmd, "action": "save_color_profile"})
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route('/api/color_profiles/load', methods=['POST'])
def load_color_profile():
    if _state_dict is None:
        return jsonify({"status": "error"}), 500
    cmd = request.json
    if cmd:
        _command_queue.put({**cmd, "action": "load_color_profile"})
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

def run_flask():
    app.run(host='0.0.0.0', port=9020, debug=False, use_reloader=False)

def start_web_server(command_queue, state_dict, qimage_getter=None):
    global _command_queue, _state_dict, _cached_preview
    _command_queue = command_queue
    _state_dict = state_dict

    if qimage_getter is not None:
        def preview_loop():
            global _cached_preview
            from PyQt6.QtCore import QBuffer, QIODevice, QByteArray
            while True:
                try:
                    qimg = qimage_getter()
                    if qimg is not None:
                        buf = QBuffer()
                        buf.open(QIODevice.OpenModeFlag.WriteOnly)
                        qimg.save(buf, "PNG")
                        raw = bytes(buf.data())
                        with _preview_cond:
                            _cached_preview = raw
                            _preview_cond.notify_all()
                except:
                    pass
                time.sleep(0.2)
        threading.Thread(target=preview_loop, daemon=True).start()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
