"""Logo concepts D-H: same ridge method as the banners (stacked thin lines, nearer rows hide farther
ones, colour glowing only at the peaks). No dependencies. Letterforms come from frontend/brand/logo.svg."""
import math, pathlib, re

HERE = pathlib.Path(__file__).parent
HS = re.search(r'd="([^"]+)"', (HERE / "../../../frontend/brand/logo.svg").read_text()).group(1)
BG, TEXT = "#0f1312", "#f4f4f1"
REG, PEER, PRE, PRESS, NEWS = (111,155,255), (79,201,138), (199,123,220), (240,166,60), (190,194,192)
TEAL, WHITE = (47,184,160), (244,244,241)


def gauss(d, s):
    return math.exp(-(d / s) ** 2 / 2)


def mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def svg(body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">'
            f'<title>HealthSurface</title><defs>{defs}</defs><rect width="400" height="400" fill="{BG}"/>{body}</svg>\n')


def draw_row(pts, style, sw, fill=BG):
    """pts: (x, y). style(x) -> (rgb, alpha). Fills below the line to hide farther rows, then strokes
    it in runs of matching colour so the file stays small."""
    path = " L".join(f"{x} {y:.1f}" for x, y in pts)
    out = f'<path d="M{pts[0][0]} 430 L{path} L{pts[-1][0]} 430 Z" fill="{fill}"/>'
    run, key = [pts[0]], None

    def flush():
        nonlocal out
        if key and len(run) > 1:
            d = " L".join(f"{x} {y:.1f}" for x, y in run)
            r, g, b, a = key
            out += f'<path d="M{d}" fill="none" stroke="rgb({r},{g},{b})" stroke-opacity="{a}" stroke-width="{sw}" stroke-linejoin="round"/>'

    for p in pts[1:]:
        rgb, a = style(p[0])
        k = tuple(int(c // 20 * 20) for c in rgb) + (round(min(1, a) * 10) / 10,)
        if k != key:
            flush()
            run, key = [run[-1]], k
        run.append(p)
    flush()
    return out


def field(peaks, sig, sv=.11):
    def f(u, v):
        h = .03 * math.sin(u * 8 + v * 7) + .025 * math.sin(u * 17 - v * 13) + .05
        w, col = 0, [0, 0, 0]
        for rgb, pu, pv, a in peaks:
            g = gauss(u - pu, sig) * gauss(v - pv, sv)
            h += a * g
            w += g
            for i in range(3):
                col[i] += rgb[i] * g
        m = min(1, w * 1.5)
        rgb = mix(TEAL, [c / w for c in col], m) if w > 0 else TEAL
        return max(0, h), rgb, m
    return f


def ridges(peaks, rows, horizon, bottom, amp, sw, sig=.11, fill=BG, base=.2, sv=.11):
    f, out = field(peaks, sig, sv), ""
    for r in range(rows + 1):
        v = r / rows
        y0 = horizon + (bottom - horizon) * v ** 1.35
        sc = .5 + .5 * v
        pts = [(x, y0 - f(x / 400, v)[0] * amp * sc) for x in range(-8, 409, 4)]

        def style(x, v=v):
            _, rgb, m = f(x / 400, v)
            return rgb, base + .3 * v + m * .6
        out += draw_row(pts, style, sw, fill)
    return out


# ---- HS as a height map ----
def letter_mask(scale, blur):
    """Rasterises the HS path (each subpath filled, then merged) and blurs it. Returns mask[y][x]."""
    toks = re.findall(r"[A-Za-z]|-?\d*\.?\d+", HS)
    assert set(t for t in toks if t.isalpha()) <= set("MLHVQZ"), "unexpected path command"
    subs, cur, i, cmd, x, y = [], [], 0, None, 0, 0
    num = lambda k: float(toks[k])
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]; i += 1
            if cmd == "Z":
                subs.append(cur); cur = []
                continue
        if cmd in "ML":
            x, y = num(i), num(i + 1); i += 2
            cur.append((x, y))
            cmd = "L"
        elif cmd == "H":
            x = num(i); i += 1; cur.append((x, y))
        elif cmd == "V":
            y = num(i); i += 1; cur.append((x, y))
        elif cmd == "Q":
            cx, cy, ex, ey = (num(i + k) for k in range(4)); i += 4
            for t in (.25, .5, .75, 1):
                cur.append(((1-t)**2*x + 2*(1-t)*t*cx + t*t*ex, (1-t)**2*y + 2*(1-t)*t*cy + t*t*ey))
            x, y = ex, ey
    N = 400
    m = [[0.0] * N for _ in range(N)]
    tf = lambda p: ((p[0] - 200) * scale + 200, (p[1] - 200) * scale + 200)
    for poly in subs:
        poly = [tf(p) for p in poly]
        for row in range(N):
            yy = row + .5
            xs = sorted(a[0] + (yy - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
                        for a, b in zip(poly, poly[1:] + poly[:1]) if (a[1] <= yy) != (b[1] <= yy))
            for s, e in zip(xs[::2], xs[1::2]):
                for c in range(max(0, int(s)), min(N, int(e) + 1)):
                    m[row][c] = 1.0

    def box(a):
        out = []
        for row in a:
            acc, res = 0.0, [0.0] * N
            pre = [0.0]
            for val in row:
                acc += val; pre.append(acc)
            for c in range(N):
                lo, hi = max(0, c - blur), min(N, c + blur + 1)
                res[c] = (pre[hi] - pre[lo]) / (hi - lo)
            out.append(res)
        return out
    t = lambda a: [list(c) for c in zip(*a)]
    return t(box(t(box(m))))


def raised(rows, y_top, y_bot, lift, sw, colour, scale=1.3, blur=2):
    mask, out = letter_mask(scale, blur), ""
    for r in range(rows + 1):
        y0 = y_top + (y_bot - y_top) * r / rows
        src = min(399, max(0, int(y0 - lift * .5)))
        wave = lambda x: 3.5 * math.sin(x / 38 + r * .35) + 2.5 * math.sin(x / 17 - r * .2)
        pts = [(x, y0 + wave(x) - lift * mask[src][min(399, max(0, x))]) for x in range(-8, 409, 2)]

        def style(x, src=src):
            k = mask[src][min(399, max(0, x))]
            return mix(TEAL, colour(x), k), .3 + .7 * k
        out += draw_row(pts, style, sw)
    return out


def spectrum(x):
    """Across the letters: blue, green, purple, amber, like the banner's peaks left to right."""
    stops = [(70, REG), (175, PEER), (240, PRE), (330, PRESS)]
    if x <= stops[0][0]:
        return stops[0][1]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if x <= b:
            return mix(ca, cb, (x - a) / (b - a))
    return stops[-1][1]


FIVE = [(REG, .30, .30, 1.0), (PEER, .70, .20, 1.1), (PRE, .50, .58, .85), (PRESS, .78, .70, .8), (NEWS, .24, .84, .55)]

concepts = {
    "logo-d-field": lambda: svg(ridges(FIVE, 22, 150, 420, 165, 2.2)),
    "logo-e-raised-colour": lambda: svg(raised(60, 22, 400, 13, 1.9, spectrum)),
    "logo-f-raised-white": lambda: svg(raised(40, 22, 400, 15, 3, lambda x: WHITE, blur=3)),
    "logo-g-surfacing-fine": lambda: svg(
        f'<g transform="translate(-30 -74) scale(1.15)"><path d="{HS}" fill="{TEXT}"/></g>'
        + ridges([(REG, .31, .28, .9), (PRESS, .70, .34, .85), (PEER, .5, .7, .55)], 15, 232, 420, 120, 2.4, base=.3)),
    "logo-h-field-bold": lambda: svg(ridges(
        [(REG, .30, .34, 1.05), (PEER, .68, .24, 1.2), (PRESS, .62, .78, .8)], 11, 150, 420, 175, 5.5, sig=.13, sv=.15, base=.45)),
}
for name, make in concepts.items():
    (HERE / f"{name}.svg").write_text(make())
