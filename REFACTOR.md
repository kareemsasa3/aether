# Refactor: Decomposing the `aether.py` TUI Monolith

> Status: **Phases 1–4a complete.** The original 1671-line `aether.py` monolith
> has been carved into `ui/overlays.py`, `config_model.py`, `render.py`, and
> `engine.py`, each behind a tested seam. `aether.py` is now ~929 lines.
> Remaining work (Phase 4b/4c and small cleanups) is **optional** and listed at
> the end — none of it is required for the codebase to be in a good state.
>
> Each phase was landed as its own behavior-preserving commit, with automated
> tests where the logic is headless and a manual TUI smoke (the curses UI has no
> automated coverage). The suite is currently **39 tests**.

## Starting point (for context)

`aether.py` was a single god class — `UltimateOscilloscope` — that owned the
config model, visualizer signal state, layout + render primitives, every draw
routine, two modal overlays, input handling, and the frame loop. The `styles/`
plugin system around it was already clean (each style a file behind a small
`render_waveform(...)` contract) and was **left untouched** throughout.

The decomposition principle: name the state clusters that travel together and
extract them one seam at a time, lowest-risk first, never changing the style
plugin API and never splitting draw methods ahead of the state they read.

## Completed work

### Phase 1 — Modal overlays → `ui/overlays.py` ✅
- Commit: `b4ffb25 Extract Aether overlay menus`
- The two self-contained modal UIs (`switch_style` ~225 lines, `show_config`
  ~210 lines) moved into `ui/overlays.py` as `run_style_picker` /
  `run_config_menu`. The oscilloscope keeps `switch_style()` / `show_config()`
  as thin delegators.
- Manual TUI smoke passed for the style and config overlays.

### Phase 2 — Config model → `config_model.py` ✅
- Commit: `a0b1d00 Extract Aether config model`
- Added `config_model.py` with `VizConfig`, `CONFIG_SCHEMA`, and `PRESETS`. The
  oscilloscope holds a `VizConfig` and delegates the get/set/preset helpers to
  it; schema/presets are byte-identical to the originals.
- Added `test_config_model.py`; CI updated.
- Manual TUI config smoke passed.

### Phase 3 — Render primitives → `render.py` ✅
- Commit: `0fb2778 Extract Aether render primitives`
- Moved `safe_addstr`, `get_bg_char`, and the curses color-pair initialization
  into `render.py` (kept as delegators on the oscilloscope so the ~79 call
  sites and the overlays stay unchanged).
- **Deliberately left `recalculate_layout` in `UltimateOscilloscope`**: the
  coupling audit found it mutates ~25 instance fields (geometry, waveform
  buffers, perf counters), so it is layout *state*, not a render primitive.
- Added `test_render.py`; CI updated.
- Manual TUI smoke passed, including terminal resize.

### Phase 4a — Pure visualizer state → `engine.py` ✅
- Commit: `e06d12e Extract Aether visualizer state`
- Added `engine.py` with `VisualizerState`, which now owns the waveform/
  spectrum/RGB buffers, the smoothing scalars, the signal constants
  (`BAND_FREQS`, `BAND_TO_BINS`, `SPECTRUM_DECAY_LEGACY`), and the
  ingestion/decay/smoothing math: `ingest(event, config)`, `decay(config)`,
  `add_scroll_sample(config)`, `resize(half_width)`, and the per-band/legacy
  updaters.
- `check_for_events` still owns the SHM read, perf counters, and
  `last_event_time`; it delegates event dispatch to `state.ingest(...)`.
  `add_scroll_sample()` / `decay_all()` remain as delegators so the frame loop
  is unchanged.
- **Read-only compatibility properties** on `UltimateOscilloscope` forward the
  fields draw/status methods read (`spectrum_values`, the waveform deques,
  `bass/mid/treble_level`, `current_freq`) to `self.state.*`, so **no draw
  method was edited**.
- Left in place: geometry + `recalculate_layout`, `last_ys`, perf counters, the
  SHM object and event loop, overlays, render primitives, config model, and the
  style plugin API.
- Added `test_engine.py` (init, resize grow/shrink + padding, legacy & banded
  spectrum, RGB clamp math, both dispatch paths, smoothing/sample-count, decay).
- Manual TUI smoke passed for launch/render, oscilloscope mode, spectrum mode,
  RGB preview, config overlay, style overlay, and resize.

## The Phase 4 split decision

Phase 4 (originally "visualizer state / ingestion / decay") was split once the
coupling audit clarified what was safe to move:

- **4a — pure ingestion/decay/smoothing engine.** ✅ Completed. Headless and
  testable; no geometry, no curses.
- **4b — geometry / buffer / layout-state ownership.** **Deferred.** Moving the
  geometry fields and `recalculate_layout` out of `UltimateOscilloscope` would
  require broad read-surface churn across the `draw_*` / `clear_*` methods,
  which read geometry throughout the TUI.
- **4c — direct `viz.state.<field>` reads / removing the compatibility
  properties.** **Optional**, and likely not worth doing unless future work
  specifically benefits from it.

Rationale, recorded so the next person doesn't re-litigate it:
- 4a was self-contained and unit-testable, so it carried the real risk (the
  signal math) with the least collateral change.
- `recalculate_layout` is layout/state mutation, **not** a render primitive — it
  was correctly left behind in Phase 3 and remains out of scope.
- `last_ys` is render scratch (written mid-draw), **not** signal-engine state.
- The performance counters are loop diagnostics, **not** signal state.

## Loose ends / optional future work

None of these are required; they are noted for a future handoff.

- Remove the dead `event_file` field (assigned in `__init__`, never read) in a
  small separate cleanup commit.
- Consider migrating `ui/overlays.py` to accept `VizConfig` and the render
  helpers directly instead of the full `viz` object, retiring the transitional
  config delegators.
- Consider retiring the delegator/proxy methods only if it materially helps
  future work — otherwise they are harmless and keep call sites stable.
- Consider **4b** only if there is a concrete need to move geometry/layout state
  out of `UltimateOscilloscope`.
- Consider **4c** only if direct `viz.state.<field>` reads are preferred over
  the compatibility properties; otherwise leave the shims in place.

## Guardrails (still in force for any future phase)

- **Do not change the style plugin API** — `render_waveform`'s signature and the
  `STYLE_NAME` / `STYLE_DESCRIPTION` attributes are the one clean seam.
- **Do not split `draw_*` methods ahead of the state they read.**
- **Keep each phase behavior-preserving** — moves, not redesigns; one phase per
  commit.
- **Manually smoke the TUI** after each phase — the curses UI has no automated
  coverage, though the engine, config, render, and IPC layers now do.
