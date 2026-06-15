"""Modal overlays for the Aether terminal visualizer.

Phase 1 of the TUI refactor (see REFACTOR.md): the style-picker and config
menu are lifted verbatim out of `UltimateOscilloscope` so the main file stops
carrying ~435 lines of self-contained modal UI.

These functions currently take the visualizer instance (`viz`) and drive it
directly — they still lean on `viz.safe_addstr`, `viz.draw_static_elements`,
`viz.draw_waveform_grid`, and the config model living on the class. That
coupling is intentional for a behavior-preserving move; decoupling them to a
plain `(stdscr, config_model)` surface is deferred to Phases 2-3.
"""

import curses
import importlib.util
from pathlib import Path


def run_style_picker(viz):
    """Show modern style selection overlay"""
    # Styles live at the project root; this module sits one level down in ui/,
    # so resolve up two parents rather than using this file's directory.
    styles_dir = Path(__file__).resolve().parent.parent / "styles"
    available_styles = sorted(
        [f.stem for f in styles_dir.glob("*.py") if f.stem != "__init__"]
    )

    # Load style metadata
    style_info = []
    for style_name in available_styles:
        style_path = styles_dir / f"{style_name}.py"
        try:
            spec = importlib.util.spec_from_file_location(style_name, style_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            style_info.append(
                {
                    "name": style_name,
                    "display": getattr(module, "STYLE_NAME", style_name),
                    "desc": getattr(module, "STYLE_DESCRIPTION", ""),
                    "module": module,
                }
            )
        except Exception:
            continue

    # Get current style name for highlighting
    current_style = getattr(viz.style, "STYLE_NAME", "")

    # Menu sizing
    max_visible_items = max(5, viz.height - 10)
    visible_count = min(len(style_info), max_visible_items)

    menu_width = min(55, viz.width - 4)
    menu_height = (
        visible_count + 6
    )  # top + subtitle + divider + items + divider + bottom
    menu_y = max(2, (viz.height - menu_height) // 2)
    menu_x = max(2, (viz.width - menu_width) // 2)

    scroll_offset = 0
    selected_idx = 0  # Keyboard navigation

    # Find current style in list
    for i, info in enumerate(style_info):
        if info["display"] == current_style:
            selected_idx = i
            if i >= visible_count:
                scroll_offset = i - visible_count + 1
            break

    viz.stdscr.nodelay(False)

    while True:
        # Clear the menu area with spaces (no reverse, just empty)
        for y in range(menu_y, min(menu_y + menu_height, viz.height)):
            viz.safe_addstr(y, menu_x, " " * menu_width, 0)

        # Draw box border
        # Top
        viz.safe_addstr(
            menu_y, menu_x, "┌" + "─" * (menu_width - 2) + "┐", curses.color_pair(3)
        )
        # Sides
        for y in range(menu_y + 1, menu_y + menu_height - 1):
            viz.safe_addstr(y, menu_x, "│", curses.color_pair(8))
            viz.safe_addstr(y, menu_x + menu_width - 1, "│", curses.color_pair(8))
        # Bottom
        viz.safe_addstr(
            menu_y + menu_height - 1,
            menu_x,
            "└" + "─" * (menu_width - 2) + "┘",
            curses.color_pair(8),
        )

        # Title
        title = " ◈ SELECT STYLE "
        title_x = menu_x + (menu_width - len(title)) // 2
        viz.safe_addstr(
            menu_y, title_x, title, curses.color_pair(3) | curses.A_BOLD
        )

        # Subtitle line
        subtitle = f"{len(style_info)} styles available"
        viz.safe_addstr(menu_y + 1, menu_x + 3, subtitle, curses.color_pair(8))

        # Divider after subtitle
        viz.safe_addstr(
            menu_y + 2,
            menu_x,
            "├" + "─" * (menu_width - 2) + "┤",
            curses.color_pair(8),
        )

        # Scroll indicators (on the divider lines)
        if scroll_offset > 0:
            viz.safe_addstr(
                menu_y + 2,
                menu_x + menu_width - 3,
                "▲",
                curses.color_pair(6) | curses.A_BOLD,
            )
        if scroll_offset + visible_count < len(style_info):
            viz.safe_addstr(
                menu_y + 3 + visible_count,
                menu_x + menu_width - 3,
                "▼",
                curses.color_pair(6) | curses.A_BOLD,
            )

        # List styles
        for i in range(visible_count):
            idx = scroll_offset + i
            if idx >= len(style_info):
                break

            info = style_info[idx]
            row = menu_y + 3 + i

            # Key label (1-9, then a-z)
            if idx < 9:
                key_label = str(idx + 1)
            else:
                key_label = chr(ord("a") + idx - 9)

            is_selected = idx == selected_idx
            is_current = info["display"] == current_style

            # Clear the row first
            viz.safe_addstr(row, menu_x + 1, " " * (menu_width - 2), 0)

            if is_selected:
                # Selected: cyan arrow and bright text
                viz.safe_addstr(
                    row, menu_x + 2, "▸", curses.color_pair(3) | curses.A_BOLD
                )
                viz.safe_addstr(
                    row, menu_x + 4, key_label, curses.color_pair(6) | curses.A_BOLD
                )
                viz.safe_addstr(row, menu_x + 5, ".", curses.color_pair(3))
                viz.safe_addstr(
                    row,
                    menu_x + 7,
                    info["display"][: menu_width - 14],
                    curses.color_pair(3) | curses.A_BOLD,
                )
            else:
                # Not selected: dimmer
                viz.safe_addstr(row, menu_x + 4, key_label, curses.color_pair(6))
                viz.safe_addstr(row, menu_x + 5, ".", curses.color_pair(8))
                name_color = (
                    curses.color_pair(1) if is_current else curses.color_pair(8)
                )
                viz.safe_addstr(
                    row, menu_x + 7, info["display"][: menu_width - 14], name_color
                )

            # Current style indicator
            if is_current:
                viz.safe_addstr(
                    row,
                    menu_x + menu_width - 4,
                    "✓",
                    curses.color_pair(1) | curses.A_BOLD,
                )

        # Footer divider and hints
        footer_y = menu_y + 3 + visible_count
        viz.safe_addstr(
            footer_y,
            menu_x,
            "├" + "─" * (menu_width - 2) + "┤",
            curses.color_pair(8),
        )

        hints = "↑↓ Navigate  Enter Select  Esc Cancel"
        hint_x = menu_x + (menu_width - len(hints)) // 2
        viz.safe_addstr(footer_y + 1, hint_x, hints, curses.color_pair(8))

        viz.stdscr.refresh()

        key = viz.stdscr.getch()

        if key == 27:  # ESC
            break
        elif key == curses.KEY_UP or key == ord("k"):
            selected_idx = max(0, selected_idx - 1)
            if selected_idx < scroll_offset:
                scroll_offset = selected_idx
        elif key == curses.KEY_DOWN or key == ord("j"):
            selected_idx = min(len(style_info) - 1, selected_idx + 1)
            if selected_idx >= scroll_offset + visible_count:
                scroll_offset = selected_idx - visible_count + 1
        elif key == curses.KEY_PPAGE:
            selected_idx = max(0, selected_idx - visible_count)
            scroll_offset = max(0, scroll_offset - visible_count)
        elif key == curses.KEY_NPAGE:
            selected_idx = min(len(style_info) - 1, selected_idx + visible_count)
            scroll_offset = min(
                len(style_info) - visible_count, scroll_offset + visible_count
            )
        elif key == 10 or key == curses.KEY_ENTER:  # Enter
            if 0 <= selected_idx < len(style_info):
                viz.style = style_info[selected_idx]["module"]
                break
        elif ord("1") <= key <= ord("9"):
            choice = key - ord("0") - 1
            if 0 <= choice < len(style_info):
                viz.style = style_info[choice]["module"]
                break
        elif ord("a") <= key <= ord("z"):
            choice = key - ord("a") + 9
            if 0 <= choice < len(style_info):
                viz.style = style_info[choice]["module"]
                break
        elif ord("A") <= key <= ord("Z"):
            choice = key - ord("A") + 9
            if 0 <= choice < len(style_info):
                viz.style = style_info[choice]["module"]
                break

    viz.stdscr.nodelay(True)
    viz.stdscr.clear()
    viz.draw_static_elements()
    viz.draw_waveform_grid()


def run_config_menu(viz):
    """Show real-time configuration overlay with presets"""
    selected_idx = 0
    current_preset = None  # Track which preset is active

    # Menu sizing - add room for presets
    menu_width = min(58, viz.width - 4)
    menu_height = len(viz.config_keys) + 8  # Extra rows for presets
    menu_y = max(2, (viz.height - menu_height) // 2)
    menu_x = max(2, (viz.width - menu_width) // 2)

    viz.stdscr.nodelay(False)

    while True:
        # Clear menu area
        for y in range(menu_y, min(menu_y + menu_height, viz.height)):
            viz.safe_addstr(y, menu_x, " " * menu_width, 0)

        # Draw box
        viz.safe_addstr(
            menu_y, menu_x, "┌" + "─" * (menu_width - 2) + "┐", curses.color_pair(6)
        )
        for y in range(menu_y + 1, menu_y + menu_height - 1):
            viz.safe_addstr(y, menu_x, "│", curses.color_pair(8))
            viz.safe_addstr(y, menu_x + menu_width - 1, "│", curses.color_pair(8))
        viz.safe_addstr(
            menu_y + menu_height - 1,
            menu_x,
            "└" + "─" * (menu_width - 2) + "┘",
            curses.color_pair(8),
        )

        # Title
        title = " ◈ CONFIGURATION "
        title_x = menu_x + (menu_width - len(title)) // 2
        viz.safe_addstr(
            menu_y, title_x, title, curses.color_pair(6) | curses.A_BOLD
        )

        # Preset buttons row
        preset_y = menu_y + 1
        viz.safe_addstr(preset_y, menu_x + 3, "PRESETS:", curses.color_pair(8))

        presets_display = [
            ("1", "Phosphor", "phosphor"),
            ("2", "EDM", "edm"),
            ("3", "Ambient", "ambient"),
            ("0", "Default", "default"),
        ]
        # Add custom preset if it exists
        if "custom" in viz.PRESETS:
            presets_display.append(("4", "Custom", "custom"))
        px = menu_x + 12
        for key_char, label, preset_name in presets_display:
            is_active = current_preset == preset_name
            viz.safe_addstr(preset_y, px, "[", curses.color_pair(8))
            viz.safe_addstr(
                preset_y, px + 1, key_char, curses.color_pair(6) | curses.A_BOLD
            )
            viz.safe_addstr(preset_y, px + 2, "]", curses.color_pair(8))
            label_attr = (
                curses.color_pair(1) | curses.A_BOLD
                if is_active
                else curses.color_pair(8)
            )
            viz.safe_addstr(preset_y, px + 3, label, label_attr)
            px += len(label) + 5

        # Divider after presets
        viz.safe_addstr(
            menu_y + 2,
            menu_x,
            "├" + "─" * (menu_width - 2) + "┤",
            curses.color_pair(8),
        )

        # Draw each setting
        for i, cfg_key in enumerate(viz.config_keys):
            row = menu_y + 3 + i
            schema = viz.CONFIG_SCHEMA[cfg_key]
            default, min_val, max_val, step, name, desc = schema
            current = viz._get_config_value(cfg_key)

            is_selected = i == selected_idx

            # Clear row
            viz.safe_addstr(row, menu_x + 1, " " * (menu_width - 2), 0)

            # Selection indicator
            if is_selected:
                viz.safe_addstr(
                    row, menu_x + 2, "▸", curses.color_pair(6) | curses.A_BOLD
                )
                name_attr = curses.color_pair(6) | curses.A_BOLD
            else:
                name_attr = curses.color_pair(8)

            # Setting name (shortened)
            viz.safe_addstr(row, menu_x + 4, name[:14], name_attr)

            # Value bar visualization
            bar_x = menu_x + 19
            bar_width = 18

            # Calculate fill percentage
            value_range = max_val - min_val
            fill_pct = (current - min_val) / value_range if value_range > 0 else 0
            fill_chars = int(fill_pct * bar_width)

            # Draw bar background
            viz.safe_addstr(row, bar_x, "░" * bar_width, curses.color_pair(8))

            # Draw bar fill
            if fill_chars > 0:
                bar_color = (
                    curses.color_pair(1) if is_selected else curses.color_pair(3)
                )
                viz.safe_addstr(
                    row,
                    bar_x,
                    "█" * min(fill_chars, bar_width),
                    bar_color | curses.A_BOLD,
                )

            # Value display
            if isinstance(current, float):
                if current >= 100:
                    val_str = f"{current:.0f}"
                elif current >= 10:
                    val_str = f"{current:.1f}"
                else:
                    val_str = f"{current:.2f}"
            else:
                val_str = str(int(current))
            val_attr = curses.color_pair(3) if is_selected else curses.color_pair(8)
            viz.safe_addstr(row, bar_x + bar_width + 1, val_str.rjust(5), val_attr)

        # Footer divider
        footer_y = menu_y + 3 + len(viz.config_keys)
        viz.safe_addstr(
            footer_y,
            menu_x,
            "├" + "─" * (menu_width - 2) + "┤",
            curses.color_pair(8),
        )

        # Hints
        hints = "↑↓ ←→ Adjust  R Reset  W Save  Esc Close"
        hint_x = menu_x + (menu_width - len(hints)) // 2
        viz.safe_addstr(footer_y + 1, hint_x, hints, curses.color_pair(8))

        viz.stdscr.refresh()

        # Get input
        input_key = viz.stdscr.getch()

        if input_key == 27:  # ESC
            break
        elif input_key == curses.KEY_UP or input_key == ord("k"):
            selected_idx = max(0, selected_idx - 1)
        elif input_key == curses.KEY_DOWN or input_key == ord("j"):
            selected_idx = min(len(viz.config_keys) - 1, selected_idx + 1)
        elif input_key == curses.KEY_LEFT or input_key == ord("h"):
            cfg_key = viz.config_keys[selected_idx]
            schema = viz.CONFIG_SCHEMA[cfg_key]
            step = schema[3]
            current = viz._get_config_value(cfg_key)
            viz._set_config_value(cfg_key, current - step)
            current_preset = None  # Clear preset indicator
        elif input_key == curses.KEY_RIGHT or input_key == ord("l"):
            cfg_key = viz.config_keys[selected_idx]
            schema = viz.CONFIG_SCHEMA[cfg_key]
            step = schema[3]
            current = viz._get_config_value(cfg_key)
            viz._set_config_value(cfg_key, current + step)
            current_preset = None
        elif input_key in (ord("r"), ord("R")):
            # Reset selected setting to default
            cfg_key = viz.config_keys[selected_idx]
            default = viz.CONFIG_SCHEMA[cfg_key][0]
            viz._set_config_value(cfg_key, default)
            current_preset = None
        elif input_key == ord("1"):
            viz._load_preset("phosphor")
            current_preset = "phosphor"
        elif input_key == ord("2"):
            viz._load_preset("edm")
            current_preset = "edm"
        elif input_key == ord("3"):
            viz._load_preset("ambient")
            current_preset = "ambient"
        elif input_key == ord("0"):
            viz._load_preset("default")
            current_preset = "default"
        elif input_key == ord("4"):
            # Load custom preset if it exists
            if "custom" in viz.PRESETS:
                viz._load_preset("custom")
                current_preset = "custom"
        elif input_key in (ord("w"), ord("W")):
            # Save current settings as custom preset
            viz.PRESETS["custom"] = {
                key: viz._get_config_value(key) for key in viz.config_keys
            }
            current_preset = "custom"

    viz.stdscr.nodelay(True)
    viz.stdscr.clear()
    viz.draw_static_elements()
    viz.draw_waveform_grid()
