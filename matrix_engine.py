import pygame

class MatrixEngine:
    """
    A logical representation of the LED Matrix.
    Uses Pygame internally to allow drawing, rendering shapes, text, etc.
    and easily extract raw RGB byte streams for DDP.
    """
    def __init__(self, config):
        self.config = config
        self.width = config.get("matrix", {}).get("width", 16)
        self.height = config.get("matrix", {}).get("height", 16)
        self.fps = config.get("app", {}).get("fps", 30)
        
        self.preview_scale = config.get("app", {}).get("preview_scale", 30)
        self.preview_mode = config.get("app", {}).get("preview", True)
        
        pygame.init()
        
        # The internal drawing surface mapped 1:1 with actual LED matrix dimension
        self.surface = pygame.Surface((self.width, self.height))
        
        if self.preview_mode:
            self.screen = pygame.display.set_mode((self.width * self.preview_scale, self.height * self.preview_scale))
            pygame.display.set_caption("WLED Matrix Virtual Preview")
        
        self.clock = pygame.time.Clock()
        
    def clear(self, color=(0, 0, 0)):
        self.surface.fill(color)
        
    def get_pixel_data(self):
        """
        Retrieves RGB bytes in row-major order (top to bottom, left to right).
        This maps perfectly to WLED's default 2D rendering layout expectation.
        """
        return pygame.image.tostring(self.surface, "RGB", False)

    def update_preview(self):
        if self.preview_mode:
            # Scale up the 1:1 surface so we can see the individual pixels clearly
            pygame.transform.scale(
                self.surface, 
                (self.width * self.preview_scale, self.height * self.preview_scale), 
                self.screen
            )
            pygame.display.flip()

    def tick(self):
        """
        Updates the preview and manages the framerate tick.
        Returns False if the UI is closed.
        """
        self.update_preview()
        
        # Process Pygame events to keep the window responsive and handle exist
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
                
        self.clock.tick(self.fps)
        return True
