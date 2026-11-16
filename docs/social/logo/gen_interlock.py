"""Interlaced HS monograms. The S comes from frontend/brand/logo.svg; the H is rebuilt in the same style
with lighter stems so the letters can weave. Crossings are real cut-outs (SVG masks), so the mark works
on any background colour."""
import pathlib, re

HERE = pathlib.Path(__file__).parent
FULL = re.search(r'd="([^"]+)"', (HERE / "../../../frontend/brand/logo.svg").read_text()).group(1)
H_ORIGINAL, S = FULL[:FULL.index("M300.12")].strip(), FULL[FULL.index("M300.12"):]
SCX, SCY = 269, 200  # centre of the S in the source file


def h_path(cx, cy, d, w, h, bar=8, serif=13):
    top, bot = cy - h / 2, cy + h / 2

    def stem(x):
        a, b = x - w / 2, x + w / 2
        return (f"M{b} {bot-6.4}L{b+serif} {bot-2.8}V{bot}H{a-serif}V{bot-2.8}L{a} {bot-6.4}"
                f"V{top+6.4}L{a-serif} {top+2.8}V{top}H{b+serif}V{top+2.8}L{b} {top+6.4}Z")
    return stem(cx - d / 2) + stem(cx + d / 2) + f"M{cx-d/2} {cy-bar/2}H{cx+d/2}V{cy+bar/2}H{cx-d/2}Z"


def rects(rs):
    return "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>' for x, y, w, h in rs)


def mark(name, h, s_at, k, s_over, h_over, rot=0, gap=5, ink="#111111", s_ink=None, bg="#ffffff", frame=""):
    """h: H path. s_at, k, rot: S centre, scale and clockwise rotation. s_over, h_over: rects where
    that letter runs on top."""
    sx, sy = s_at
    tf = f'transform="translate({sx} {sy}) rotate({rot}) scale({k}) translate({-SCX} {-SCY})"'
    w = 'x="0" y="0" width="400" height="400"'
    defs = f'''<clipPath id="so">{rects(s_over)}</clipPath><clipPath id="ho">{rects(h_over)}</clipPath>
<mask id="hm" maskUnits="userSpaceOnUse" {w}><rect width="400" height="400" fill="#fff"/><g clip-path="url(#so)"><path {tf} d="{S}" fill="#000" stroke="#000" stroke-width="{2*gap/k}" stroke-linejoin="round"/></g></mask>
<mask id="sm" maskUnits="userSpaceOnUse" {w}><rect width="400" height="400" fill="#fff"/><g clip-path="url(#ho)"><path d="{h}" fill="#000" stroke="#000" stroke-width="{2*gap}" stroke-linejoin="round"/></g></mask>'''
    body = (f'<g transform="{frame}"><g mask="url(#hm)"><path d="{h}" fill="{ink}"/></g>'
            f'<g mask="url(#sm)"><path {tf} d="{S}" fill="{s_ink or ink}"/></g></g>')
    back = f'<rect width="400" height="400" fill="{bg}"/>' if bg else ""
    (HERE / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">'
        f'<title>HealthSurface</title><defs>{defs}</defs>{back}{body}</svg>\n')


# Travelling down the S: over the right stem, under the crossbar, over the left stem.
# Zones are drawn per column so each tip of the S stays whole where it crosses a stem.
WEAVE = dict(s_over=[(260, 0, 140, 196), (200, 0, 60, 165), (0, 204, 140, 196), (140, 235, 60, 165)],
             h_over=[(0, 0, 140, 204), (140, 0, 60, 235), (200, 165, 60, 235), (260, 196, 140, 204)])
WIDE = dict(h=h_path(200, 200, 138, 22, 206), s_at=(200, 200), k=1.56, rot=21, **WEAVE)
CHAIN = dict(h=h_path(156, 200, 112, 20, 200), s_at=(240, 200), k=1.42, rot=8,
             s_over=[(0, 0, 400, 150), (0, 250, 400, 150)], h_over=[(0, 150, 400, 100)])

mark("logo-interlock-wide", **WIDE)
mark("logo-interlock-wide-teal", **WIDE, s_ink="#0b6e5f")
mark("logo-interlock-wide-dark", **WIDE, ink="#f4f4f1", bg="#0f1312")
mark("logo-interlock-wide-transparent", **WIDE, bg=None)
mark("logo-interlock-chain", **CHAIN)


# Original letters, untouched: the S just slides left and catches the H's right stem.
def slight(name, shift, s_on_top_at_top=True, split_y=200, **kw):
    top, bottom = [(0, 0, 400, split_y)], [(0, split_y, 400, 400 - split_y)]
    s_over, h_over = (top, bottom) if s_on_top_at_top else (bottom, top)
    mark(name, H_ORIGINAL, (SCX - shift, SCY), 1, s_over, h_over, gap=3.5,
         frame=f"translate({shift / 2} 0)", **kw)


slight("logo-hs-interlock", 24)
slight("logo-hs-interlock-dark", 24, ink="#f4f4f1", bg="#0f1312")
slight("logo-hs-interlock-transparent", 24, bg=None)
slight("logo-hs-interlock-alt", 32, s_on_top_at_top=False, split_y=214)
