# Aether agent instructions

This file applies to the entire repository.

## Project and ownership

Aether is a Linux audio-analysis pipeline organized around PipeWire capture,
FFT publication, a seqlock shared-memory contract, and independent consumers:
the terminal visualizer, OpenRGB controller, query client, and integrations.
This repository owns their source, tests, documentation, and repository copies
of installer and service definitions. It does not thereby own the live host or
external state those files can affect, including the PipeWire graph or audio
devices, OpenRGB or physical LEDs, Hue bridges and lights, OBS, Discord, Dunst,
status bars, systemd, installed packages, terminal configuration, or files
outside this checkout.

## Authority and context

- Read `README.md` for project-wide purpose and operational/user context.
  Check current code, configuration, tests, and workflows before repeating a
  README current-state claim; report stale or conflicting claims explicitly.
- Read `REFACTOR.md` before architectural changes to the TUI, render layer,
  signal engine, frame loop, or style system. Its chronology is architectural
  history; its recorded ownership decisions and guardrails remain important
  context unless a concrete, authorized change supplies a reason to revise
  them.
- Code, configuration, and tests establish implementation behavior, while
  `.github/workflows/ci.yml` defines checked-in CI automation. They do not
  silently rewrite documented architectural intent. Aether defines no blanket
  precedence that resolves every disagreement; surface conflicts and stop for
  direction when the owning authority or authorized resolution is unclear.
- Integration README files, service units, and installers describe supported
  integration paths. Their presence is not authorization to execute them or
  mutate their targets.
- Do not put task counts, branch state, commit IDs, process state, CI drift, or
  handoff/session status into durable project instructions.

## Repository and live-system boundary

Repository mutation and live-system mutation are separate permissions. Editing
or testing this checkout does not authorize starting persistent Aether daemons
or consumers; restarting or enabling systemd units; installing packages or
files; changing the PipeWire graph, audio devices, terminal, desktop, or host
configuration; writing RGB hardware or Hue lights; changing OBS input state;
publishing Discord presence; or changing Dunst or status-bar state. Obtain
explicit authorization before any such consequential action.

The daemon's normal path creates or updates shared-memory/runtime files and
starts `pw-record`; the RGB and integration entrypoints contact live services
or devices. Do not invoke those paths as ordinary validation. Other host state
and neighboring repositories may be inspected read-only when necessary for
evidence, but must not be modified without explicit authorization.

## Architectural boundaries

- Treat `aether_shm.py` as a versioned interprocess compatibility boundary, not
  ordinary in-process state. Changes to its header layout, magic/version,
  sizing, serialization or event schema, sequence rules, seqlock ordering,
  reader/writer assumptions, or legacy fallback must account for the daemon
  producer and every consumer, including `aether.py`, `aether_rgb.py`,
  `aether_client.py`, and integrations. Preserve the odd/in-progress and
  even/committed sequence semantics unless a deliberate protocol migration is
  in scope and compatibility is addressed explicitly.
- Preserve the producer/consumer broadcast model. PipeWire capture and FFT
  publication belong to the daemon; the TUI, RGB controller, query client, and
  external integrations consume published state independently. Do not couple
  a consumer's lifecycle or behavior back into capture as an incidental part
  of unrelated work.
- The style compatibility surface is `STYLE_NAME`, `STYLE_DESCRIPTION`, and
  `render_waveform(...)`. Optional `render_frame(ctx, canvas)` is additive;
  frame styles retain the legacy entrypoint as a fallback. Do not silently
  replace, narrow, or redesign this API during unrelated visualization work.
- `UltimateOscilloscope` owns terminal geometry, layout mutation through
  `recalculate_layout`, render scratch, loop diagnostics, and SHM polling.
  `render.py` owns generic terminal primitives. Keep layout ownership on the
  oscilloscope unless a concrete change benefits from moving it and accounts
  for the broad draw-state coupling documented in `REFACTOR.md`; abstraction
  symmetry alone is not a reason.
- For the TUI, `engine.VisualizerState` owns headless temporal signal state and
  behavior: waveform/spectrum/RGB-preview buffers, ingestion, smoothing,
  decay, beat pulse, and silence state. Rendering code and styles consume that
  state rather than independently reimplementing signal semantics. Keep daemon
  FFT analysis and device-specific RGB behavior in their existing layers.

## Working tree and generated/runtime state

Inspect Git status before editing. Preserve and investigate unexplained staged,
unstaged, or untracked work; never discard, absorb, normalize, or reclassify it
as part of the current task by assumption.

Treat `.aether_logs/`, shared-memory and legacy event files under `/dev/shm`
and `/tmp`, caches, bytecode, virtual environments and backups, build/package
outputs, PID files, logs, and other runtime or generated artifacts as protected
state. Do not delete, regenerate, relocate, or include them in unrelated work,
and do not add generated/runtime data to Git merely because validation created
or exposed it.

## Validation

The broad local pure-Python test command, with pytest available, is:

```bash
python -m pytest -q
```

Focused `test_*.py` files may also be run directly during development. The CI
workflow additionally byte-compiles an explicit module list and runs explicit
test entries. Consult `.github/workflows/ci.yml` before claiming CI or
repository-wide validation; when modules or tests are added, renamed, or
removed, keep explicit CI lists, direct runs, and repository-wide discovery
coherent rather than assuming one covers the others.

Report exactly what ran and its result. Never claim a check passed because it
was expected to pass. Headless/unit validation is distinct from shared-memory
interoperability with live processes, a real curses terminal, PipeWire/audio,
OpenRGB hardware, Hue, OBS, Discord, Dunst, status bars, systemd, installation,
or deployment. A unit pass neither proves nor authorizes those behaviors.
Perform manual TUI or live integration validation only when it is explicitly in
scope, and report any required validation that was not run.

## Git and publication

Permission to edit does not imply permission to stage, commit, push, fetch,
pull, merge, rebase, rewrite history, publish, deploy, install, or restart a
live instance. Preserve unrelated work and treat each publication, deployment,
installation, and live restart as a separate explicit authorization boundary.

## Skills

User-level generic skills such as `$project-onboarding` may guide an applicable
workflow, but project-local authority and the user's current explicit scope
outrank generic guidance. Invoking a skill does not grant permission to mutate
this repository, the live host, external integrations or devices, or another
repository.
