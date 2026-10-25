# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check the themes against their design rules.

Ghostty: regular colours 1-6 clear 6:1 on the background, each bright twin
(9-14) is lighter than its regular colour, and the foreground, cursor and
selection pairs stay readable. Starship: each *_fg key clears 4.5:1 on the
rail it is drawn on. Claude Code: text stays readable on every tinted
surface, and accents and hints stay readable on the terminal background.

Run with `uv run scripts/check_contrast.py`; exits non-zero on any failure.
Output is coloured on a terminal; NO_COLOR turns that off, FORCE_COLOR on.
"""

import json
import math
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Which rail each Starship text colour sits on in a rail powerline prompt.
STARSHIP_PAIRS = {
    "os_fg": "rail0",
    "alert": "rail0",
    "dir_fg": "rail1",
    "git_fg": "rail2",
    "dur_fg": "rail2",
    "lang_fg": "rail3",
    "clock_fg": "rail3",
    "text": "base",
    "ok": "base",
    "vim": "base",
}

# Claude Code: (foreground token, surface token or None for the terminal
# background, minimum ratio, minimum for the 256-colour ANSI variants)
CLAUDE_PAIRS = [
    ("text", "userMessageBackground", 7),
    ("text", "bashMessageBackgroundColor", 7),
    ("text", "memoryBackgroundColor", 7),
    ("text", "diffAdded", 6),
    ("text", "diffRemoved", 6),
    ("text", "diffAddedDimmed", 7),
    ("text", "diffRemovedDimmed", 7),
    # the 256-colour cube has no green between #005f00 (line) and #008700
    # (word), so ANSI word highlights can only reach about 3.7:1
    ("text", "diffAddedWord", 4.5, 3.5),
    ("text", "diffRemovedWord", 4.5, 3.5),
    ("text", "selectionBg", 4.5),
    ("inverseText", "claude", 4.5),
    ("inactive", None, 4.5),
    ("subtle", None, 3),
    *(
        (token, None, 4.5)
        for token in (
            "claude",
            "permission",
            "suggestion",
            "success",
            "error",
            "warning",
            "planMode",
            "autoAccept",
            "remember",
        )
    ),
]
ANSI = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


def xterm256(index: int) -> str:
    """Default xterm colour for a 256-colour index (16-255)."""
    if index >= 232:
        v = 8 + 10 * (index - 232)
        return f"#{v:02x}{v:02x}{v:02x}"
    cube = [0, 95, 135, 175, 215, 255]
    index -= 16
    return "#" + "".join(f"{cube[(index // d) % 6]:02x}" for d in (36, 6, 1))


def channels(hex_colour: str) -> list[float]:
    h = hex_colour.lstrip("#")
    return [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]


def linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    r, g, b = map(linear, channels(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def oklab_lightness(hex_colour: str) -> float:
    r, g, b = map(linear, channels(hex_colour))
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (math.cbrt(v) for v in lms)
    return 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_


def parse_ghostty(path: Path) -> dict[str, str]:
    theme: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = (part.strip() for part in line.partition("="))
        if key == "palette":
            index, _, value = value.partition("=")
            key = f"palette{index.strip()}"
        theme[key] = value.strip()
    return theme


COLOUR = "FORCE_COLOR" in os.environ or (
    sys.stdout.isatty() and "NO_COLOR" not in os.environ
)


def paint(text: str, sgr: str) -> str:
    return f"\033[{sgr}m{text}\033[0m" if COLOUR else text


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, ok: bool, label: str, detail: str) -> None:
        self.failures += not ok
        status = paint("PASS", "1;32") if ok else paint("FAIL", "1;31")
        print(f"  {status}  {label:<34} {paint(detail, '2')}")


def check_ghostty(path: Path, report: Report) -> None:
    print(paint(str(path.relative_to(ROOT)), "1;34"))
    t = parse_ghostty(path)
    bg = t["background"]

    ratio = contrast(t["foreground"], bg)
    report.check(ratio >= 7, "foreground on background", f"{ratio:5.2f} >= 7")
    for i in range(1, 7):
        for slot in (i, i + 8):
            ratio = contrast(t[f"palette{slot}"], bg)
            report.check(
                ratio >= 6, f"palette {slot} on background", f"{ratio:5.2f} >= 6"
            )
        dark, bright = (oklab_lightness(t[f"palette{s}"]) for s in (i, i + 8))
        report.check(
            bright > dark,
            f"palette {i + 8} lighter than {i}",
            f"L {bright:.3f} > {dark:.3f}",
        )

    ratio = contrast(t["palette8"], bg)
    report.check(ratio >= 3, "palette 8 (dim text) on background", f"{ratio:5.2f} >= 3")
    ratio = contrast(t["cursor-text"], t["cursor-color"])
    report.check(ratio >= 4.5, "cursor text on cursor", f"{ratio:5.2f} >= 4.5")
    ratio = contrast(t["selection-foreground"], t["selection-background"])
    report.check(ratio >= 4.5, "selection text on selection", f"{ratio:5.2f} >= 4.5")


def check_starship(path: Path, report: Report) -> None:
    print(paint(str(path.relative_to(ROOT)), "1;34"))
    for name, palette in tomllib.loads(path.read_text())["palettes"].items():
        for fg, bg in STARSHIP_PAIRS.items():
            ratio = contrast(palette[fg], palette[bg])
            report.check(ratio >= 4.5, f"{name}.{fg} on {bg}", f"{ratio:5.2f} >= 4.5")


def check_claude(path: Path, report: Report) -> None:
    """Resolve ANSI slot names through the matching Ghostty theme and
    xterm-256 indices to their default colours, then check the token pairs
    Claude Code draws on top of each other."""
    print(paint(str(path.relative_to(ROOT)), "1;34"))
    theme = json.loads(path.read_text())
    ghostty = parse_ghostty(ROOT / "ghostty" / theme["name"].removesuffix(" (ANSI)"))

    def resolve(value: str) -> str:
        if value.startswith("ansi256("):
            return xterm256(int(value.removeprefix("ansi256(").rstrip(")")))
        if not value.startswith("ansi:"):
            return value
        name = value.removeprefix("ansi:")
        slot = ANSI.index(name.removesuffix("Bright")) + 8 * name.endswith("Bright")
        return ghostty[f"palette{slot}"]

    colours = {token: resolve(v) for token, v in theme["overrides"].items()}
    ansi = theme["base"].endswith("-ansi")
    for fg, bg, minimum, *ansi_minimum in CLAUDE_PAIRS:
        if ansi and ansi_minimum:
            minimum = ansi_minimum[0]
        surface = colours[bg] if bg else ghostty["background"]
        ratio = contrast(colours[fg], surface)
        report.check(
            ratio >= minimum,
            f"{fg} on {bg or 'terminal'}",
            f"{ratio:5.2f} >= {minimum}",
        )


def main() -> None:
    report = Report()
    for path in sorted((ROOT / "ghostty").iterdir()):
        check_ghostty(path, report)
    for path in sorted((ROOT / "starship").glob("*.toml")):
        check_starship(path, report)
    for path in sorted((ROOT / "claude-code").glob("*.json")):
        check_claude(path, report)
    if report.failures:
        print("\n" + paint(f"{report.failures} check(s) failed", "1;31"))
        sys.exit(1)
    print("\n" + paint("all checks passed", "1;32"))


if __name__ == "__main__":
    main()
