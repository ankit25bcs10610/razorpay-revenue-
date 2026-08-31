"""Generate docs/architecture-3d.svg — an isometric view of RevRecover.

Deterministic output: run `uv run python scripts/generate_architecture_svg.py`
after architecture changes and commit the regenerated SVG. Colors reuse the
dashboard's validated palette.
"""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

S = 34.0          # world unit -> px
COS, SIN = math.cos(math.radians(30)), 0.5
OX, OY = 370.0, 210.0

INK, INK2 = "#0b0b0b", "#52514e"
SURFACE = "#fcfcfb"
BLUE, ORANGE, AQUA, YELLOW, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7"
SLATE = "#8a887f"


def iso(x: float, y: float, z: float) -> tuple[float, float]:
    return (OX + (x - y) * COS * S, OY + (x + y) * SIN * S - z * S)


def poly(points, fill, opacity=1.0) -> str:
    path = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    return f'<polygon points="{path}" fill="{fill}" fill-opacity="{opacity}"/>'


def shade(hex_color: str, factor: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def box(x, y, z, w, d, h, color) -> str:
    top = [iso(x, y, z + h), iso(x + w, y, z + h), iso(x + w, y + d, z + h), iso(x, y + d, z + h)]
    front = [iso(x, y + d, z + h), iso(x + w, y + d, z + h), iso(x + w, y + d, z), iso(x, y + d, z)]
    right = [iso(x + w, y, z + h), iso(x + w, y + d, z + h), iso(x + w, y + d, z), iso(x + w, y, z)]
    return poly(top, color) + poly(front, shade(color, 0.82)) + poly(right, shade(color, 0.62))


def text_at(px, py, lines, *, size=13, color="#ffffff", weight=700, anchor="middle") -> str:
    spans = "".join(
        f'<tspan x="{px:.1f}" dy="{0 if i == 0 else size + 2}">{escape(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    return (
        f'<text x="{px:.1f}" y="{py:.1f}" font-size="{size}" fill="{color}" '
        f'font-weight="{weight}" text-anchor="{anchor}" '
        f'font-family="system-ui, -apple-system, sans-serif">{spans}</text>'
    )


def label(x, y, z, lines, **kw) -> str:
    px, py = iso(x, y, z)
    return text_at(px, py, lines, **kw)


def arrow(p_from, p_to, *, color=INK2, dash=None, width=2.2) -> str:
    (x1, y1), (x2, y2) = p_from, p_to
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{color}" stroke-width="{width}"{dash_attr} marker-end="url(#arrow)"/>'
    )


def slab(x, color, title, sub, *, w=2.6, d=1.5, h=1.0, y=0.6) -> str:
    parts = [box(x, y, 0.0, w, d, h, color)]
    parts.append(label(x + w / 2, y + d / 2 + 0.1, h + 0.06, [title], size=14))
    front_px, front_py = iso(x + w / 2 + 0.4, y + d, h * 0.62)
    parts.append(text_at(front_px, front_py, sub, size=9, weight=600))
    return "".join(parts)


def main() -> None:
    parts: list[str] = []

    # ---- base platforms ----
    parts.append(box(-1.8, -1.0, -2.05, 25.6, 4.8, 0.45, "#d8d6cf"))
    parts.append(box(-1.4, -0.8, -1.25, 24.8, 4.4, 0.5, SLATE))

    # ---- CUSTOMER-360 (back-left, drawn before the slabs) ----
    parts.append(box(-1.6, -4.2, 0.0, 4.6, 1.4, 0.7, "#b9b7ae"))
    parts.append(label(0.7, -3.5, 0.82, ["CUSTOMER-360"], size=12, color=INK))
    parts.append(label(0.9, -2.7, -0.5, ["cross-case caps · opt-outs · channel affinity"], size=9.5, color=INK2, weight=600))

    # ---- pipeline slabs ----
    parts.append(slab(0.0, BLUE, "INGEST", ["webhooks · poller", "event bus"]))
    parts.append(slab(3.6, BLUE, "DETECT", ["recoverability score", "EWMA degradation"]))
    parts.append(slab(7.2, VIOLET, "DIAGNOSE", ["evidence pack", "LLM + rule fallback"]))
    parts.append(slab(10.8, YELLOW, "DECIDE", ["EV ranking — rejected", "options audited"]))
    parts.append(slab(15.8, AQUA, "ACT", ["bounded playbooks", "idempotent actuators"]))
    parts.append(slab(19.4, AQUA, "MEASURE", ["₹ recovered", "stop reasons"]))

    # ---- compliance gate wall between DECIDE and ACT ----
    parts.append(box(14.35, 0.25, -0.15, 0.55, 2.5, 2.1, ORANGE))
    parts.append(label(14.62, 1.5, 2.85, ["COMPLIANCE GATE"], size=13, color=shade(ORANGE, 0.75)))
    parts.append(arrow(iso(14.62, 1.5, 2.62), iso(14.62, 1.4, 2.05), color=shade(ORANGE, 0.75), width=1.6))


    # ---- flow arrows along the slab tops ----
    flow_z = 0.55
    xs = [0.0, 3.6, 7.2, 10.8, 15.8, 19.4]
    for left, right in zip(xs, xs[1:], strict=False):
        parts.append(arrow(iso(left + 2.68, 1.35, flow_z), iso(right - 0.12, 1.35, flow_z), color=INK, width=2.4))

    # ---- LLM plane (floats above diagnosis) ----
    parts.append(box(4.8, -4.6, 2.7, 5.2, 1.4, 0.75, VIOLET))
    parts.append(label(7.4, -3.2, 2.82, ["CLAUDE (LLM)"], size=13))
    parts.append(arrow(iso(7.6, -2.9, 2.6), iso(8.5, 0.75, 1.15), color=VIOLET, dash="6 5"))
    apx, apy = iso(9.6, -2.4, 2.15)
    parts.append(text_at(apx, apy, ["diagnosis · message drafts · Hinglish voice", "schema-validated · falls back to rules", "never touches money"], size=10.5, color=VIOLET, anchor="start"))

    # ---- LEARN plane + feedback loop ----
    parts.append(box(18.8, -4.1, 2.7, 4.4, 1.4, 0.75, AQUA))
    parts.append(label(21.0, -3.4, 3.55, ["LEARN"], size=13.5))

    parts.append(arrow(iso(20.8, 0.55, 1.15), iso(21.0, -2.6, 2.65), color=AQUA, width=2.2))
    parts.append(arrow(iso(18.9, -3.2, 2.75), iso(12.6, 0.5, 1.2), color=AQUA, dash="6 5"))
    lnx, lny = iso(15.0, -2.7, 3.4)
    parts.append(text_at(lnx, lny, ["channel bandit per segment · holdout-gated", "re-ranks allowed options only —", "can never relax a rule"], size=10.5, color=shade(AQUA, 0.75), anchor="start"))

    # ---- audit drop lines from stages into the ledger ----
    for x in (1.3, 8.5, 12.1, 17.1, 20.7):
        parts.append(arrow(iso(x, 2.25, -0.05), iso(x, 3.0, -0.7), color="#6f6d66", dash="3 4", width=1.6))

    # ---- platform legend (fixed screen position, always legible) ----
    parts.append(
        f'<rect x="40" y="640" width="16" height="16" fill="{SLATE}" rx="3"/>'
        + text_at(64, 653, ["HASH-CHAINED AUDIT LEDGER — every stage appended; tampering breaks verify() at the exact record"], size=13, color=INK, weight=600, anchor="start")
    )
    parts.append(
        '<rect x="40" y="668" width="16" height="16" fill="#d8d6cf" rx="3"/>'
        + text_at(64, 681, ["SQLITE PERSISTENCE — the ledger and case snapshots survive restart"], size=13, color=INK, weight=600, anchor="start")
    )
    parts.append(
        f'<rect x="40" y="696" width="16" height="16" fill="{ORANGE}" rx="3"/>'
        + text_at(64, 709, ["COMPLIANCE GATE — quiet hours · contact caps · e-mandate rules · daily budget · HITL approval · kill switch"], size=13, color=INK, weight=600, anchor="start")
    )

    body = "\n".join(parts)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 730" role="img"
     aria-label="RevRecover isometric architecture: detect, diagnose, decide, act, measure, learn over a hash-chained audit ledger, with a compliance gate before action and the LLM confined to reasoning">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/>
    </marker>
  </defs>
  <rect width="1280" height="730" fill="{SURFACE}"/>
  <text x="640" y="42" text-anchor="middle" font-size="23" font-weight="800" fill="{INK}"
        font-family="system-ui, -apple-system, sans-serif">RevRecover — detect → diagnose → decide → act → measure → learn</text>
  <text x="640" y="68" text-anchor="middle" font-size="14" fill="{INK2}"
        font-family="system-ui, -apple-system, sans-serif">LLMs reason and communicate · deterministic code moves money · everything lands on the audit ledger</text>
{body}
</svg>
"""
    out = Path(__file__).parents[1] / "docs" / "architecture-3d.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
