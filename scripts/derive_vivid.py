# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Derive ghostty/Mint-Y-Vivid from Mint-Y's accent colours.

Every hue is one of Linux Mint's own Mint-Y accents, held fixed in OKLCH
(one exception: Mint-Y has no yellow, so Sand is warmed to gold). Lightness
and chroma are what change: each accent is pushed to rich, saturated colour
just above the contrast floor, so the six read as one vivid family, a
styling idea taken from Monokai Pro (no Monokai Pro colour values are used).
Chroma is capped, then clipped to the sRGB gamut at that lightness.

Run with `uv run scripts/derive_vivid.py`; it rewrites the theme file.
"""

import math

from check_contrast import ROOT, contrast

OUT = ROOT / "ghostty" / "Mint-Y-Vivid"

# Bright twins sit this much higher in OKLab lightness, at reduced chroma.
BRIGHT_LIFT = 0.06
BRIGHT_CHROMA = 0.9

# slot: (Mint-Y accent, its hex, target OKLab lightness, chroma cap, hue turn)
ACCENTS = {
    # Pink rather than Red: a hot, pink-leaning red
    1: ("Pink", "#e54980", 0.735, 0.19, 0),
    2: ("Mint-Y green", "#35a854", 0.82, 0.19, 0),
    # Mint-Y has no yellow. Sand is its stand-in, but at Sand's own hue sRGB
    # only reaches a pale peach this light, so it is warmed 18 degrees to gold
    3: ("Sand", "#c5a07c", 0.86, 0.19, 18),
    # Aqua rather than Blue: a blue that leans towards cyan
    4: ("Aqua", "#1f9ede", 0.76, 0.19, 0),
    5: ("Purple", "#8c5dd9", 0.73, 0.19, 0),
    # Teal reaches far more chroma than its neighbours at this lightness;
    # the lower cap stops it turning electric
    6: ("Teal", "#199ca8", 0.80, 0.14, 0),
}

# Orange is the sixth accent outside the ANSI 16 (Claude Code's brand colour,
# Starship's duration). Lower lightness than gold keeps the two apart.
ORANGE = ("Orange", "#ff7139", 0.74, 0.19)

GREYS = {
    "background": ("window title bar and menus (wm_bg)", "#222226"),
    "foreground": ("Cinnamon panel text #e1e1e1, brightened", "#f0f0f0"),
    "palette0": ("panel grey", "#303036"),
    "palette7": ("panel secondary text", "#c3c3c3"),
    "palette8": ("Grey accent: dim text, autosuggestions", "#70737a"),
    "palette15": ("white", "#ffffff"),
    "selection-background": ("panel highlight grey", "#44444c"),
}


def linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def to_oklch(hex_colour: str) -> tuple[float, float, float]:
    h = hex_colour.lstrip("#")
    r, g, b = (linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4))
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (math.cbrt(v) for v in lms)
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness, math.hypot(a, b_), math.degrees(math.atan2(b_, a)) % 360


def from_oklch(lightness: float, chroma: float, hue: float) -> list[float]:
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    return [gamma(v) for v in rgb]


def in_gamut(rgb: list[float]) -> bool:
    return all(-1e-9 <= v <= 1 + 1e-9 for v in rgb)


def place(source: str, lightness: float, chroma_cap: float, turn: float = 0) -> str:
    """Source hue (turned by `turn` degrees) at the given lightness, with the
    most chroma up to the cap that sRGB can show there."""
    hue = to_oklch(source)[2] + turn
    chroma = chroma_cap
    if not in_gamut(from_oklch(lightness, chroma, hue)):
        # binary search for the gamut edge; lo always stays inside it
        lo, hi = 0.0, chroma_cap
        for _ in range(50):
            mid = (lo + hi) / 2
            if in_gamut(from_oklch(lightness, mid, hue)):
                lo = mid
            else:
                hi = mid
        chroma = lo
    rgb = from_oklch(lightness, chroma, hue)
    return "#" + "".join(f"{round(min(max(v, 0), 1) * 255):02x}" for v in rgb)


def derive() -> dict[str, str]:
    colours = {key: value for key, (_, value) in GREYS.items()}
    for slot, (_, source, lightness, cap, turn) in ACCENTS.items():
        colours[f"palette{slot}"] = place(source, lightness, cap, turn)
        colours[f"palette{slot + 8}"] = place(
            source, lightness + BRIGHT_LIFT, cap * BRIGHT_CHROMA, turn
        )
    _, source, lightness, cap = ORANGE
    colours["orange"] = place(source, lightness, cap)
    colours["orange-bright"] = place(
        source, lightness + BRIGHT_LIFT, cap * BRIGHT_CHROMA
    )
    return colours


def render(c: dict[str, str]) -> str:
    def accent(slot: int) -> str:
        name, source, lightness, _, turn = ACCENTS[slot]
        turned = f", warmed {turn} degrees" if turn else ""
        return (
            f"# {name} {source}{turned}, at L {lightness:.3f}\n"
            f"palette = {slot}={c[f'palette{slot}']}"
        )

    lines = [
        "# Mint-Y-Vivid - a rich, vivid Ghostty theme on Linux Mint's Mint-Y-Dark",
        "# greys.",
        "#",
        "# Generated by scripts/derive_vivid.py; edit that, not this file.",
        "#",
        "# Every hue is one of Mint-Y's own accent colours, held fixed in OKLCH",
        "# (Sand, Mint-Y's only yellow, is warmed to gold). Lightness and chroma",
        "# move: each accent is pushed to rich, saturated colour just above the",
        "# contrast floor so they read as one vivid family, a styling idea taken",
        "# from Monokai Pro. No Monokai Pro colour values are used.",
        "#",
        "# Surfaces stay Mint-Y-Dark's, so the terminal still fuses with its",
        "# title bar on Cinnamon.",
        "#",
        "# Design rules (checked by scripts/check_contrast.py):",
        "#   - every regular colour (1-6) clears WCAG 6:1 contrast on the background",
        f"#   - bright colours (9-14) sit {BRIGHT_LIFT} higher in OKLab lightness than",
        "#     their regular twins, at slightly lower chroma",
        "#   - character lives in 1-6; black/white (0/7/15) are not relied upon",
        "#   - orange (Claude Code's brand colour, Starship's duration) lives",
        "#     outside the ANSI 16; it is listed here for reference only:",
        f"#       orange {c['orange']}, bright {c['orange-bright']}  "
        f"(Mint-Y {ORANGE[0]} {ORANGE[1]})",
        "",
        "# -- normal " + "-" * 66,
        f"# {GREYS['palette0'][0]}",
        f"palette = 0={c['palette0']}",
        *(accent(slot) for slot in range(1, 7)),
        f"# {GREYS['palette7'][0]}",
        f"palette = 7={c['palette7']}",
        "",
        "# -- bright " + "-" * 66,
        f"# {GREYS['palette8'][0]}",
        f"palette = 8={c['palette8']}",
        *(f"palette = {slot}={c[f'palette{slot}']}" for slot in range(9, 15)),
        f"palette = 15={c['palette15']}",
        "",
        "# -- ui " + "-" * 70,
        f"# {GREYS['background'][0]}",
        f"background = {c['background']}",
        f"# {GREYS['foreground'][0]}",
        f"foreground = {c['foreground']}",
        "# the green accent, as in Mint-Y-Dark",
        f"cursor-color = {c['palette2']}",
        f"cursor-text = {c['background']}",
        "# a neutral grey selection keeps every accent readable inside it",
        f"selection-background = {c['selection-background']}",
        f"selection-foreground = {c['palette15']}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    colours = derive()
    bg = colours["background"]
    for slot in range(1, 7):
        name = ACCENTS[slot][0]
        regular, bright = colours[f"palette{slot}"], colours[f"palette{slot + 8}"]
        print(
            f"{slot:>2} {name:<13} {regular} {contrast(regular, bg):5.2f}   "
            f"{bright} {contrast(bright, bg):5.2f}"
        )
    orange = colours["orange"]
    print(f"   {'Orange':<13} {orange} {contrast(orange, bg):5.2f}")
    OUT.write_text(render(colours))
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
