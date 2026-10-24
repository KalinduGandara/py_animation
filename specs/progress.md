# Progress — bouncekit

## Log

- 2026-10-24: Phase 1–2 done; defaults accepted (see clarifications.md). uv installed, git initialised, uv project created with pymunk 7.3.1, pygame-ce 2.5.8, numpy; dev: pytest, ruff, mypy.
- 2026-10-24: requirements.md, design.md, tasks.md written for M0.
- 2026-10-24: T-001 done: pyproject tool config + entry point, package skeleton (world/render/export, cli stub), smoke tests; pytest/ruff/mypy pass.
- 2026-10-24: T-002 done: errors, colour parsing, frozen validated SceneConfig; tests/test_config.py; gate passes.
- 2026-10-24: T-003 done: Scene core (config, rng, `_overrides`, registry, fixed-step loop), Ball (speed clamp in velocity_func), CircleBoundary (segments, gap, rotation, set_neighbors); shared validators in config.py; tests/test_world.py + add_* validation; gate passes. Note: Chipmunk adds ~0.2% speed on head-on vertex hits (bounded by the clamp); neighbour-joined seams cut wall hops from ~10 px to ~2 px.
- 2026-10-24: T-004 done: Renderer protocol (runtime_checkable), PygameRenderer (off-screen Surface; thick_line = filled quad + AA edges + round caps), Ball/CircleBoundary.draw, Scene.draw/frames (yield current frame then step); tests/test_render.py + tests/test_determinism.py; gate passes.
- 2026-10-24: T-005 done: export/ffmpeg.py (`require_ffmpeg`, `FfmpegWriter` with frame-length and stderr-tail errors), `Scene.render` (checks ffmpeg before simulating, creates parent dirs); tests/test_export.py incl. real ffprobe check; gate passes.
- 2026-10-24: T-006 done: cli.py (`load_scene` via runpy with `_overrides`, `render`/`preview` subcommands, `default_scene` for `Scene.run`, errors -> `error: ...` exit 2), `SceneLoadError`, `Scene.run`, `run_preview` placeholder; tests/test_cli.py + tests/fixtures; gate passes.
- 2026-10-24: T-007 done: render/preview.py (`Preview` class with handle_event/tick/run, `run_preview(make_scene, scale, max_frames)` returns final scene), `Scene.preview` (restart reloads `sys.argv[0]` with same seed/duration); tests/test_preview.py headless; gate passes.
- 2026-10-24: T-008 done: examples/single_ball.py, README (quickstart + API), tests/test_example.py incl. ffprobe 1080x1920/60fps/h264/yuv420p; full suite ~6 s; gate passes.

- 2026-10-24: Phase 7 review (fresh-eyes Opus agent) found 2 medium + 3 low issues; all fixed with regression tests first:
  1. Speed exceeded `max_speed` (~4100 px/s) vs a spinning ring: clamp moved from `velocity_func` to after each `space.step` (`Ball.clamp_speed`).
  2. Balls with `radius + thickness/2 <= max_speed·dt` tunnelled: new `TunnellingWarning` on add_ball/add_circle (NFR-003 condition made explicit). A hard error was tried first and rejected: it broke 34 valid low-speed test scenes.
  3. Duration shorter than one frame wrote an empty MP4: now `ConfigError`.
  4. pygame banner on stdout: `PYGAME_HIDE_SUPPORT_PROMPT` set on import.
  5. Example test now asserts ring centre/radius and gravity.
- 2026-10-24: Verified: 184 tests pass (~6 s), ruff + mypy strict clean; `bouncekit render examples/single_ball.py` -> 1080x1920 h264 yuv420p 60/1, 600 frames; two separate-process renders produce byte-identical MP4s; seed 7 differs.

## Traceability (requirement -> tests)

| Req | Tests |
|---|---|
| FR-001 | test_config.py: test_defaults, test_custom_values_stored, test_bad_size, test_bad_positive, test_fps_substeps_must_be_int, test_bad_seed_and_gravity, colour tests, test_duration_shorter_than_one_frame_rejected; test_world.py: test_scene_defaults_and_config, test_scene_custom_config |
| FR-002 | test_config.py::test_gravity_positive_y_is_down; test_world.py::test_gravity_pulls_down_screen |
| FR-003 | test_world.py: test_ring_properties_and_segments, test_gap_removes_segments_around_zero_degrees, test_ball_escapes_through_gap, test_static_ring_with_gap_right_holds_falling_ball, test_rotation_angle_after_n_frames, test_rotating_gap_collisions_follow_rotation, test_seams_are_smooth; test_config.py::test_add_circle_validation; test_render.py: test_scene_draw_shows_gap, test_scene_draw_follows_rotation |
| FR-004 | test_world.py: test_ball_properties, test_closed_ring_contains_ball; test_config.py::test_add_ball_validation |
| FR-005 | test_world.py: test_one_frame_is_substeps_fixed_steps, test_step_and_frame_counting, test_speed_clamp_keeps_direction, test_speed_clamp_under_gravity_uses_config, test_speed_clamped_after_collisions_with_spinning_ring; test_render.py: test_frames_first_frame_is_initial_state_then_steps, test_frames_yields_total_frames_of_right_size. "No wall-clock" verified by code review only. |
| FR-006 | test_world.py: test_rng_seeded_from_seed, test_overrides_applied_before_rng |
| FR-007 | test_export.py: test_writer_real_encode, test_scene_render, test_require_ffmpeg_missing, test_writer_missing_ffmpeg, test_scene_render_fails_before_simulating, test_writer_ffmpeg_failure_includes_stderr, test_writer_bad_frame_length; test_cli.py: test_render_default_out_path, test_render_default_out_uses_script_seed, test_missing_ffmpeg_exit_code. **Untested:** CRF 18 / +faststart flags (moov-before-mdat checked manually) |
| FR-008 | test_render.py: test_renderer_satisfies_protocol, test_clear_fills_frame_and_size, test_circle_fills_inside_only, test_thick_line_has_width_and_round_caps, test_scene_draw_background_ball_and_ring, test_draw_order_is_insertion_order. Anti-aliasing checked visually only. |
| FR-009 | test_preview.py: key tests, test_holds_last_frame_when_finished, test_step_does_not_pass_the_end, test_preview_frames_match_offline_render, test_window_size_and_title; test_cli.py: preview dispatch tests. **Untested:** real-time pacing / slow-down-not-skip (manual) |
| FR-010 | test_cli.py: load single/zero/many, test_load_skips_main_block, override tests, test_scene_run_dispatches_to_cli, test_script_run_as_main_renders, missing-file tests, test_render_end_to_end |
| FR-011 | test_example.py: test_example_layout, test_example_initial_velocity_follows_seed, test_ball_stays_inside_ring |
| NFR-001 | test_determinism.py: same-seed identical hashes, different-seed differs; manual two-process byte-identical MP4 |
| NFR-002 | test_example.py::test_example_renders_expected_format |
| NFR-003 | test_world.py: test_no_tunnelling_at_max_speed, test_ball_too_thin_for_ring_at_max_speed_warns, test_thin_ball_ok_with_more_substeps |
| NFR-004 | test_render.py: test_rendering_does_not_mutate_physics, test_draw_alone_leaves_state_unchanged |
| NFR-005 | test_smoke.py; ruff + mypy gate |
| NFR-006 | test_example.py::test_readme_has_quickstart_and_api (docstrings by review) |
| NFR-007 | full suite ~6 s (no automated check) |

## Status

M0 complete and reviewed. Waiting for user review. Next: M1 (audio) planning — not started.
