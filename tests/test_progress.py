"""Progress bar tests (FR-408, NFR-401)."""

import io
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import cli  # noqa: E402
from bouncekit.progress import Progress  # noqa: E402

TINY = Path(__file__).parent / "fixtures" / "tiny_scene.py"


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _bar(total: int = 10) -> tuple[Progress, io.StringIO, Clock]:
    out, clock = io.StringIO(), Clock()
    return (
        Progress(total, label="render", unit="frames", stream=out, enabled=True, clock=clock),
        out,
        clock,
    )


def test_update_format_and_eta() -> None:
    bar, out, clock = _bar()
    clock.t += 5
    bar.update(5)
    text = out.getvalue()
    assert text.startswith("\r")
    assert "50%" in text and "5/10 frames" in text and "ETA 0:05" in text
    assert "[##########----------]" in text


def test_throttle_and_completion_always_drawn() -> None:
    bar, out, clock = _bar()
    clock.t += 1
    bar.update(1)
    n = out.getvalue().count("\r")
    clock.t += 0.05
    bar.update(2)
    assert out.getvalue().count("\r") == n
    bar.update(10)
    assert out.getvalue().count("\r") == n + 1
    assert "100%" in out.getvalue()


def test_eta_unknown_at_zero() -> None:
    bar, out, clock = _bar()
    clock.t += 1
    bar.update(0)
    assert "ETA --:--" in out.getvalue()


def test_padding_over_longer_previous_line() -> None:
    bar, out, clock = _bar(1000)
    clock.t += 1
    bar.update(100)
    long = out.getvalue().rstrip().split("\r")[-1]
    out.truncate(0)
    out.seek(0)
    clock.t += 1
    bar.update(1000)
    short = out.getvalue()[1:]
    assert len(short) >= len(long)


def test_close_writes_one_newline() -> None:
    bar, out, clock = _bar()
    clock.t += 1
    bar.update(1)
    bar.close()
    assert out.getvalue().endswith("\n") and out.getvalue().count("\n") == 1


def test_close_without_draw_writes_nothing() -> None:
    bar, out, _ = _bar()
    bar.close()
    assert out.getvalue() == ""


def test_non_tty_writes_nothing() -> None:
    out = io.StringIO()
    bar = Progress(2, label="x", unit="jobs", stream=out)
    bar.update(1)
    bar.update(2)
    bar.write("hello", stream=out)
    bar.close()
    assert out.getvalue() == "hello\n"


def test_write_clears_then_redraws() -> None:
    bar, out, clock = _bar()
    clock.t += 1
    bar.update(3)
    out.truncate(0)
    out.seek(0)
    bar.write("line", stream=out)
    text = out.getvalue()
    assert text.startswith("\r ") and "\rline\n" in text
    assert text.rstrip().split("\r")[-1].startswith("render [")


def test_scene_render_progress_callback(tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []
    a = cli.load_scene(TINY)
    a.render(tmp_path / "a.mp4", progress=lambda d, t: calls.append((d, t)))
    total = a.total_frames
    assert calls == [(i, total) for i in range(1, total + 1)]
    b = cli.load_scene(TINY)
    b.render(tmp_path / "b.mp4")
    assert (tmp_path / "a.mp4").read_bytes() == (tmp_path / "b.mp4").read_bytes()


def test_cli_render_non_tty_has_no_cr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["render", str(TINY), "--out", str(tmp_path / "o.mp4")]) == 0
    assert "\r" not in capsys.readouterr().err


def test_cli_render_tty_shows_bar_and_quiet_hides(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setattr(type(sys.stderr), "isatty", lambda self: True, raising=False)
    assert cli.main(["render", str(TINY), "--out", str(tmp_path / "o.mp4")]) == 0
    err = capsys.readouterr().err
    assert "\r" in err and "frames" in err and "100%" in err
    assert cli.main(["render", str(TINY), "--quiet", "--out", str(tmp_path / "q.mp4")]) == 0
    assert "\r" not in capsys.readouterr().err


def test_cli_batch_bar_shows_jobs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setattr(type(sys.stderr), "isatty", lambda self: True, raising=False)
    code = cli.main(["batch", str(TINY), "--seeds", "1-2", "--out-dir", str(tmp_path)])
    assert code == 0
    err = capsys.readouterr().err
    assert "jobs" in err and "2/2" in err
