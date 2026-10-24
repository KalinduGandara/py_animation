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

- 2026-10-24: User review of M0: (a) tunnelling -> `ConfigError` (test scenes given honest `max_speed` values for their slow balls); (b) jagged ring fixed: new `Renderer.arc`, SDF anti-aliasing for circle/thick_line/arc, tests compare every pixel to analytic coverage; (c) added tests for CRF 18/+faststart flags + moov-before-mdat, and preview pacing (ticks at fps, one step per displayed frame even when lagging). ruff/mypy kept.

- 2026-10-24: M1 planned: requirements FR-101..FR-110 / NFR-101..NFR-105, design §M1, tasks T-101..T-104, assumptions B1..B15. Probe: pymunk 7.3.1 `begin` sees pre-impulse velocities; a seam hit fires two `begin`s in one substep (merged per object pair).
- 2026-10-24: T-101 done: events.py (`EventRecorder` wildcard begin/separate, per-pair contact count + per-step merge), sound.py (`pitch_to_hz`, `note`), actions.py (`play`), audio/voices.py (`ADSR`, `Sine`), audio/mixer.py (`sample_offset`, `num_samples`, `mix`: tanh + normalise + 5 ms fade), export/audio.py (`write_wav`), ffmpeg `mux`, `AudioConfig`, `Scene.on_collision/events/triggers/has_sound/audio_buffer`, render muxes AAC when sound rules exist; `soundfile` added (mypy override: no stubs). Probe: seam landing = 2 begins -> 1 event; rolling 3 s = 85 begins -> 1 event. Tests: test_events/test_sound/test_mixer/test_audio_export; gate passes (~8 s).
- 2026-10-24: T-102 done: audio/voices.py `Triangle` (exact triangle x ADSR), `Pluck` (Karplus-Strong, vectorised per period, noise from `default_rng([seed, hz, damping])`, delay `round(48000/hz - 0.5)` to cancel the averaging filter's half-sample lag), `Marimba` (partials 1/3.93/9.3, >20 kHz dropped); `Voice` union, `VOICES` has 4 names, `resolve_voice` accepts all types; sound.py re-exports them; mixer's `(voice, hz, seed)` cache verified (one render per key). tests/test_voices.py (pitch by autocorrelation within 2% at 220/440/880 Hz); gate passes.
- 2026-10-24: T-103 done: sound.py `Scale`/`scale` (5 modes, octaves 1..8, top root, identity-hashed; top note > 20 kHz is a ConfigError), `Play` accepts `Scale`; `AudioConfig` validates every field; `Scene._dispatch` applies min impact speed, retrigger interval per (play, object a) on exact step gaps, per-frame cap, gain curve, per-scene scale cursor advanced only by played notes; mixer steals the oldest note with a linear 5 ms fade when `max_polyphony` notes sound (triggers mixed in offset order). Tests: test_scale.py, test_policy.py (incl. AudioConfig cases); test_events gain assertion updated to the FR-106 curve (was the documented T-101 staging value). Gate passes.

## Traceability (requirement -> tests)

| Req | Tests |
|---|---|
| FR-001 | test_config.py: test_defaults, test_custom_values_stored, test_bad_size, test_bad_positive, test_fps_substeps_must_be_int, test_bad_seed_and_gravity, colour tests, test_duration_shorter_than_one_frame_rejected; test_world.py: test_scene_defaults_and_config, test_scene_custom_config |
| FR-002 | test_config.py::test_gravity_positive_y_is_down; test_world.py::test_gravity_pulls_down_screen |
| FR-003 | test_world.py: test_ring_properties_and_segments, test_gap_removes_segments_around_zero_degrees, test_ball_escapes_through_gap, test_static_ring_with_gap_right_holds_falling_ball, test_rotation_angle_after_n_frames, test_rotating_gap_collisions_follow_rotation, test_seams_are_smooth; test_config.py::test_add_circle_validation; test_render.py: test_scene_draw_shows_gap, test_scene_draw_follows_rotation |
| FR-004 | test_world.py: test_ball_properties, test_closed_ring_contains_ball; test_config.py::test_add_ball_validation |
| FR-005 | test_world.py: test_one_frame_is_substeps_fixed_steps, test_step_and_frame_counting, test_speed_clamp_keeps_direction, test_speed_clamp_under_gravity_uses_config, test_speed_clamped_after_collisions_with_spinning_ring; test_render.py: test_frames_first_frame_is_initial_state_then_steps, test_frames_yields_total_frames_of_right_size. "No wall-clock" verified by code review only. |
| FR-006 | test_world.py: test_rng_seeded_from_seed, test_overrides_applied_before_rng |
| FR-007 | test_export.py: test_writer_real_encode, test_scene_render, test_require_ffmpeg_missing, test_writer_missing_ffmpeg, test_scene_render_fails_before_simulating, test_writer_ffmpeg_failure_includes_stderr, test_writer_bad_frame_length; test_cli.py: test_render_default_out_path, test_render_default_out_uses_script_seed, test_missing_ffmpeg_exit_code. test_command_uses_crf18_faststart_h264, test_real_encode_is_faststart |
| FR-008 | test_render.py: test_full_ring_matches_analytic_coverage, test_circle_edge_matches_analytic_coverage, test_gap_arc_ends_at_physics_segment_ends, test_renderer_satisfies_protocol, test_clear_fills_frame_and_size, test_circle_fills_inside_only, test_thick_line_has_width_and_round_caps, test_scene_draw_background_ball_and_ring, test_draw_order_is_insertion_order. |
| FR-009 | test_preview.py: key tests, test_holds_last_frame_when_finished, test_step_does_not_pass_the_end, test_preview_frames_match_offline_render, test_window_size_and_title; test_cli.py: preview dispatch tests. test_paced_at_scene_fps_and_never_skips_steps |
| FR-010 | test_cli.py: load single/zero/many, test_load_skips_main_block, override tests, test_scene_run_dispatches_to_cli, test_script_run_as_main_renders, missing-file tests, test_render_end_to_end |
| FR-011 | test_example.py: test_example_layout, test_example_initial_velocity_follows_seed, test_ball_stays_inside_ring |
| NFR-001 | test_determinism.py: same-seed identical hashes, different-seed differs; manual two-process byte-identical MP4 |
| NFR-002 | test_example.py::test_example_renders_expected_format |
| NFR-003 | test_world.py: test_no_tunnelling_at_max_speed, test_ball_too_thin_for_ring_at_max_speed_is_rejected, test_thin_ball_allowed_with_more_substeps |
| NFR-004 | test_render.py: test_rendering_does_not_mutate_physics, test_draw_alone_leaves_state_unchanged |
| NFR-005 | test_smoke.py; ruff + mypy gate |
| NFR-006 | test_example.py::test_readme_has_quickstart_and_api (docstrings by review) |
| NFR-007 | full suite ~6 s (no automated check) |
| FR-101 | test_events.py: test_drop_event_step_time_and_speed_are_analytic, test_one_event_per_seam_hit, test_no_events_while_resting_after_settling, test_no_events_while_rolling_across_seams, test_handler_never_mutates_the_space |
| FR-102 | test_voices.py::test_voice_name_lookup; test_sound.py: test_pitch_to_hz, test_octave_range_bounds, test_bad_pitch_raises, test_note_source, test_note_rejects_bad_voice |
| FR-104 | test_events.py: test_rule_produces_trigger_per_matching_event, test_rules_fire_in_registration_order, test_scene_without_rules_has_no_sound, test_on_collision_rejects_bad_input; test_sound.py::test_play_action |
| FR-105 | test_sound.py: test_sine_voice_render, test_sine_validation, test_adsr_validation; test_voices.py: test_render_shape_start_peak_finite, test_dominant_frequency_within_two_percent, test_triangle_is_a_triangle_wave, test_pluck_same_seed_and_pitch_identical_different_seed_differs, test_pluck_decays, test_marimba_drops_partials_above_20khz, test_parameter_validation_names_field, test_render_cache_one_render_per_key |
| FR-107 | test_mixer.py: test_sample_offset, test_num_samples, test_isolated_note_starts_exactly_at_offset, test_quiet_mix_is_normalised_to_peak_dbfs, test_silence_stays_zero_and_end_is_faded, test_samples_past_the_end_are_dropped, test_scene_audio_buffer_length_follows_simulated_frames |
| FR-103 | test_scale.py: test_c4_major_pentatonic_one_octave, test_defaults_two_octaves_with_top_root, test_mode_intervals, test_root_as_hz_and_voice, test_bad_scale_raises, test_scale_is_compared_by_identity, test_cursor_advances_and_wraps, test_dropped_triggers_do_not_advance_cursor, test_shared_instance_shares_cursor_across_rules, test_separate_instances_have_separate_cursors, test_fresh_scene_restarts_at_first_note |
| FR-106 | test_policy.py: test_gain_curve, test_gain_uses_reference_speed, test_below_min_impact_speed_is_ignored, test_retrigger_interval_per_play_and_object, test_retrigger_interval_counts_from_last_played_note, test_per_frame_cap_drops_later_events_in_order, test_per_frame_cap_in_simulation, test_polyphony_steals_oldest_with_linear_5ms_fade, test_finished_notes_do_not_count_as_sounding; test_events.py::test_rule_produces_trigger_per_matching_event |
| FR-108 | test_mixer.py::test_audio_config_defaults_and_scene; test_policy.py: test_bad_audio_config_names_field_and_value, test_audio_config_edge_values_and_coercion |
| FR-109 | test_audio_export.py: test_write_wav_float32_roundtrip, test_render_with_sound_muxes_aac, test_render_without_sound_rules_has_no_audio_stream, test_temp_files_removed_when_mux_fails, test_mux_failure_raises_with_stderr, test_mux_command_flags |
| NFR-101 | test_events.py: test_same_seed_identical_events_and_audio, test_different_seed_differs; test_mixer.py::test_mix_is_deterministic; test_voices.py::test_mix_with_every_voice_is_deterministic |
| NFR-102 | test_mixer.py::test_isolated_note_starts_exactly_at_offset; test_audio_export.py::test_render_with_sound_muxes_aac (durations within 50 ms) |
| NFR-103 | test_mixer.py::test_two_hundred_full_gain_triggers_respect_headroom |

## Status

M0 complete and reviewed. M1 (audio) in progress: T-101, T-102, T-103 done; next: T-104.
