"""Bundled emoji font and emoji fallback in Renderer.text (T-603: FR-606, NFR-601, NFR-602)."""

import hashlib
import os

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit.render.pygame_renderer import EMOJI_FONT, PygameRenderer  # noqa: E402

# Recorded with the pre-M6 renderer (commit 9bd4fa9): default-font text must not change.
GOLDEN_ASCII = "7e74682a5e8aa52587679f651e606d4d45607b8a43a1667b5cd6952915320bbf"
GOLDEN_UNKNOWN = "b2f816ca9562d06585bac370884b73d4c48fbcd89babeb8a7f25079b88e3a0ec"


def _draw(text: str, w: int = 200, h: int = 100, size: float = 30) -> PygameRenderer:
    r = PygameRenderer(w, h)
    r.clear((0, 0, 0))
    r.text(text, (w / 2, h / 2), size, (255, 255, 255))
    return r


def _pixels(r: PygameRenderer) -> np.ndarray:
    return np.frombuffer(r.to_rgb_bytes(), np.uint8).reshape(r.height, r.width, 3)


def test_font_and_licence_ship_in_the_package() -> None:
    assert EMOJI_FONT.name == "NotoEmoji.ttf" and EMOJI_FONT.is_file()
    licence = EMOJI_FONT.with_name("OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE VERSION 1.1" in licence.upper()


def test_default_font_text_keeps_pre_m6_bytes() -> None:
    r = PygameRenderer(240, 120)
    r.clear((10, 20, 30))
    r.text("Hi there, Für Elise 30%", (120, 40), 22, (255, 200, 0))
    r.text("ÄBC xyz", (100, 90), 40, (255, 255, 255))
    assert hashlib.sha256(r.to_rgb_bytes()).hexdigest() == GOLDEN_ASCII
    assert hashlib.sha256(_draw("A★B").to_rgb_bytes()).hexdigest() == GOLDEN_UNKNOWN


def test_emoji_draws_a_glyph_not_a_box() -> None:
    import pygame.freetype

    pygame.freetype.init()
    tofu = PygameRenderer(200, 100)
    tofu.clear((0, 0, 0))
    font = pygame.freetype.Font(None, 30)
    font.origin = True
    font.render_to(tofu.surface, (85, 60), "\U0001f447", (255, 255, 255), size=30)
    emoji = _pixels(_draw("\U0001f447"))
    assert emoji.any()
    assert not np.array_equal(emoji, _pixels(tofu))


def test_mixed_line_is_centred_on_its_total_advance() -> None:
    ink = _pixels(_draw("A\U0001f525A", w=300)).any(axis=(0, 2)).nonzero()[0]
    left, right = ink[0], 300 - 1 - ink[-1]
    assert abs(left - right) <= 4
    assert ink[-1] - ink[0] > 50  # three glyphs side by side, not drawn on top of each other


def test_variation_selector_is_dropped_and_output_is_deterministic() -> None:
    a = _draw("❤️ go").to_rgb_bytes()
    assert a == _draw("❤ go").to_rgb_bytes() == _draw("❤️ go").to_rgb_bytes()
    assert a != _draw("  go").to_rgb_bytes()
