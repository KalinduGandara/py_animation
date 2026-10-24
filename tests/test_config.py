"""Tests for SceneConfig, colour parsing and errors (FR-001, FR-002)."""

import dataclasses

import pytest

from bouncekit.colors import parse_color
from bouncekit.config import SceneConfig
from bouncekit.errors import BouncekitError, ConfigError, FfmpegError


def test_defaults() -> None:
    c = SceneConfig()
    assert (c.width, c.height, c.fps, c.substeps) == (1080, 1920, 60, 8)
    assert c.duration == 60.0
    assert c.seed == 0
    assert c.background == (0, 0, 0)
    assert c.gravity == (0.0, 900.0)
    assert c.max_speed == 4000.0


def test_gravity_positive_y_is_down() -> None:
    assert SceneConfig().gravity[1] > 0


def test_custom_values_stored() -> None:
    c = SceneConfig(width=100, height=200, fps=30, duration=2.5, seed=7,
                    background="#fff", gravity=(1, 2), substeps=4, max_speed=10)
    assert (c.width, c.height, c.fps, c.duration, c.seed) == (100, 200, 30, 2.5, 7)
    assert c.background == (255, 255, 255)
    assert c.gravity == (1.0, 2.0)
    assert c.substeps == 4
    assert c.max_speed == 10.0


def test_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        SceneConfig().width = 10  # type: ignore[misc]


def test_error_hierarchy() -> None:
    assert issubclass(ConfigError, BouncekitError)
    assert issubclass(FfmpegError, BouncekitError)


@pytest.mark.parametrize("field", ["width", "height"])
@pytest.mark.parametrize("bad", [0, -2, 101, 100.0, True, "100"])
def test_bad_size(field: str, bad: object) -> None:
    with pytest.raises(ConfigError) as e:
        SceneConfig(**{field: bad})  # type: ignore[arg-type]
    assert field in str(e.value)
    assert repr(bad) in str(e.value) or str(bad) in str(e.value)


@pytest.mark.parametrize("field", ["fps", "duration", "substeps", "max_speed"])
@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_bad_positive(field: str, bad: float) -> None:
    with pytest.raises(ConfigError) as e:
        SceneConfig(**{field: bad})  # type: ignore[arg-type]
    assert field in str(e.value)


def test_fps_substeps_must_be_int() -> None:
    with pytest.raises(ConfigError):
        SceneConfig(fps=29.5)  # type: ignore[arg-type]
    with pytest.raises(ConfigError):
        SceneConfig(substeps=2.5)  # type: ignore[arg-type]


def test_bad_seed_and_gravity() -> None:
    with pytest.raises(ConfigError, match="seed"):
        SceneConfig(seed=1.5)  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="gravity"):
        SceneConfig(gravity=(1, 2, 3))  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="gravity"):
        SceneConfig(gravity=(float("nan"), 0))


@pytest.mark.parametrize("bad", ["red", "#12", "#12345", "#gggggg", "ffffff", "", "#1234567"])
def test_bad_colour_strings(bad: str) -> None:
    with pytest.raises(ConfigError) as e:
        parse_color(bad)
    assert repr(bad) in str(e.value)


@pytest.mark.parametrize("bad", [(1, 2), (1, 2, 3, 4), (256, 0, 0), (-1, 0, 0), (1.5, 0, 0),
                                 (True, 0, 0), 5, None])
def test_bad_colour_tuples(bad: object) -> None:
    with pytest.raises(ConfigError):
        parse_color(bad)  # type: ignore[arg-type]


def test_good_colours() -> None:
    assert parse_color("#fff") == (255, 255, 255)
    assert parse_color("#1a2B3c") == (0x1A, 0x2B, 0x3C)
    assert parse_color("#abc") == (0xAA, 0xBB, 0xCC)
    assert parse_color((1, 2, 3)) == (1, 2, 3)
    assert parse_color([4, 5, 6]) == (4, 5, 6)  # type: ignore[arg-type]


def test_bad_background_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        SceneConfig(background="nope")


# --- Scene / add_* validation (FR-001, FR-003, FR-004) -----------------------


def test_scene_validates_config() -> None:
    from bouncekit import Scene

    with pytest.raises(ConfigError, match="width"):
        Scene(width=101)
    with pytest.raises(ConfigError, match="fps"):
        Scene(fps=0)


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"radius": 0}, "radius"),
        ({"radius": -5}, "radius"),
        ({"radius": float("nan")}, "radius"),
        ({"thickness": 0}, "thickness"),
        ({"thickness": -1}, "thickness"),
        ({"segments": 7}, "segments"),
        ({"segments": 8.0}, "segments"),
        ({"gap_degrees": -1}, "gap_degrees"),
        ({"gap_degrees": 360}, "gap_degrees"),
        ({"angular_velocity": float("inf")}, "angular_velocity"),
        ({"elasticity": -0.1}, "elasticity"),
        ({"color": "nope"}, "nope"),
        ({"center": (1, 2, 3)}, "center"),
        ({"tags": [1]}, "tags"),
    ],
)
def test_add_circle_validation(kwargs: dict[str, object], field: str) -> None:
    from bouncekit import Scene

    opts: dict[str, object] = {"center": (0, 0), "radius": 10}
    opts.update(kwargs)
    with pytest.raises(ConfigError, match=field):
        Scene().add_circle(**opts)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"radius": 0}, "radius"),
        ({"radius": -1}, "radius"),
        ({"radius": float("inf")}, "radius"),
        ({"pos": (1,)}, "pos"),
        ({"pos": (float("nan"), 0)}, "pos"),
        ({"velocity": "fast"}, "velocity"),
        ({"elasticity": float("nan")}, "elasticity"),
        ({"color": (300, 0, 0)}, "300"),
        ({"tags": "ab"}, "tags"),
    ],
)
def test_add_ball_validation(kwargs: dict[str, object], field: str) -> None:
    from bouncekit import Scene

    opts: dict[str, object] = {"pos": (0, 0), "radius": 5}
    opts.update(kwargs)
    with pytest.raises(ConfigError, match=field):
        Scene().add_ball(**opts)  # type: ignore[arg-type]


def test_add_circle_accepts_edge_values() -> None:
    from bouncekit import Scene

    r = Scene().add_circle(center=(0, 0), radius=10, segments=8, gap_degrees=359.9)
    assert r.gap_degrees == pytest.approx(359.9)


def test_duration_shorter_than_one_frame_rejected() -> None:
    with pytest.raises(ConfigError, match="duration"):
        SceneConfig(fps=60, duration=0.001)
