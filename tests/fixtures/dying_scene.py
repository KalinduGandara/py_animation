"""Fixture: like ``flaky_scene`` but some ``mode`` values kill the worker process.

``mode=die`` calls ``os._exit(3)`` while the script loads (after the Scene exists);
``mode=die_render`` kills the process after a few frames have gone to ffmpeg, leaving
a partial MP4. Only for batch tests with ``--jobs > 1``.
"""

import os

from bouncekit import Scene

scene = Scene(width=64, height=64, fps=30, duration=0.3, seed=7, max_speed=1000)
mode = scene.param("mode", "a")
if mode == "die":
    os._exit(3)
scene.add_circle(center=(32, 32), radius=28, segments=24, tags={"wall"})
scene.add_ball(pos=(32, 28), radius=4, velocity=(60.0, 0.0), color="#40ff80", tags={"ball"})

if mode == "die_render":
    _frames = scene.frames

    def _dying_frames():  # type: ignore[no-untyped-def]
        for i, frame in enumerate(_frames()):
            if i == 4:
                os._exit(4)
            yield frame

    scene.frames = _dying_frames  # type: ignore[method-assign]
