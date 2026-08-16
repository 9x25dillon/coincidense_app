"""Terminal presentation.

Kept apart from `analysis` on purpose: the numbers must not know how they are going to
be displayed, and the display must not be able to change them.

The one presentational commitment worth stating is that a negative result gets the same
banner, the same colour weight, and the same amount of space as a positive one. "No
association" is a finding here, and a UI that renders it as a failure — grey, small,
apologetic — would undo in styling what the engine is for.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap

BLOCKS = " ▁▂▃▄▅▆▇█"

_CODES = {
    "bold": "1", "dim": "2", "italic": "3", "reverse": "7",
    "red": "31", "green": "32", "yellow": "33", "blue": "34",
    "magenta": "35", "cyan": "36", "grey": "90",
}


class Style:
    """ANSI styling that turns itself off when nobody is looking at a terminal."""

    def __init__(self, enabled: bool | None = None, stream=None):
        stream = stream or sys.stdout
        if enabled is None:
            enabled = (
                stream.isatty()
                and os.environ.get("NO_COLOR") is None
                and os.environ.get("TERM") != "dumb"
            )
        self.enabled = enabled

    def __call__(self, text: str, *names: str) -> str:
        if not self.enabled or not names:
            return text
        codes = ";".join(_CODES[n] for n in names if n in _CODES)
        return f"\033[{codes}m{text}\033[0m" if codes else text


def width(default: int = 80, cap: int = 100) -> int:
    return max(60, min(cap, shutil.get_terminal_size((default, 24)).columns))


def wrap(text: str, indent: str = "  ", cols: int | None = None) -> str:
    cols = cols or width()
    return textwrap.fill(
        text, width=cols - len(indent), initial_indent=indent, subsequent_indent=indent
    )


def rule(cols: int | None = None, char: str = "─", indent: str = "  ") -> str:
    cols = cols or width()
    return indent + char * (cols - len(indent) - 2)


def sparkline(counts: list[int]) -> str:
    """One row of block characters. Empty bins stay blank rather than showing the
    lowest block, so the shape of the distribution is not padded with mass that is
    not there."""
    peak = max(counts) if counts else 0
    if peak <= 0:
        return " " * len(counts)
    return "".join(
        BLOCKS[max(1, min(8, round(c / peak * 8)))] if c else " " for c in counts
    )


def histogram(values: list[float], observed: float, bins: int) -> tuple[list[int], float, float]:
    """Bin the null, with the range widened to include the observed value.

    The observed value is often outside the null entirely — that is what a strong
    result looks like — and a plot that clipped it there would hide the finding.
    """
    lo = min(min(values), observed)
    hi = max(max(values), observed)
    span = hi - lo
    if span <= 0:
        span = max(abs(hi), 1.0) * 1e-6
        lo, hi = lo - span, hi + span
    pad = (hi - lo) * 0.03
    lo, hi = lo - pad, hi + pad
    counts = [0] * bins
    for v in values:
        i = min(bins - 1, max(0, int((v - lo) / (hi - lo) * bins)))
        counts[i] += 1
    return counts, lo, hi


def null_plot(values: list[float], observed: float, style: Style,
              cols: int | None = None, indent: str = "  ", suffix: str = "") -> list[str]:
    """Where the observed statistic falls against the simulated null.

    "The null model is visible" is a design principle of this project, and until this
    existed the tool asserted the null rather than showing it. A reader can now see at
    a glance whether the observation sits inside the cloud of things chance produces or
    somewhere off the end of it — which is the actual question, and is much harder to
    misread than a p-value.

    Callers pass values already divided by the null mean, so the axis is in the same
    units as the headline effect ratio and 1.00 is the centre of chance. Plotting the
    raw statistic instead makes the reader convert between two scales to check whether
    the picture agrees with the number.
    """
    if not values:
        return []
    cols = cols or width()
    # One column per bin, so bin count and plot width cannot disagree. Narrow the plot
    # rather than scatter a few hundred simulations across a wide, gappy row.
    plot_w = max(24, min(cols - len(indent) - 2, len(values) // 8))
    counts, lo, hi = histogram(values, observed, plot_w)
    obs_col = min(plot_w - 1, max(0, int((observed - lo) / (hi - lo) * plot_w)))

    spark = sparkline(counts)
    inside = min(values) <= observed <= max(values)
    marker_colour = "cyan" if inside else "yellow"

    caret = [" "] * plot_w
    caret[obs_col] = "▲"
    label = f"observed {observed:.2f}{suffix}"
    start = obs_col - len(label) // 2
    start = max(0, min(plot_w - len(label), start))
    label_row = [" "] * max(plot_w, start + len(label))
    for k, ch in enumerate(label):
        label_row[start + k] = ch

    left, right = f"{lo:.2f}{suffix}", f"{hi:.2f}{suffix}"
    axis = left.ljust(plot_w - len(right)) + right

    return [
        indent + style(spark, "dim"),
        indent + style("".join(caret), marker_colour, "bold"),
        indent + style("".join(label_row), marker_colour),
        indent + style(axis, "grey"),
        indent + style(f"{len(values)} simulated nulls, "
                       f"{'observed falls inside them' if inside else 'observed falls outside them'}",
                       "grey"),
    ]


def bar(fraction: float, cells: int = 20) -> str:
    """A filled bar, used for the effect ratio against 1.0."""
    filled = max(0, min(cells, int(round(fraction * cells))))
    return "█" * filled + "░" * (cells - filled)


class Progress:
    """Single-line progress on stderr, and nothing at all when redirected.

    Monte Carlo is the slow step and a tool that prints nothing for thirty seconds
    reads as hung.
    """

    def __init__(self, label: str, enabled: bool | None = None):
        self.label = label
        self.enabled = sys.stderr.isatty() if enabled is None else enabled
        self._last = -1

    def __call__(self, done: int, total: int) -> None:
        if not self.enabled or total <= 0:
            return
        pct = int(done * 100 / total)
        if pct == self._last:
            return
        self._last = pct
        filled = pct * 24 // 100
        sys.stderr.write(
            f"\r  {self.label} {'█' * filled}{'░' * (24 - filled)} {pct:3d}%"
        )
        sys.stderr.flush()

    def done(self) -> None:
        if self.enabled and self._last >= 0:
            sys.stderr.write("\r" + " " * 60 + "\r")
            sys.stderr.flush()
