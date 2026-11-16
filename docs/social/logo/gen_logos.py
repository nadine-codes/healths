"""Writes the wavy HealthSurface logo concepts as SVG. Letterforms come from frontend/brand/logo.svg."""
import math, pathlib, re

HERE = pathlib.Path(__file__).parent
HS = re.search(r'd="([^"]+)"', (HERE / "../../../frontend/brand/logo.svg").read_text()).group(1)
BG, TEXT = "#0f1312", "#f4f4f1"
REG, PEER, PRE, PRESS, TEAL = "#6f9bff", "#4fc98a", "#c77bdc", "#f0a63c", "#2fb8a0"


def gauss(x, c, s):
    return math.exp(-((x - c) / s) ** 2 / 2)


def line(fn, x0=-10, x1=410, step=4):
    pts = [(x, fn(x)) for x in range(x0, x1 + 1, step)]
    return "M" + " L".join(f"{x} {y:.1f}" for x, y in pts)


def svg(body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">'
            f'<title>HealthSurface</title><defs>{defs}</defs>'
            f'<rect width="400" height="400" fill="{BG}"/>{body}</svg>\n')


def concept_a():
    """Letters in the source-type colours, with wave lines cut through them."""
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in
                    [(0, REG), (.36, TEAL), (.62, PEER), (1, PRESS)])
    defs = (f'<linearGradient id="g" gradientUnits="userSpaceOnUse" x1="88" y1="0" x2="312" y2="0">{stops}</linearGradient>'
            f'<clipPath id="c"><path d="{HS}"/></clipPath>')
    cuts = ""
    for y0 in range(150, 280, 30):
        fn = lambda x, y0=y0: y0 + 7 * math.sin(x / 26 + 1) - 10 * gauss(x, 200, 50)
        cuts += f'<path d="{line(fn)}" fill="none" stroke="{BG}" stroke-width="6"/>'
    return svg(f'<g transform="translate(200 200) scale(1.32) translate(-200 -200)">'
               f'<path d="{HS}" fill="url(#g)"/><g clip-path="url(#c)">{cuts}</g></g>', defs)


def concept_b():
    """Solid letters rising out of the ridgelines, which hide their feet."""
    rows = [(268, REG, 34), (298, PEER, 38), (328, PRE, 42), (358, PRESS, 46)]
    waves = ""
    for y0, col, a in rows:
        fn = lambda x, y0=y0, a=a: y0 - a * gauss(x, 122, 46) - a * .8 * gauss(x, 280, 50)
        waves += f'<path d="{line(fn)} L410 420 L-10 420 Z" fill="{BG}" stroke="{col}" stroke-width="12" stroke-linejoin="round"/>'
    return svg(f'<g transform="translate(-30 -74) scale(1.15)"><path d="{HS}" fill="{TEXT}"/></g>{waves}')


def concept_c():
    """No letters: nested ridgelines rising to one peak, one colour per line."""
    rows = [(176, REG, 92), (208, PEER, 80), (240, PRE, 66), (272, PRESS, 50), (304, TEXT, 32)]
    body = ""
    for y0, col, a in rows:
        fn = lambda x, y0=y0, a=a: y0 - a * gauss(x, 200, 46) + 7 * math.sin(x / 42 + 1)
        body += f'<path d="{line(fn, 56, 344)}" fill="none" stroke="{col}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>'
    return svg(body)


for name, fn in [("logo-a-cut", concept_a), ("logo-b-surfacing", concept_b), ("logo-c-peak", concept_c)]:
    (HERE / f"{name}.svg").write_text(fn())
