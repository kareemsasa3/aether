# Refactor Plan: Decomposing the `aether.py` TUI Monolith

> Status: **planning only** — no code has been moved. This document captures
> the investigation and a phased, behavior-preserving extraction plan. Line
> numbers reference `aether.py` as of this writing and will drift as work lands.

## 1. Current State

`aether.py` is a **1671-line TUI monolith**. Aside from a few module-level
loader functions (`load_default_style`, `load_style`, `main`, `cli`), the entire
file is a single god class: **`UltimateOscilloscope`, 31 methods**.

That one class owns, all at once:

- the configuration model (schema, presets, get/set),
- visualizer state (waveform/spectrum/RGB buffers, smoothing targets),
- layout and terminal rendering primitives,
- every view/drawing routine,
- two full modal overlays (style picker, config menu),
- keyboard input handling, and
- the frame loop.

The `styles/` plugin system around it is **already clean** — each style is its
own file loaded dynamically, behind a small contract. The problem is
concentrated entirely in `UltimateOscilloscope`. Leave the style system alone.

## 2. Responsibility Map

| Concern | Methods / definitions | Lines | ~LOC |
|---|---|---|---|
| **Config model** | `CONFIG_SCHEMA`, `PRESETS`, `_init_config`, `_get/_set_config_value`, `_load_preset` | 15–77, 174–208 | ~100 |
| **Layout / render primitives** | color-pair init (in `__init__`), `recalculate_layout`, `get_bg_char`, `safe_addstr` | 91–116, 209–333 | ~140 |
| **Data ingestion** (SHM → state) | `check_for_events`, `update_*_from_bands`, `add_wave`, `add_scroll_sample`, `update_spectrum`, `update_rgb_levels` | 775–968 | ~190 |
| **State + smoothing / decay** | state fields in `__init__`, `decay_all`, `clear_waveform_area`, `clear_spectrum_area` | 118–166, 969–1038 | ~120 |
| **Views / drawing** | `draw_static_elements`, `draw_waveform_grid`, `draw_waveform`, `draw_frame`, `draw_spectrum*`, `draw_rgb_preview`, `draw_debug_stats`, `draw_status` | 334–774 | ~440 |
| **Modal overlays** | `switch_style` (~225 lines), `show_config` (~210 lines) | 1039–1475 | **~435** |
| **Input + frame loop** | `run` | 1476–1557 | ~80 |

The shared mutable `self` is the glue holding these together: nearly every
method reaches into `self.*` state directly. Decomposition is therefore about
**naming the state clusters that travel together** first, not just moving code.

## 3. Existing Seams (build on these)

- **Style plugin contract** — `style.render_waveform(i, amp, age, half_width, colors, sample_id) -> (char, attr) | None`, plus the `STYLE_NAME` / `STYLE_DESCRIPTION` attributes (see `aether.py:481`). Styles already live in separate files loaded via `importlib`. This is the model the rest of the refactor should imitate. **Do not change it.**
- **`check_for_events` ingestion boundary** (`aether.py:775`) — the shared-memory reader is already funneled through one method. The only leak is that it writes results straight into `self.*` rather than into a state object.
- **Schema-driven config** — `CONFIG_SCHEMA` and `PRESETS` are already declarative data. Only the *menu rendering* is entangled with the model; the data is clean.

## 4. Extraction Plan

Ordered lowest-risk → highest. Each phase is independently shippable.

### Phase 1 — Modal overlays → `ui/overlays.py`
**Highest value, lowest risk.** `switch_style` + `show_config` are ~435 lines
(26% of the file) and are self-contained modal UIs: each clears the screen, runs
its own input sub-loop, and returns. Their only real dependencies are `stdscr`,
the available style list, and the config model. Extract as plain functions, e.g.
`run_style_picker(stdscr, current_style) -> style_module` and
`run_config_menu(stdscr, config_model)`. Removes a quarter of the file with
almost no coupling risk.

### Phase 2 — Config model → `config_model.py`
`CONFIG_SCHEMA`, `PRESETS`, and the four `_*config*` methods become a small
`VizConfig` class holding the values with `get` / `set` / `load_preset`. The
Phase 1 overlay then receives a `VizConfig` instead of reaching into the
oscilloscope. Testable in isolation — no curses required.

### Phase 3 — Render / layout primitives → `render.py`
`safe_addstr`, `get_bg_char`, color-pair init, and `recalculate_layout` are
generic terminal/geometry helpers with no domain logic. Pulling them out gives
the draw methods a thin, explicit surface to call.

### Phase 4 — Visualizer state / ingestion / decay → `engine.py`
A `VisualizerState` that owns the waveform/spectrum/RGB buffers and exposes
`ingest(event)` and `decay()` — pure data, no curses. Biggest testability win
(smoothing and decay become unit-testable the way the seqlock now is), but also
the most invasive, since every `draw_*` reads this state. Do it **last**, after
Phases 1–3 have proven the boundaries.

## 5. Guardrails

- **Do not split the `draw_*` view methods before extracting state (Phase 4).**
  They are glued to `self` state; moving them first creates circular
  dependencies.
- **Do not change the style plugin API.** It is the one clean seam — preserve
  `render_waveform`'s signature and the `STYLE_NAME` / `STYLE_DESCRIPTION`
  attributes exactly.
- **Keep each phase strictly behavior-preserving.** These are moves, not
  redesigns; no feature or visual change should accompany a phase.
- **One phase per commit.** Each phase is reviewable on its own and easy to
  revert.
- **Phase 1 must be verified manually in the running TUI** — there is no
  automated curses coverage yet, so a human has to confirm the style picker and
  config menu still behave. (Contrast: the seqlock IPC and config wiring *do*
  have automated tests; the TUI does not.)

## 6. Recommended Next Change

**Phase 1 only:** extract `switch_style` and `show_config` into `ui/overlays.py`.
Treat it as a standalone, behavior-preserving refactor — the cleanest cut, the
largest line reduction, and the lowest coupling risk of the four phases. Do not
begin a later phase in the same change.
