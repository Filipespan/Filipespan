"""Skyline das contribuicoes: o heat map do GitHub do ultimo ano em 3D isometrico.

Versao estatica do componente React ContributionSkyline, porque o README nao
roda JavaScript. Mesma camera (45 graus, 34 de elevacao), mesmos niveis pelo
percentil 95 e mesma altura das barras. Os predios sobem em onda da semana
mais antiga para a mais nova quando a imagem abre.

    pip install fonttools brotli
    python scripts/skyline.py

Token: GITHUB_TOKEN, GH_TOKEN ou o do `gh auth token`. Na Action roda todo dia.
"""

import json
import math
import os
import subprocess
import sys
import urllib.request
from datetime import date, timedelta
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import FAMILY, THEME, font_face, text_width  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "skyline.svg"
LOGIN = os.environ.get("SKYLINE_LOGIN", "Filipespan")

# github dark, do nivel 1 ao 4
LEVELS = ["#0e4429", "#006d32", "#26a641", "#39d353"]
ACCENT = LEVELS[3]

W = 1200
PAD = 36
YAW = math.pi / 4
ELEV = math.radians(34)
CS, SN = math.cos(YAW), math.sin(YAW)
SE, CE = math.sin(ELEV), math.cos(ELEV)
CELL = 0.9
OFF = (1 - CELL) / 2


# ---------------------------------------------------------------- dados

def token():
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    return subprocess.run(["gh", "auth", "token"], check=True, capture_output=True, text=True).stdout.strip()


