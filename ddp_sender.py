import socket
import struct

class DDPSender:
    """
    Implements the Distributed Display Protocol (DDP) for sending raw RGB 
    pixel data over UDP to a WLED controller.
    """
    def __init__(self, ip, port=4048):
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
    def send_frame(self, rgb_data):
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
