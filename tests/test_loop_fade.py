"""Loop-friendly ending: video cross-fade into frame 0 and audio fade (T-605: FR-607, FR-608)."""

import math
import os

import numpy as np
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import sound as S  # noqa: E402
from bouncekit.audio.mixer import num_samples  # noqa: E402
from bouncekit.errors import ConfigError  # noqa: E402
from bouncekit.export.audio import fade_out  # noqa: E402

FPS = 30


def _scene(loop_fade: float = 0.0, *, duration: float = 1.0, end: float | None = None) -> Scene:
    scene = Scene(width=64, height=64, fps=FPS, duration=duration, seed=1, gravity=(0.0, 400.0),
                  max_speed=1000, loop_fade=loop_fade)  # fmt: skip
    scene.add_circle(center=(32, 32), radius=28, segments=32, color="#80ff80", tags={"wall"})
    scene.add_ball(pos=(32, 20), radius=5, velocity=(170, 0), color="#ff4060", tags={"ball"})
    scene.on_collision("ball", "wall", [A.play(S.scale("C4"))])
    if end is not None:
        scene.at(end, [A.end_after(0)])
    return scene


def _frames(scene: Scene) -> list[np.ndarray]:
    return [np.frombuffer(f, np.uint8).astype(np.float64) for f in scene.frames()]


@pytest.mark.parametrize("bad", [-0.1, math.nan, math.inf, "1"])
def test_loop_fade_validation(bad: object) -> None:
    with pytest.raises(ConfigError, match="loop_fade"):
        Scene(loop_fade=bad)  # type: ignore[arg-type]


def _check_window(plain: list[np.ndarray], faded: list[np.ndarray], n: int) -> None:
    assert len(faded) == len(plain)
    start = len(plain) - n
    for k in range(start):
        assert np.array_equal(faded[k], plain[k])
    for i in range(1, n + 1):
        t = i / (n + 1)
        expected = plain[start + i - 1] * (1 - t) + plain[0] * t
        assert np.abs(faded[start + i - 1] - expected).max() <= 1.0


def test_last_frames_cross_fade_into_frame_0() -> None:
    _check_window(_frames(_scene()), _frames(_scene(0.2)), n=6)


def test_window_follows_an_early_end() -> None:
    plain = _frames(_scene(end=0.5))
    assert len(plain) == 15
    _check_window(plain, _frames(_scene(0.2, end=0.5)), n=6)


def test_window_capped_at_frames_minus_one() -> None:
    plain = _frames(_scene(duration=0.1))
    _check_window(plain, _frames(_scene(1.0, duration=0.1)), n=len(plain) - 1)


def test_delay_line_holds_at_most_n_plus_one_frames() -> None:
    scene = _scene(0.2)
    for yielded, _ in enumerate(scene.frames(), 1):
        assert scene.frame - yielded <= 6 + 1


def test_audio_fades_to_zero_over_the_window() -> None:
    plain, faded = _scene(), _scene(0.2)
    for _ in plain.frames():
        pass
    for _ in faded.frames():
        pass
    a, b = plain.audio_buffer(), faded.audio_buffer()
    start = num_samples(30 - 6, FPS)
    assert np.array_equal(a[:start], b[:start])
    assert np.allclose(b[start:], a[start:] * np.linspace(1, 0, len(a) - start)[:, None], atol=1e-6)
    assert np.abs(a[start:]).max() > 0  # the test means something: there is sound to fade


def test_zero_fade_keeps_frames_and_audio() -> None:
    a, b = _scene(), _scene(0.0)
    assert [bytes(x) for x in a.frames()] == [bytes(x) for x in b.frames()]
    assert np.array_equal(a.audio_buffer(), b.audio_buffer())


def test_fade_out_helper() -> None:
    buf = np.ones((10, 2), np.float32)
    out = fade_out(buf, 6)
    assert np.array_equal(out[:6], buf[:6])
    assert np.allclose(out[6:, 0], [1, 2 / 3, 1 / 3, 0])
    assert np.array_equal(buf, np.ones((10, 2), np.float32))  # input untouched
