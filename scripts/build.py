"""Gera os cards dos projetos e os blocos de cards do README.

O banner animado sai de scripts/banner.py.

    pip install fonttools brotli
    python scripts/build.py

Projeto novo: acrescentar em data/projects.json, colocar o print em
assets/src/shots/<id>.webp (852x462) e rodar de novo.
"""

import base64
import io
import json
import re
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"
FONT = SRC / "fonts" / "PlusJakartaSans.ttf"
FAMILY = "'PJS', 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif"

THEME = {
    "bg": "#000000",
    "fg": "#ededed",
    "muted": "#a1a1aa",
    "faint": "#86868f",
    "line": "#27272a",
    "bar": "#0f0f11",
}


# ---------------------------------------------------------------- fontes

_metrics = {}


def text_width(text, size, weight, tracking=0.0):
    if weight not in _metrics:
        font = instancer.instantiateVariableFont(TTFont(FONT), {"wght": weight})
        _metrics[weight] = (font.getBestCmap(), font["hmtx"].metrics, font["head"].unitsPerEm)
    cmap, hmtx, upm = _metrics[weight]
    units = sum(hmtx[cmap.get(ord(ch), ".notdef")][0] for ch in text)
    return units * size / upm + tracking * len(text)


def wrap(text, size, weight, max_width):
    lines, current = [], ""
    for word in text.split():
        attempt = f"{current} {word}".strip()
        if current and text_width(attempt, size, weight) > max_width:
            lines.append(current)
            current = word
        else:
            current = attempt
    if current:
        lines.append(current)
    return lines


def font_face(text):
    """@font-face com a fonte variavel cortada so para os caracteres usados."""
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["kern", "liga", "calt"]
    options.name_IDs = []
    font = TTFont(FONT)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text="".join(sorted(set(text + " "))))
    subsetter.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return (
        "@font-face{font-family:'PJS';font-weight:200 800;"
        f"src:url(data:font/woff2;base64,{data}) format('woff2')}}"
    )


def data_uri(path):
    return "data:image/webp;base64," + base64.b64encode(path.read_bytes()).decode()


# ---------------------------------------------------------------- cards

CARD_W = 600
PAD = 12
SHOT_W = CARD_W - PAD * 2
SHOT_H = round(SHOT_W * 462 / 852)
BAR_H = 30
DESC_SIZE = 15
DESC_LEAD = 22
TEXT_X = 28
TEXT_W = CARD_W - TEXT_X * 2


def card_height(desc_lines):
    # nome + descricao + linha das tags + respiro embaixo
    return PAD + BAR_H + SHOT_H + 46 + 30 + (desc_lines - 1) * DESC_LEAD + 34 + 30


def card(project, desc_lines):
    t = THEME
    shown = project.get("shown") or project["url"].removeprefix("https://")
    lines = wrap(project["description"], DESC_SIZE, 400, TEXT_W)
    height = card_height(desc_lines)
    tags = project["tags"]

    all_text = project["name"] + shown + project["description"] + "".join(tags)
    face = font_face(all_text)

    shot = data_uri(SRC / "shots" / f"{project['id']}.webp")
    frame_h = BAR_H + SHOT_H
    y_name = PAD + frame_h + 46
    y_desc = y_name + 30
    y_tags = height - 30  # tags sempre no rodape, mesmo com menos linhas de texto

    desc = "".join(
        f'<tspan x="{TEXT_X}" dy="{0 if i == 0 else DESC_LEAD}">{escape(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    tag_parts, x = [], TEXT_X
    for tag in tags:
        tag_parts.append(f'<text x="{x:.1f}" y="{y_tags}" font-size="13" font-weight="500" fill="{t["faint"]}">{escape(tag)}</text>')
        x += text_width(tag, 13, 500) + 20

    url_w = text_width(shown, 12.5, 500)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CARD_W} {height}" width="{CARD_W}" height="{height}" role="img" aria-labelledby="t">
<title id="t">{escape(project["name"])}: {escape(project["description"])}</title>
<style>
{face}
text{{font-family:{FAMILY}}}
</style>
<defs><clipPath id="frame"><rect x="{PAD}" y="{PAD}" width="{SHOT_W}" height="{frame_h}" rx="10"/></clipPath></defs>
<rect x=".5" y=".5" width="{CARD_W - 1}" height="{height - 1}" rx="16" fill="{t["bg"]}" stroke="{t["line"]}"/>
<g clip-path="url(#frame)">
<rect x="{PAD}" y="{PAD}" width="{SHOT_W}" height="{frame_h}" fill="{t["bar"]}"/>
<image href="{shot}" x="{PAD}" y="{PAD + BAR_H}" width="{SHOT_W}" height="{SHOT_H}" preserveAspectRatio="xMidYMin slice"/>
</g>
<rect x="{PAD + .5}" y="{PAD + .5}" width="{SHOT_W - 1}" height="{frame_h - 1}" rx="9.5" fill="none" stroke="{t["line"]}"/>
<text x="{CARD_W / 2 - url_w / 2:.1f}" y="{PAD + 20}" font-size="12.5" font-weight="500" fill="{t["faint"]}">{escape(shown)}</text>
<text x="{TEXT_X}" y="{y_name}" font-size="22" font-weight="700" letter-spacing="-.4" fill="{t["fg"]}">{escape(project["name"])}</text>
<text y="{y_desc}" font-size="{DESC_SIZE}" font-weight="400" fill="{t["muted"]}">{desc}</text>
{"".join(tag_parts)}
</svg>
"""


# ---------------------------------------------------------------- README

def picture(project, folder="assets/cards"):
    alt = escape(f'{project["name"]}: {project["description"]}', quote=True)
    return f'<a href="{project["url"]}"><img src="{folder}/{project["id"]}.svg" width="49%" alt="{alt}"></a>'


def update_readme(groups):
    path = ROOT / "README.md"
    readme = path.read_text(encoding="utf-8")
    for key, projects in groups.items():
        block = "\n".join(picture(p) for p in projects)
        pattern = re.compile(rf"(<!-- cards:{key} -->).*?(<!-- /cards:{key} -->)", re.S)
        if not pattern.search(readme):
            raise SystemExit(f"README.md sem os marcadores <!-- cards:{key} -->")
        readme = pattern.sub(lambda m: f"{m.group(1)}\n{block}\n{m.group(2)}", readme)
    path.write_text(readme, encoding="utf-8")


def main():
    data = json.loads((ROOT / "data" / "projects.json").read_text(encoding="utf-8"))
    every = data["client"] + data["oss"]

    # Todos os cards com a mesma altura, para as linhas do grid alinharem.
    desc_lines = max(len(wrap(p["description"], DESC_SIZE, 400, TEXT_W)) for p in every)
    cards = ROOT / "assets" / "cards"
    cards.mkdir(exist_ok=True)
    for project in every:
        out = cards / f"{project['id']}.svg"
        out.write_text(card(project, desc_lines), encoding="utf-8")
        print(f"cards/{project['id']}: {out.stat().st_size // 1024} KB")

    update_readme(data)


if __name__ == "__main__":
    main()
