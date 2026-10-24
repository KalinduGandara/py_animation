"""Scene params and CLI overrides (FR-401, FR-402, NFR-401 params part)."""

import hashlib
import os
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene, cli  # noqa: E402
from bouncekit import scene as scene_module  # noqa: E402
from bouncekit.errors import ConfigError  # noqa: E402
from bouncekit.params import check_name, parse_value, suffix  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PARAM = FIXTURES / "param_scene.py"
TINY = FIXTURES / "tiny_scene.py"


def _scene() -> Scene:
    return Scene(width=64, height=48, fps=30, duration=0.2)


# --- params.parse_value / check_name / suffix -------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("true", True), ("TRUE", True), ("1", True), ("yes", True), ("On", True),
        ("false", False), ("0", False), ("No", False), ("off", False),
    ],
)  # fmt: skip
def test_parse_bool_words(text: str, expected: bool) -> None:
    assert parse_value("flag", False, text) is expected


@pytest.mark.parametrize("text", ["", "maybe", "2", "tru"])
def test_parse_bool_rejects(text: str) -> None:
    with pytest.raises(ConfigError, match="flag"):
        parse_value("flag", True, text)


def test_parse_int() -> None:
    assert parse_value("n", 3, "40") == 40
    assert parse_value("n", 3, " -7 ") == -7
    with pytest.raises(ConfigError, match=r"n.*int.*40\.5"):
        parse_value("n", 3, "40.5")


def test_parse_float() -> None:
    value = parse_value("g", 1.5, "40")
    assert value == 40.0 and isinstance(value, float)
    assert parse_value("g", 1.5, "1e3") == 1000.0
    for bad in ["nan", "inf", "-inf", "abc", ""]:
        with pytest.raises(ConfigError, match=r"g.*float"):
            parse_value("g", 1.5, bad)


def test_parse_str_is_verbatim() -> None:
    assert parse_value("theme", "neon", "  a b=,c ") == "  a b=,c "
    assert parse_value("theme", "neon", "") == ""


@pytest.mark.parametrize("name", ["", "1x", "a-b", "a b", 3, None])
def test_check_name_rejects(name: object) -> None:
    with pytest.raises(ConfigError, match="name"):
        check_name(name)


def test_check_name_accepts() -> None:
    assert check_name("_gap2") == "_gap2"


def test_suffix() -> None:
    assert suffix([]) == ""
    assert suffix([("gap", "60"), ("theme", "neon")]) == "_gap-60_theme-neon"
    assert suffix([("t", "a b/c"), ("e", ""), ("x", "-1.5e+3")]) == "_t-a_b_c_e-__x--1.5e+3"


# --- Scene.param / Scene.params ----------------------------------------------------


def test_param_returns_default_without_override() -> None:
    s = _scene()
    assert s.param("gap", 40.0) == 40.0
    assert s.param("on", True) is True
    assert s.param("theme", "neon") == "neon"
    assert s.params == {"gap": 40.0, "on": True, "theme": "neon"}


def test_params_keep_declaration_order_and_are_a_copy() -> None:
    s = _scene()
    for name, default in [("z", 1), ("a", 2.0), ("m", "x")]:
        s.param(name, default)
    s.param("z", 1)  # re-declaration does not move it
    params = s.params
    assert list(params) == ["z", "a", "m"]
    params["z"] = 99
    assert s.params["z"] == 1


