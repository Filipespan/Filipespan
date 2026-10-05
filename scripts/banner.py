"""Banner animado do README: esfera iridescente em loop com o texto.

Video: "Vibrant iridescent fluid art sphere", de Rafael Minguet Delgado,
https://www.pexels.com/video/36345264/ (licenca Pexels, uso livre).

O trecho escolhido ganha um crossfade entre o fim e o comeco, entao o loop
nao tem corte. Os quadros vao direto para o ffmpeg, sem arquivo temporario.

    pip install numpy pillow imageio-ffmpeg
    python scripts/banner.py
"""

import subprocess
import urllib.request
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "src" / "fonts" / "PlusJakartaSans.ttf"
OUT = ROOT / "assets" / "banner.avif"

SOURCE = "https://videos.pexels.com/video-files/36345264/15415744_1280_720_25fps.mp4"
CACHE = Path.home() / ".cache" / "filipespan-banner" / "sphere.mp4"

SCALE = 1.5                       # banner de 1200x300 desenhado a 1.5x
W, H = int(1200 * SCALE), int(300 * SCALE)
FPS = 25
START, LOOP, FADE = 1.0, 10.0, 2.0  # segundos
CRF = 50

BOX_W = int(W * 0.56)             # o video ocupa os 56% da direita
BOX_X = W - BOX_W
FADE_W = 0.35                     # parte do box que some no preto, da esquerda

TEXT = {
    "name": "Filipe Spanghero",
    "role": "Front-end developer",
    "line": "Fast sites and web apps with Next.js, React and TypeScript.",
}
FG, MUTED, FAINT = (237, 237, 237), (161, 161, 170), (134, 134, 143)

FF = imageio_ffmpeg.get_ffmpeg_exe()


def source():
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(SOURCE, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(CACHE, "wb") as f:
            f.write(r.read())
    return CACHE


def clip():
    """Trecho do video ja escalado para cobrir o box e cortado no topo da esfera."""
    scaled_h = round(720 * BOX_W / 1280 / 2) * 2
    cmd = [
        FF, "-loglevel", "error", "-ss", str(START), "-t", str(LOOP + FADE), "-i", str(source()),
        "-vf", f"fps={FPS},scale={BOX_W}:{scaled_h}:flags=lanczos,crop={BOX_W}:{H}:0:0",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, H, BOX_W, 3)
    need = int((LOOP + FADE) * FPS)
    if len(frames) < need:
        raise SystemExit(f"trecho curto: {len(frames)} de {need} quadros")
    return frames[:need]


def looped(frames):
    """Os primeiros FADE segundos misturam o fim do trecho com o comeco."""
    n, f = int(LOOP * FPS), int(FADE * FPS)
    for i in range(n):
        if i >= f:
            yield frames[i].astype(np.float32)
        else:
            w = (i / f) ** 2 * (3 - 2 * i / f)  # smoothstep
            yield frames[n + i].astype(np.float32) * (1 - w) + frames[i].astype(np.float32) * w


def font(size, weight):
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_axes([weight])
    return f


def overlay():
    """Texto e cantos arredondados, iguais em todos os quadros."""
    s = SCALE
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(text)
    name, size = TEXT["name"], round(66 * s)
    big = font(size, 700)
    for i, ch in enumerate(name):  # letter-spacing mantendo o kerning
        x = 69 * s + big.getlength(name[:i]) - 2.3 * s * i
        d.text((x, 142 * s), ch, font=big, fill=FG, anchor="ls")
    d.text((72 * s, 186 * s), TEXT["role"], font=font(round(24 * s), 500), fill=MUTED, anchor="ls")
    d.text((72 * s, 230 * s), TEXT["line"], font=font(round(17 * s), 400), fill=FAINT, anchor="ls")

    corners = Image.new("L", (W * 2, H * 2), 0)
    ImageDraw.Draw(corners).rounded_rectangle((0, 0, W * 2 - 1, H * 2 - 1), radius=int(32 * s), fill=255)
    corners = corners.resize((W, H), Image.LANCZOS)

    t = np.asarray(text, np.float32) / 255
    return t[..., :3] * 255, t[..., 3:], np.asarray(corners, np.uint8)


def main():
    frames = clip()
    text_rgb, text_a, alpha = overlay()
    ramp = np.clip(np.arange(BOX_W) / (BOX_W * FADE_W), 0, 1)
    ramp = (ramp * ramp * (3 - 2 * ramp))[None, :, None].astype(np.float32)

    cmd = [
        FF, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-filter_complex", "[0:v]split[c][a];[c]format=yuv420p[c];[a]alphaextract,format=gray[a]",
        "-map", "[c]", "-map", "[a]",
        "-c:v", "libaom-av1", "-crf", str(CRF), "-cpu-used", "4", "-row-mt", "1",
        "-g", str(int(LOOP * FPS)),
        # alpha em faixa cheia; em faixa limitada 255 vira ~235 e o banner fica translucido
        "-color_range:v:1", "pc",
        "-f", "avif", "-loop", "0", str(OUT),
    ]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    canvas = np.zeros((H, W, 3), np.float32)
    for i, frame in enumerate(looped(frames)):
        canvas[:] = 0
        canvas[:, BOX_X:] = frame * ramp
        rgb = canvas * (1 - text_a) + text_rgb * text_a
        rgba = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), alpha])
        enc.stdin.write(rgba.tobytes())
        print(f"\r{i + 1}/{int(LOOP * FPS)}", end="", flush=True)
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg falhou")
    print(f"\n{OUT.name}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