def fetch():
    query = """query($login: String!) { user(login: $login) { contributionsCollection {
      contributionCalendar { weeks { contributionDays { date contributionCount } } } } } }"""
    body = json.dumps({"query": query, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", body,
        {"Authorization": f"bearer {token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        res = json.load(r)
    if "errors" in res:
        raise SystemExit(res["errors"])
    weeks = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]


def grid(days):
    """Colunas sao semanas (domingo no topo), terminando no ultimo dia recebido."""
    counts = dict(days)
    end = date.fromisoformat(max(counts))
    start = end - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    cells, d, i = [], start, 0
    while d <= end:
        cells.append({"date": d, "count": counts.get(d.isoformat(), 0), "week": i // 7, "day": i % 7})
        d += timedelta(days=1)
        i += 1
    nz = sorted(c["count"] for c in cells if c["count"] > 0)
    busy = nz[int(0.95 * (len(nz) - 1))] if nz else 0
    for c in cells:
        n = c["count"]
        c["level"] = 0 if n <= 0 else 4 if busy <= 0 else 1 + min(3, int(n / busy * 4))
    return cells, (nz[-1] if nz else 0)


def bar_height(count, top):
    return 0.4 + (count / top) ** 0.85 * 7.2 if count > 0 and top > 0 else 0.2


def stats(cells):
    total = sum(c["count"] for c in cells)
    busiest = max(cells, key=lambda c: c["count"])
    longest, run, run_start = (0, None, None), 0, None
    for c in cells:
        if c["count"] > 0:
            run_start = c["date"] if run == 0 else run_start
            run += 1
            if run > longest[0]:
                longest = (run, run_start, c["date"])
        else:
            run = 0
    j = len(cells) - 1
    if cells[j]["count"] == 0:  # hoje ainda nao acabou
        j -= 1
    end_at = j
    while j >= 0 and cells[j]["count"] > 0:
        j -= 1
    days = end_at - j
    current = (days, cells[j + 1]["date"], cells[end_at]["date"]) if days else (0, None, None)
    return total, busiest, longest, current


# ---------------------------------------------------------------- desenho

def project(x, y, z):
    return x * CS - y * SN, (x * SN + y * CS) * SE - z * CE


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def shade(rgb, k):
    return "#%02x%02x%02x" % tuple(round(v * k) for v in rgb)


def short(d):
    return d.strftime("%b ") + str(d.day)


def span(a, b, year=False):
    if not a:
        return "—"
    f = (lambda d: short(d) + d.strftime(", %Y")) if year else short
    return f"{f(a)} — {f(b)}"


def plural(n, one, many):
    return one if n == 1 else many


def stat(x, y, label, value, unit, sub, anchor):
    """Rotulo, numero grande com a unidade do lado e a linha de datas embaixo."""
    t = THEME
    big, small = 50, 16
    vw = text_width(value, big, 700, -1)
    uw = text_width(unit, small, 500)
    gap = 8
    if anchor == "end":
        vx, ux = x - uw - gap - vw, x - uw
    else:
        vx, ux = x, x + vw + gap
    a = 'text-anchor="end"' if anchor == "end" else ""
    return (
        f'<text x="{x}" y="{y}" font-size="14" fill="{t["muted"]}" {a}>{escape(label)}</text>'
        f'<text x="{vx:.1f}" y="{y + 50}" font-size="{big}" font-weight="700" letter-spacing="-1" fill="{ACCENT}">{escape(value)}</text>'
        f'<text x="{ux:.1f}" y="{y + 50}" font-size="{small}" font-weight="500" fill="{t["fg"]}">{escape(unit)}</text>'
        f'<text x="{x}" y="{y + 72}" font-size="13" fill="{t["faint"]}" {a}>{escape(sub)}</text>'
    )


def render(cells, top):
    t = THEME
    weeks = cells[-1]["week"] + 1
    bg, fg = hexrgb(t["bg"]), hexrgb(t["fg"])
    empty = tuple(b + (f - b) * 0.11 for b, f in zip(bg, fg))
    colours = [empty] + [hexrgb(c) for c in LEVELS]

    boxes = []
    for c in cells:
        x0, y0 = c["week"] + OFF, c["day"] + OFF
        x1, y1 = x0 + CELL, y0 + CELL
        z = bar_height(c["count"], top)
        boxes.append((c, x0, y0, x1, y1, z))

    # escala: cabe a cena inteira (e os meses na frente) na largura
    pts = [project(x, y, z) for _, x0, y0, x1, y1, z in boxes for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)) for z in (0, z)]
    pts += [project(0, 8.6, 0), project(weeks, 8.6, 0)]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    s = (W - PAD * 2) / (maxx - minx)
    H = round((maxy - miny) * s + PAD * 2)
    ox, oy = PAD - minx * s, PAD - miny * s

    def pt(x, y, z):
        px, py = project(x, y, z)
        return f"{ox + px * s:.1f},{oy + py * s:.1f}"

    def poly(corners, fill):
        return f'<polygon points="{" ".join(pt(*p) for p in corners)}" fill="{fill}"/>'

    parts = []
    for c, x0, y0, x1, y1, z in sorted(boxes, key=lambda b: (b[0]["week"] + 0.5) * SN + (b[0]["day"] + 0.5) * CS):
        rgb = colours[c["level"]]
        left = poly([(x0, y1, 0), (x1, y1, 0), (x1, y1, z), (x0, y1, z)], shade(rgb, 0.84))
        right = poly([(x1, y0, 0), (x1, y1, 0), (x1, y1, z), (x1, y0, z)], shade(rgb, 0.68))
        roof = poly([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], shade(rgb, 1))
        tip = f'{c["count"]} {plural(c["count"], "contribution", "contributions")} on {short(c["date"])}, {c["date"].year}'
        parts.append(f'<g class="w{c["week"]}"><title>{tip}</title>{left}{right}{roof}</g>')

    months, prev, edge = [], None, -1e9
    for w in range(weeks):
        d = cells[w * 7]["date"]
        if d.month != prev and w > 0:
            px, py = project(w + 0.5, 7.3, 0)
            x, y = ox + px * s, oy + py * s + 14
            label = d.strftime("%b")
            if x > edge and x + text_width(label, 12, 500) < W - PAD:
                months.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="12" font-weight="500" fill="{t["faint"]}">{label}</text>')
                edge = x + text_width(label, 12, 500) + 10
        prev = d.month
    return parts, months, H


def svg(days):
    cells, top = grid(days)
    total, busiest, longest, current = stats(cells)
    parts, months, H = render(cells, top)
    weeks = cells[-1]["week"] + 1
    t = THEME

    blocks = [
        ("1 year total", f"{total:,}", plural(total, "contribution", "contributions"),
         span(cells[0]["date"], cells[-1]["date"], True)),
        ("Busiest day", f"{busiest['count']:,}", plural(busiest["count"], "contribution", "contributions"),
         short(busiest["date"]) if busiest["count"] else "—"),
        ("Longest streak", f"{longest[0]:,}", plural(longest[0], "day", "days"), span(longest[1], longest[2])),
        ("Current streak", f"{current[0]:,}", plural(current[0], "day", "days"), span(current[1], current[2])),
    ]
    corner = (
        stat(W - PAD, PAD + 8, *blocks[0], "end") + stat(W - PAD, PAD + 118, *blocks[1], "end")
        + stat(PAD, H - PAD - 182, *blocks[2], "start") + stat(PAD, H - PAD - 72, *blocks[3], "start")
    )
    face = font_face("".join(b for blk in blocks for b in blk) + "0123456789JFMASONDanebrpyulgctov ,—")

    # a onda: semana mais antiga primeiro, ~1.4s ate a ultima
    waves = "".join(f".w{w}{{animation-delay:{w / max(1, weeks - 1) * 1.1:.2f}s}}" for w in range(weeks))
    title = f"{total:,} contributions in the last year on GitHub, drawn as an isometric skyline"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{escape(title)}</title>
<style>
{face}
text{{font-family:{FAMILY}}}
g{{animation:rise .7s cubic-bezier(.22,1,.36,1) both}}
.stats{{animation:fade .8s ease 1.4s both}}
@keyframes rise{{from{{opacity:0;transform:translateY(14px)}}}}
@keyframes fade{{from{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{g,.stats{{animation:none}}}}
{waves}
</style>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="16" fill="{t["bg"]}" stroke="{t["line"]}"/>
{"".join(parts)}
{"".join(months)}
<g class="stats">{corner}</g>
</svg>
"""


def main():
    days = fetch()
    OUT.write_text(svg(days), encoding="utf-8")
    print(f"{OUT.name}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
