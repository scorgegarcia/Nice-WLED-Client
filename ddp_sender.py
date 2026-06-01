import socket
import struct
import threading

class DDPSender:
    """
    Implements the Distributed Display Protocol (DDP) for sending raw RGB 
    pixel data over UDP to a WLED controller.
    """
    def __init__(self, ip, port=4048):
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setblocking(False)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
        except Exception:
            pass

        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._running = True
        self._latest_frame = None
        self._frames_enqueued = 0
        self._frames_sent = 0
        self._frames_dropped = 0
        self._tx_thread = threading.Thread(target=self._tx_loop, daemon=True)
        self._tx_thread.start()

    def _send_frame_sync(self, rgb_data):
        # DDP max payload is typically ~1440 bytes to stay under typical MTU constraints
        # 1440 bytes = 480 RGB pixels. We'll chunk the data if the matrix is too big.
        MAX_BYTES = 1440
        
        offset = 0
        total_bytes = len(rgb_data)
        
        while offset < total_bytes:
            chunk = rgb_data[offset:offset+MAX_BYTES]
            # Set push flag to True if this is the final chunk
            push_flag = (offset + len(chunk) >= total_bytes)
            
            # Flags: V1 (0x40) | Push (0x01)
            flags = 0x41 if push_flag else 0x40
            
            # sequence=0, data_type=1 (RGB), destination=0, offset=4 bytes (I), length=2 bytes (H)
            header = struct.pack('>BBBBIH', flags, 0, 1, 0, offset, len(chunk))

            self.sock.sendto(header + chunk, (self.ip, self.port))
            
            offset += len(chunk)

    def _tx_loop(self):
        while True:
            with self._cond:
                while self._running and self._latest_frame is None:
                    self._cond.wait(timeout=0.25)
                if not self._running:
                    break
                frame = self._latest_frame
                self._latest_frame = None

            if frame is None:
                continue

            try:
                self._send_frame_sync(frame)
                with self._lock:
                    self._frames_sent += 1
            except (BlockingIOError, InterruptedError):
                # Socket busy: drop this frame, keep UI thread smooth.
                pass
            except OSError:
                # Network hiccup: skip frame and continue.
                pass

    def send_frame(self, rgb_data):
        with self._cond:
            self._frames_enqueued += 1
            if self._latest_frame is not None:
                self._frames_dropped += 1
            self._latest_frame = rgb_data
            self._cond.notify()

    def get_stats(self):
        with self._lock:
            return {
                "enqueued": self._frames_enqueued,
                "sent": self._frames_sent,
                "dropped": self._frames_dropped,
            }

    def close(self):
        with self._cond:
            self._running = False
            self._latest_frame = None
            self._cond.notify_all()
        try:
            self._tx_thread.join(timeout=0.5)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
