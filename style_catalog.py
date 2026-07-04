"""Style discovery and loading for the Aether visualizer.

Phase 5 of the TUI refactor (see REFACTOR.md): the style catalog logic that
was duplicated between `aether.py` (CLI selection) and `ui/overlays.py` (the
in-app picker) lives here. This module is pure discovery/loading — no
printing, no input(), no sys.exit — so it is unit-testable headlessly; the
CLI keeps its prompts and exit behavior in `aether.py`.

The style plugin contract is unchanged: each `styles/*.py` exposes
STYLE_NAME, STYLE_DESCRIPTION, and render_waveform(...).
"""

import importlib.util
from pathlib import Path

STYLES_DIR = Path(__file__).resolve().parent / "styles"

# Fallback styles, in preference order, when a requested style fails to load.
DEFAULT_STYLES = ("neon_wave", "classic_wave")


def list_style_names(styles_dir=STYLES_DIR):
    """Sorted style slugs (file stems) available in the styles directory."""
    return sorted(f.stem for f in styles_dir.glob("*.py") if f.stem != "__init__")


def load_style_module(name, styles_dir=STYLES_DIR):
    """Load styles/<name>.py as a module.

    Raises FileNotFoundError if the style does not exist, and propagates
    whatever the module raises if it fails to execute.
    """
    style_path = styles_dir / f"{name}.py"
    if not style_path.exists():
        raise FileNotFoundError(f"Style '{name}' not found at {style_path}")
    spec = importlib.util.spec_from_file_location(name, style_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_catalog(styles_dir=STYLES_DIR):
    """Load every available style, returning a list of catalog entries.

    Each entry is {"name": slug, "display": STYLE_NAME, "desc":
    STYLE_DESCRIPTION, "module": module}, sorted by slug. Styles that fail to
    load are skipped, matching the in-app picker's tolerance.
    """
    catalog = []
    for name in list_style_names(styles_dir):
        try:
            module = load_style_module(name, styles_dir)
        except Exception:
            continue
        catalog.append(
            {
                "name": name,
                "display": getattr(module, "STYLE_NAME", name),
                "desc": getattr(module, "STYLE_DESCRIPTION", ""),
                "module": module,
            }
        )
    return catalog


def _normalize(name):
    """Fold a style reference to slug form: lowercase, separators -> _."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def resolve_style_name(choice, available):
    """Resolve a selection string against the available style slugs.

    Accepts a 1-based number or a name. Names are matched case-insensitively
    with spaces/hyphens folding to underscores, so "matrix_rain",
    "Matrix Rain", and "MATRIX RAIN" all resolve (display names follow the
    slug-with-capitals convention throughout styles/; test_style_catalog
    verifies every catalog display name resolves this way).

    Returns the matching slug, or None if nothing matches.
    """
    choice = choice.strip()
    try:
        idx = int(choice) - 1
    except ValueError:
        normalized = _normalize(choice)
        for name in available:
            if _normalize(name) == normalized:
                return name
        return None
    if 0 <= idx < len(available):
        return available[idx]
    return None


def load_default_style():
    """Load the first fallback style that works, or None if none do."""
    for name in DEFAULT_STYLES:
        try:
            return load_style_module(name)
        except Exception:
            continue
    return None
