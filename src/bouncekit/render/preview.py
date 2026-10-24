"""Live preview window (FR-009).

The simulation stays fixed-step; only the pacing uses wall-clock time
(``pygame.time.Clock``). If drawing falls behind, playback slows down - steps
are never skipped.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from bouncekit.errors import ConfigError
from bouncekit.render.pygame_renderer import PygameRenderer

if TYPE_CHECKING:
    from bouncekit.scene import Scene


class Preview:
    """State and per-frame logic of the preview window.

    Keys: Space toggles pause, Right steps one frame while paused, R restarts
    from frame 0 (by calling ``make_scene`` again), Esc/Q or closing the window
    quits.
    """

    def __init__(self, make_scene: "Callable[[], Scene]", scale: float = 0.45) -> None:
        """Open the window and build the first scene.

        Raises:
            ConfigError: if ``scale`` is not a positive number.
        """
        if not scale > 0:
            raise ConfigError(f"preview scale must be > 0, got {scale}")
        pygame.init()
        self._make_scene = make_scene
        self.scale = scale
        self.paused = False
        self.quit = False
        self.clock = pygame.time.Clock()
        self.scene = make_scene()
        cfg = self.scene.config
        size = (max(1, round(cfg.width * scale)), max(1, round(cfg.height * scale)))
        self.screen = pygame.display.set_mode(size)
        self.renderer = PygameRenderer(cfg.width, cfg.height)

    def handle_event(self, event: "pygame.event.Event") -> None:
        """React to one pygame event."""
        if event.type == pygame.QUIT:
            self.quit = True
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                self.quit = True
            elif event.key == pygame.K_SPACE:
                self.paused = not self.paused
            elif event.key == pygame.K_RIGHT:
                if self.paused and self.scene.frame < self.scene.total_frames:
                    self.scene.step_frame()
            elif event.key == pygame.K_r:
                self.scene = self._make_scene()
                self.paused = False

    def is_quit(self) -> bool:
        """Whether the user asked to quit."""
        return self.quit

    def _title(self) -> str:
        scene = self.scene
        state = " - done" if scene.frame >= scene.total_frames else ""
        if self.paused:
            state += " - paused"
        return f"bouncekit {scene.frame}/{scene.total_frames}{state}"

    def tick(self) -> None:
        """Draw and show the current frame, pace to the scene fps, then advance.

        Advances one frame only when playing and the scene has not finished.
        """
        scene = self.scene
        scene.draw(self.renderer)
        if self.screen.get_size() == self.renderer.surface.get_size():
            self.screen.blit(self.renderer.surface, (0, 0))
        else:
            pygame.transform.smoothscale(
                self.renderer.surface, self.screen.get_size(), self.screen
            )
        if not self.paused and scene.frame < scene.total_frames:
            scene.step_frame()
        pygame.display.set_caption(self._title())
        pygame.display.flip()
        self.clock.tick(scene.config.fps)

    def run(self, max_frames: int | None = None) -> "Scene":
        """Loop until quit (or ``max_frames`` loop iterations); return the final scene."""
        iterations = 0
        while not self.is_quit() and (max_frames is None or iterations < max_frames):
            for event in pygame.event.get():
                self.handle_event(event)
            if not self.is_quit():
                self.tick()
                iterations += 1
        return self.scene


def run_preview(
    make_scene: "Callable[[], Scene]", scale: float = 0.45, max_frames: int | None = None
) -> "Scene":
    """Play scenes built by ``make_scene`` in a window until the user quits.

    ``max_frames`` stops after that many loop iterations (used for headless
    tests with ``SDL_VIDEODRIVER=dummy``). Returns the scene being shown at exit.
    """
    try:
        preview = Preview(make_scene, scale)
        return preview.run(max_frames)
    finally:
        pygame.quit()