@pytest.mark.parametrize("name", ["", "1x", "a-b", 5])
def test_param_bad_name(name: object) -> None:
    with pytest.raises(ConfigError, match="name"):
        _scene().param(name, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("default", [None, [1], (1,), float("nan"), float("inf"), b"x"])
def test_param_bad_default(default: object) -> None:
    with pytest.raises(ConfigError, match="speed"):
        _scene().param("speed", default)  # type: ignore[arg-type]


def test_param_redeclaration() -> None:
    s = _scene()
    assert s.param("n", 3) == 3
    assert s.param("n", 3) == 3
    with pytest.raises(ConfigError, match="n"):
        s.param("n", 4)
    with pytest.raises(ConfigError, match="n"):
        s.param("n", 3.0)  # same value, different type
    s.param("b", 1)
    with pytest.raises(ConfigError, match="b"):
        s.param("b", True)  # bool is not int here


def test_param_leaves_rng_state_untouched() -> None:
    s = _scene()
    rng, fx = s.rng.getstate(), s.fx_rng.getstate()
    s.param("a", 1.0)
    s.param("b", "x")
    assert s.rng.getstate() == rng and s.fx_rng.getstate() == fx


def test_param_reads_active_override() -> None:
    scene_module._param_overrides.update({"n": "12", "flag": "off"})
    try:
        s = _scene()
    finally:
        scene_module._param_overrides.clear()
    assert s.param("n", 3) == 12
    assert s.param("flag", True) is False
    assert s.param("other", 1.5) == 1.5
    assert s.params == {"n": 12, "flag": False, "other": 1.5}


# --- load_scene(params=) -----------------------------------------------------------


def _run(scene: Scene) -> tuple[list[str], list[tuple[object, ...]], object, int]:
    hashes = [hashlib.sha256(f).hexdigest() for f in scene.frames()]
    index = scene._indices
    keys = [
        (e.kind, e.step, tuple(index[o] for o in e.objects), e.speed, e.position)
        for e in scene.events
    ]
    return hashes, keys, scene.rng.getstate(), len(scene.triggers)


def test_load_scene_with_override_equals_hard_coded(tmp_path: Path) -> None:
    hard = tmp_path / "hard.py"
    text = PARAM.read_text()
    assert 'scene.param("vx", 100.0)' in text
    hard.write_text(text.replace('scene.param("vx", 100.0)', "250.0"))
    loaded = cli.load_scene(PARAM, params={"vx": "250"})
    assert loaded.params == {"vx": 250.0}
    a, b = _run(loaded), _run(cli.load_scene(hard))
    assert a == b
    assert a[1], "fixture should produce events"
    assert a != _run(cli.load_scene(PARAM))


def test_load_scene_without_params_uses_default() -> None:
    assert cli.load_scene(PARAM).params == {"vx": 100.0}


def test_load_scene_bad_override_text() -> None:
    with pytest.raises(ConfigError, match=r"vx.*float.*fast"):
        cli.load_scene(PARAM, params={"vx": "fast"})


def test_unknown_override_lists_declared_names() -> None:
    with pytest.raises(ConfigError, match=r"unknown param.*'vy'.*declares: vx"):
        cli.load_scene(PARAM, params={"vx": "1", "vy": "2"})


def test_unknown_override_with_no_declarations() -> None:
    with pytest.raises(ConfigError, match="declares no params"):
        cli.load_scene(TINY, params={"vx": "1"})


def test_param_overrides_cleared_after_load() -> None:
    cli.load_scene(PARAM, params={"vx": "3"})
    assert scene_module._param_overrides == {}
    with pytest.raises(ConfigError):
        cli.load_scene(PARAM, params={"nope": "3"})
    assert scene_module._param_overrides == {}
    assert _scene().param("vx", 1.0) == 1.0


# --- CLI --set -----------------------------------------------------------------------


def test_render_set_default_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = cli.main(["render", str(PARAM), "--set", "vx=250", "--duration", "0.2", "--seed", "3"])
    assert code == 0, capsys.readouterr().err
    assert (tmp_path / "out" / "param_scene_seed3_vx-250.mp4").is_file()
    assert (tmp_path / "out" / "param_scene_seed3_vx-250.json").is_file()
    assert "wrote" in capsys.readouterr().out


def test_render_without_set_keeps_m0_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["render", str(TINY), "--seed", "9", "--duration", "0.1"]) == 0
    assert (tmp_path / "out" / "tiny_scene_seed9.mp4").is_file()
    assert (tmp_path / "out" / "tiny_scene_seed9.json").is_file()


@pytest.mark.parametrize(
    "sets",
    [["vx"], ["=3"], ["1x=3"], ["vx=1", "vx=2"], ["a b=1"]],
)
@pytest.mark.parametrize("command", ["render", "preview"])
def test_malformed_or_repeated_set_exits_2(
    command: str,
    sets: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    called: list[bool] = []
    monkeypatch.setattr(cli, "run_preview", lambda *_a, **_kw: called.append(True))
    monkeypatch.setattr(cli, "load_scene", lambda *_a, **_kw: called.append(True))
    argv = [command, str(PARAM)]
    for item in sets:
        argv += ["--set", item]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "--set" in err
    assert called == []
    assert not (tmp_path / "out").exists()


def test_render_unknown_param_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["render", str(PARAM), "--set", "vy=1", "--duration", "0.1"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "vy" in err and "vx" in err
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_preview_unknown_param_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    called: list[bool] = []
    monkeypatch.setattr(cli, "run_preview", lambda *_a, **_kw: called.append(True))
    assert cli.main(["preview", str(PARAM), "--set", "vy=1"]) == 2
    assert called == [] and "vy" in capsys.readouterr().err


def test_preview_reload_receives_same_params(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Callable[[], Scene], Callable[[], Scene] | None]] = []

    def fake(make: Callable[[], Scene], _scale: float, **kw: object) -> None:
        seen.append((make, kw.get("reload")))  # type: ignore[arg-type]

    monkeypatch.setattr(cli, "run_preview", fake)
    assert cli.main(["preview", str(PARAM), "--set", "vx=42"]) == 0
    make, reload = seen[0]
    assert reload is not None
    assert make().params == {"vx": 42.0}
    assert reload().params == {"vx": 42.0}
    assert reload().params == {"vx": 42.0}
