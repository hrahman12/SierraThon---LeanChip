#!/usr/bin/env python3
"""Compose assets/leanchip_banner.svg (LeanKeel theme): 2D design -> Lean -> 3D board.

Every picture in it is real: the schematic and stack-up crops come from the official
Sierrathon files, and the 3D board is a render of leanvsdfm/out3d/sierrathon.step, which
KiCad exported from our placed board with KiCad's 3D part models.
    python3 assets/make_banner.py        (then render the SVG to PNG)
"""
import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MONO = "'JetBrains Mono',Consolas,'Courier New',monospace"
SANS = "'Space Grotesk','Segoe UI',Arial,sans-serif"


def b64(name):
    return "data:image/png;base64," + base64.b64encode(open(os.path.join(HERE, "src", name), "rb").read()).decode()


DRIFT = [  # (x, y, size, colour, opacity, rotate, text): real theorem names from leanvsdfm/
    (40, 372, 17, "#B9A7FF", 0.42, -2, "theorem bodies_never_collide : fitOk ps → Pairwise bodySep ps"),
    (40, 446, 14, "#2DD4BF", 0.32, 0, "our_board_electrically_clean"),
    (330, 446, 14, "#F5A524", 0.30, 0, "body ⊆ courtyard · body ⊆ outline"),
    (40, 508, 15, "#B9A7FF", 0.32, 0, "⊢ fit3d board = []"),
    (250, 510, 13, "#2DD4BF", 0.29, 0, "catches_reversed_led"),
    (470, 504, 13, "#F5A524", 0.29, 0, "stack-up 59.496 mil ∈ 62 ± 10 %"),
    (800, 508, 13, "#B9A7FF", 0.27, 0, "overall_is_worst"),
    (980, 500, 13, "#2DD4BF", 0.29, 0, "break1_only_row5"),
    (1160, 512, 12, "#B9A7FF", 0.25, 0, "by decide +kernel"),
    (1380, 506, 13, "#F5A524", 0.30, 0, "54 parts · 0 collisions"),
]


