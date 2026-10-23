# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Render assets/palette.svg from the Ghostty theme, so the README swatch
can't drift from the real colours.

Run with `uv run scripts/render_swatch.py`.
"""

from pathlib import Path

from check_contrast import ROOT, luminance, parse_ghostty

THEME = ROOT / "ghostty" / "Mint-Y-Dark"
OUT = ROOT / "assets" / "palette.svg"

NAMES = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
CHIP, GAP, PAD = 96, 10, 28
FONT = "ui-monospace, 'JetBrains Mono', SFMono-Regular, Menlo, monospace"


def ink(hex_colour: str) -> str:
    """Pick a label colour that stays readable on the chip."""
    return "#16161a" if luminance(hex_colour) > 0.3 else "#f4f4f5"


def chip(x: int, y: int, colour: str, label: str, h: int = CHIP) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{CHIP}" height="{h}" rx="10" '
        f'fill="{colour}"/>'
        f'<text x="{x + 10}" y="{y + h - 26}" fill="{ink(colour)}" '
        f'font-size="12" opacity="0.75">{label}</text>'
        f'<text x="{x + 10}" y="{y + h - 10}" fill="{ink(colour)}" '
        f'font-size="13" font-weight="700">{colour.lower()}</text>'
    )


def main() -> None:
    t = parse_ghostty(THEME)
    step = CHIP + GAP
    width = PAD * 2 + step * 8 - GAP
    rows = []
    y = PAD + 30
    # label chips by slot number: the bright row (8-15) is the lighter one
    for offset in (0, 8):
        for i, name in enumerate(NAMES):
            slot = i + offset
            rows.append(chip(PAD + i * step, y, t[f"palette{slot}"], f"{slot} {name}"))
        y += step
    ui = [
        ("background", t["background"]),
        ("foreground", t["foreground"]),
        ("cursor", t["cursor-color"]),
        ("selection", t["selection-background"]),
    ]
    ui_w = (width - PAD * 2 - GAP * 3) // 4
    y += 6
    for i, (label, colour) in enumerate(ui):
        x = PAD + i * (ui_w + GAP)
        # outline the background chip, which otherwise vanishes into the card
        stroke = ' stroke="#44444c"' if label == "background" else ""
        rows.append(
            f'<rect x="{x}" y="{y}" width="{ui_w}" height="64" rx="10" '
            f'fill="{colour}"{stroke}/>'
            f'<text x="{x + 12}" y="{y + 26}" fill="{ink(colour)}" '
            f'font-size="12" opacity="0.75">{label}</text>'
            f'<text x="{x + 12}" y="{y + 46}" fill="{ink(colour)}" '
            f'font-size="14" font-weight="700">{colour.lower()}</text>'
        )
    height = y + 64 + PAD
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">'
        f'<rect width="{width}" height="{height}" rx="16" fill="{t["background"]}"/>'
        f'<text x="{PAD}" y="{PAD + 12}" fill="{t["foreground"]}" font-size="15" '
        f'font-weight="700">Mint-Y-Dark</text>'
        f'<text x="{width - PAD}" y="{PAD + 12}" fill="{t["palette8"]}" '
        f'font-size="12" text-anchor="end">ghostty · starship</text>'
        + "".join(rows)
        + "</svg>\n"
    )
    Path(OUT).write_text(svg)
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
