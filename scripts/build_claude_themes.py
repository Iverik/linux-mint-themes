# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Build the Claude Code themes in claude-code/ from the Ghostty themes, so
the two can't drift apart.

Each Ghostty theme becomes two Claude Code themes:

- `<theme>.json` (base `dark`): exact colours, works in any terminal. Code
  blocks use Claude Code's built-in Monokai-style syntax colours, which a
  custom theme cannot change.
- `<theme>-ansi.json` (base `dark-ansi`): accents are ANSI slot names, so they
  resolve through the terminal palette, and code blocks are highlighted with
  it too. Pick this one when the terminal runs the matching Ghostty theme.
  An ANSI base renders in 256 colours, so colours without an ANSI slot
  (greys, orange) are written as their nearest xterm-256 colour, and the diff
  tints use the 256-colour cube's dark greens and reds.

Run with `uv run scripts/build_claude_themes.py`.
"""

import json
import math

from check_contrast import ROOT, parse_ghostty, xterm256
from derive_vivid import ORANGE, derive, place, to_oklch

OUT = ROOT / "claude-code"
SCHEMA = (
    "https://raw.githubusercontent.com/matcra587/claude-themes/main/"
    "schemas/theme.schema.json"
)
ANSI = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]

# Cinnamon panel greys shared by both themes (see starship/mint-y-dark.toml)
RAIL0, RAIL2, RAIL3, DIMMED = "#29292e", "#38383e", "#44444c", "#a8a8a8"

# Per theme: the brand colour (spinner, Claude label, Clawd) and orange.
# Mint-Y-Dark's brand is the Mint-Y green itself; Mint-Y-Vivid's is Mint-Y
# Orange, which also matches Claude Code's own warm brand colour.
VIVID = derive()
BRAND = {
    "Mint-Y-Dark": {
        "claude": "palette2",
        "claudeShimmer": "palette10",
        # Mint-Y-Dark has no orange of its own; lift Mint-Y Orange the same
        # way its other accents were lifted (hue held)
        "orange": place(ORANGE[1], 0.74, 0.17),
        "orange-bright": place(ORANGE[1], 0.80, 0.15),
    },
    "Mint-Y-Vivid": {
        "claude": "orange",
        "claudeShimmer": "orange-bright",
        "orange": VIVID["orange"],
        "orange-bright": VIVID["orange-bright"],
    },
}

# Token -> palette key. Keys are Ghostty theme keys, BRAND keys, or the
# literal greys above.
ROLES = {
    "text": "foreground",
    "inverseText": "background",
    # three-tier dim hierarchy: faint borders < hints < hint shimmer
    "subtle": "palette8",
    "inactive": DIMMED,
    "inactiveShimmer": "palette7",
    "promptBorder": "palette8",
    "promptBorderShimmer": DIMMED,
    "claude": "claude",
    "claudeShimmer": "claudeShimmer",
    "clawd_body": "claude",
    "clawd_background": "background",
    "briefLabelClaude": "claude",
    "briefLabelYou": "palette4",
    "claudeBlue_FOR_SYSTEM_SPINNER": "palette4",
    "claudeBlueShimmer_FOR_SYSTEM_SPINNER": "palette12",
    "permission": "palette4",
    "permissionShimmer": "palette12",
    "suggestion": "palette12",
    "ide": "palette4",
    "professionalBlue": "palette4",
    "remember": "palette14",
    "background": "palette6",
    "planMode": "palette6",
    "autoAccept": "palette5",
    "autoAcceptShimmer": "palette13",
    "skill": "palette5",
    "effortUltra": "palette5",
    "merged": "palette5",
    "bashBorder": "palette1",
    "success": "palette2",
    "error": "palette1",
    "warning": "palette3",
    "warningShimmer": "palette11",
    "chromeYellow": "palette3",
    "fastMode": "orange",
    "fastModeShimmer": "orange-bright",
    "rate_limit_fill": "palette4",
    "rate_limit_empty": RAIL3,
    "userMessageBackground": "palette0",
    "userMessageBackgroundHover": RAIL2,
    "composerSidebarBackground": RAIL0,
    "selectionBg": "selection-background",
    "red_FOR_SUBAGENTS_ONLY": "palette1",
    "orange_FOR_SUBAGENTS_ONLY": "orange",
    "yellow_FOR_SUBAGENTS_ONLY": "palette3",
    "green_FOR_SUBAGENTS_ONLY": "palette2",
    "cyan_FOR_SUBAGENTS_ONLY": "palette6",
    "blue_FOR_SUBAGENTS_ONLY": "palette4",
    "purple_FOR_SUBAGENTS_ONLY": "palette5",
    "pink_FOR_SUBAGENTS_ONLY": "palette9",
    "rainbow_red": "palette1",
    "rainbow_orange": "orange",
    "rainbow_yellow": "palette3",
    "rainbow_green": "palette2",
    "rainbow_blue": "palette6",
    "rainbow_indigo": "palette4",
    "rainbow_violet": "palette5",
    "rainbow_red_shimmer": "palette9",
    "rainbow_orange_shimmer": "orange-bright",
    "rainbow_yellow_shimmer": "palette11",
    "rainbow_green_shimmer": "palette10",
    "rainbow_blue_shimmer": "palette14",
    "rainbow_indigo_shimmer": "palette12",
    "rainbow_violet_shimmer": "palette13",
}

# Tinted surfaces: (accent key, share of the accent mixed into the background).
# Diff lines stay dark enough for syntax colours on top; word highlights are
# stronger but still keep the foreground readable (checked by check_contrast).
TINTS = {
    "diffAdded": ("palette2", 0.22),
    "diffRemoved": ("palette1", 0.22),
    "diffAddedWord": ("palette2", 0.42),
    "diffRemovedWord": ("palette1", 0.42),
    "diffAddedDimmed": ("palette2", 0.10),
    "diffRemovedDimmed": ("palette1", 0.10),
    "bashMessageBackgroundColor": ("palette1", 0.10),
    "memoryBackgroundColor": ("palette14", 0.10),
}


# Tints for the ANSI variants, as xterm-256 indices. The cube has no dark,
# lightly tinted colours, so these follow the usual 256-colour diff
# convention (delta, git): dark green/red lines, brighter word highlights.
# Dimmed (rejected) diffs and message backgrounds go neutral.
ANSI_TINTS = {
    "diffAdded": 22,
    "diffRemoved": 52,
    "diffAddedWord": 28,
    "diffRemovedWord": 88,
    "diffAddedDimmed": 236,
    "diffRemovedDimmed": 236,
    "bashMessageBackgroundColor": 236,
    "memoryBackgroundColor": 236,
}


def nearest256(hex_colour: str) -> str:
    """The xterm-256 colour (16-255) closest to hex_colour in OKLab."""

    def lab(c: str) -> tuple[float, float, float]:
        lightness, chroma, hue = to_oklch(c)
        return (
            lightness,
            chroma * math.cos(math.radians(hue)),
            chroma * math.sin(math.radians(hue)),
        )

    target = lab(hex_colour)
    best = min(range(16, 256), key=lambda i: math.dist(lab(xterm256(i)), target))
    return f"ansi256({best})"


def mix(accent: str, base: str, share: float) -> str:
    a, b = (bytes.fromhex(c.lstrip("#")) for c in (accent, base))
    return "#" + "".join(
        f"{round(x * share + y * (1 - share)):02x}" for x, y in zip(a, b, strict=True)
    )


def ansi_name(key: str) -> str | None:
    if not key.startswith("palette"):
        return None
    slot = int(key.removeprefix("palette"))
    return f"ansi:{ANSI[slot % 8]}{'Bright' if slot >= 8 else ''}"


def build(theme: str, ansi: bool) -> dict:
    brand = BRAND[theme]
    colours = parse_ghostty(ROOT / "ghostty" / theme) | brand
    overrides = {}
    for token, key in ROLES.items():
        if key in ("claude", "claudeShimmer"):
            key = brand[key]
        value = colours.get(key, key)
        if ansi:
            value = ansi_name(key) or nearest256(value)
        overrides[token] = value
    for token, (accent, share) in TINTS.items():
        overrides[token] = (
            f"ansi256({ANSI_TINTS[token]})"
            if ansi
            else mix(colours[accent], colours["background"], share)
        )
    return {
        "$schema": SCHEMA,
        "name": f"{theme} (ANSI)" if ansi else theme,
        "base": "dark-ansi" if ansi else "dark",
        "overrides": overrides,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for theme in BRAND:
        for ansi in (False, True):
            path = OUT / f"{theme.lower()}{'-ansi' if ansi else ''}.json"
            path.write_text(json.dumps(build(theme, ansi), indent=2) + "\n")
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