def main():
    drift = "\n".join(
        f'    <text x="{x}" y="{y}" font-size="{s}" fill="{c}" fill-opacity="{o}"'
        + (f' transform="rotate({r} {x} {y})"' if r else "") + f">{t}</text>" for x, y, s, c, o, r, t in DRIFT)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1600 520" width="1600" height="520" role="img" aria-label="LeanChip: 2D to 3D, verified in Lean. On the left the real Sierrathon schematic and stack-up as flat pages; in the middle the Lean turnstile; on the right a 3D render of the board that KiCad exported from them, standing on a glowing turnstile.">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#060B18"/><stop offset="1" stop-color="#0B1A33"/></linearGradient>
    <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0D2440" stop-opacity="0"/><stop offset="1" stop-color="#060B18"/></linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#B9A7FF" stop-opacity="0.55"/><stop offset="1" stop-color="#B9A7FF" stop-opacity="0"/></radialGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#000" flood-opacity="0.55"/></filter>
    <clipPath id="cardA"><rect x="0" y="0" width="212" height="212" rx="10"/></clipPath>
    <clipPath id="cardB"><rect x="0" y="0" width="230" height="76" rx="8"/></clipPath>
    <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#B9A7FF"/></marker>
  </defs>
  <rect width="1600" height="520" fill="url(#sky)"/>
  <g fill="none" stroke="#B9A7FF" stroke-opacity="0.07" stroke-width="1.5">
    <path d="M0 90 C 300 60 600 120 900 80 S 1400 50 1600 90"/><path d="M0 150 C 300 120 600 180 900 140 S 1400 110 1600 150"/>
  </g>
  <g fill="#F3EFE6" opacity="0.5"><circle cx="1020" cy="40" r="1.4"/><circle cx="1560" cy="60" r="1.2"/><circle cx="930" cy="96" r="1"/><circle cx="1500" cy="30" r="1"/><circle cx="700" cy="40" r="1"/></g>
  <rect y="352" width="1600" height="168" fill="url(#floor)"/>

  <!-- faint theorem names drifting below -->
  <g font-family="{MONO}">
{drift}
  </g>

  <!-- ===== 2D: the real design pages (official Sierrathon stack-up and schematic) ===== -->
  <g filter="url(#shadow)">
    <g transform="translate(664 262) rotate(-6)"><g clip-path="url(#cardB)"><rect width="230" height="76" fill="#fff"/><image href="{b64('stackup_crop.png')}" x="0" y="0" width="230" height="76" preserveAspectRatio="xMidYMid slice"/></g></g>
    <g transform="translate(716 44) rotate(3)"><g clip-path="url(#cardA)"><rect width="212" height="212" fill="#fff"/><image href="{b64('schematic_crop_u1.png')}" x="0" y="0" width="212" height="212"/></g>
      <rect x="0" y="0" width="212" height="212" rx="10" fill="none" stroke="#2DD4BF" stroke-opacity="0.8" stroke-width="2"/></g>
  </g>
  <text x="822" y="372" text-anchor="middle" font-family="{SANS}" font-size="22" font-weight="700" fill="#2DD4BF">2D design</text>
  <text x="822" y="394" text-anchor="middle" font-family="{MONO}" font-size="12" fill="#C9D3DC" fill-opacity="0.8">schematic · BOM · stack-up</text>

  <!-- ===== Lean in the middle ===== -->
  <path d="M944 196 L 1012 196" stroke="#B9A7FF" stroke-width="4" fill="none" marker-end="url(#arr)"/>
  <circle cx="978" cy="150" r="30" fill="#0B1A33" stroke="#B9A7FF" stroke-width="2.5"/>
  <path d="M968 134 L 968 166 M968 150 L 992 150" stroke="#B9A7FF" stroke-width="6" stroke-linecap="round"/>
  <text x="978" y="236" text-anchor="middle" font-family="{SANS}" font-size="18" font-weight="700" fill="#B9A7FF">Lean</text>
  <text x="978" y="256" text-anchor="middle" font-family="{MONO}" font-size="11" fill="#C9D3DC" fill-opacity="0.8">proves it</text>

  <!-- ===== 3D: render of the STEP that KiCad exported from our board ===== -->
  <ellipse cx="1300" cy="418" rx="270" ry="44" fill="url(#glow)"/>
  <path d="M1090 404 L 1510 404" stroke="#B9A7FF" stroke-width="7" stroke-linecap="round"/>
  <path d="M1300 404 L 1300 462" stroke="#B9A7FF" stroke-width="7" stroke-linecap="round"/>
  <image href="{b64('board3d_render.png')}" x="1040" y="30" width="530" height="{530 * 768 // 1100}"/>
  <text x="1582" y="440" text-anchor="end" font-family="{SANS}" font-size="22" font-weight="700" fill="#FF8A80">3D board</text>
  <text x="1582" y="462" text-anchor="end" font-family="{MONO}" font-size="12" fill="#C9D3DC" fill-opacity="0.8">KiCad STEP · real part models</text>

  <!-- ===== wordmark ===== -->
  <text x="88" y="250" font-family="{SANS}" font-size="128" font-weight="700" fill="#F3EFE6" letter-spacing="-2">Lean<tspan fill="#B9A7FF">Chip</tspan></text>
  <text x="92" y="312" font-family="{MONO}" font-size="30" fill="#B9A7FF">⊢ 2D → 3D, verified in Lean</text>
  <text x="92" y="478" font-family="{SANS}" font-size="25" fill="#F3EFE6" fill-opacity="0.85">Sierrathon 2026 · does the 2D design really become the 3D board?</text>
</svg>
'''
    open(os.path.join(HERE, "leanchip_banner.svg"), "w").write(svg)
    print("wrote leanchip_banner.svg", len(svg) // 1024, "KiB")


if __name__ == "__main__":
    main()
