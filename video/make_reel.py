"""L'Artisan KANOYA — Instagram Reel (1080x1920, 30s)
ある日のディナーより「オーラキングサーモン、グリビッシュソース」

Usage: python3 video/make_reel.py  ->  video/kanoya_salmon_reel.mp4
Requires: pillow, numpy, ffmpeg
"""
import math
import os
import subprocess
import unicodedata

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "images")
FONT_DIR = os.path.join(ROOT, "video", "fonts")
OUT = os.path.join(ROOT, "video", "kanoya_salmon_reel.mp4")

W, H, FPS, DUR = 1080, 1920, 30, 30.0
N = int(FPS * DUR)

GOLD = (201, 169, 110)
IVORY = (244, 238, 226)
NAVY = (12, 20, 34)

MINCHO = os.path.join(FONT_DIR, "ShipporiMincho-Medium.ttf")
SERIF = os.path.join(FONT_DIR, "CormorantGaramond-Medium.ttf")
ITALIC = os.path.join(FONT_DIR, "CormorantGaramond-Italic.ttf")
_fonts = {}


def font(path, size):
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)


# ---------------------------------------------------------------- images
def find_image(num):
    for f in os.listdir(IMG_DIR):
        if unicodedata.normalize("NFC", f).endswith(f"{num}.jpg"):
            return os.path.join(IMG_DIR, f)
    raise FileNotFoundError(num)


class Photo:
    """Whole photo always visible (never cropped beyond a gentle Ken Burns),
    on a blurred, darkened copy of itself filling the 9:16 frame."""

    def __init__(self, num):
        im = Image.open(find_image(num))
        im.draft("RGB", (2000, 2000))
        im = im.convert("RGB")
        self.disp = (W, round(W * im.height / im.width))
        self.pos = (0, (H - self.disp[1]) // 2)
        # source a bit larger than display for crisp zooming
        sw = int(self.disp[0] * 1.25)
        self.src = im.resize((sw, round(sw * im.height / im.width)), Image.LANCZOS)
        # background: cover, blur, darken toward navy
        s = max(W / im.width, H / im.height) * 1.1
        bg = im.resize((int(im.width * s), int(im.height * s)), Image.BILINEAR)
        l, t = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(90))
        self.bg = Image.blend(bg, Image.new("RGB", (W, H), NAVY), 0.72)

    def frame(self, p, z0, z1, dx=0.0, dy=0.0):
        """p: 0..1 progress in shot. zoom z0->z1, pan dx,dy (fraction of src)."""
        e = ease_in_out(p)
        z = z0 + (z1 - z0) * e
        sw, sh = self.src.size
        cw, ch = sw / z, sh / z
        cx = sw / 2 + dx * sw * (e - 0.5)
        cy = sh / 2 + dy * sh * (e - 0.5)
        cx = clamp(cx, cw / 2, sw - cw / 2)
        cy = clamp(cy, ch / 2, sh - ch / 2)
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        fg = self.src.resize(self.disp, Image.BICUBIC, box=box)
        out = self.bg.copy()
        out.paste(fg, self.pos)
        return out


# ---------------------------------------------------------------- text
class Text:
    """Per-character reveal: each glyph fades in and rises softly, staggered."""

    def __init__(self, s, fpath, size, track, x, y, t_in, t_out,
                 stagger=0.06, vertical=False, rise=18, fade=0.7):
        self.s, self.f = s, font(fpath, size)
        self.size, self.x, self.y = size, x, y
        self.t_in, self.t_out = t_in, t_out
        self.track, self.stagger, self.vertical = track, stagger, vertical
        self.rise, self.fade = rise, fade
        self.layout()

    def layout(self):
        self.pos = []
        if self.vertical:
            step = self.size * (1.0 + self.track)
            y = self.y
            for ch in self.s:
                ox, oy = 0, 0
                if ch in "、。":
                    ox, oy = self.size * 0.6, -self.size * 0.6
                self.pos.append((ch, self.x + ox, y + step / 2 + oy, "mm"))
                y += step
        else:
            adv = [self.f.getlength(c) + self.track * self.size for c in self.s]
            total = sum(adv) - self.track * self.size
            x = self.x - total / 2
            for c, a in zip(self.s, adv):
                self.pos.append((c, x, self.y, "ls"))
                x += a

    def draw(self, mask, t):
        d = ImageDraw.Draw(mask)
        out = 1 - smooth((t - self.t_out) / 0.5)
        if out <= 0:
            return
        for i, (c, x, y, anchor) in enumerate(self.pos):
            a = ease_out((t - self.t_in - i * self.stagger) / self.fade)
            if a <= 0:
                continue
            d.text((x, y + (1 - a) * self.rise), c, font=self.f,
                   fill=int(255 * a * out), anchor=anchor)


class Line:
    """Thin gold hairline that draws outward from its centre."""

    def __init__(self, x, y, length, t_in, t_out, dur=0.9, vertical=False):
        self.x, self.y, self.len = x, y, length
        self.t_in, self.t_out, self.dur, self.vertical = t_in, t_out, dur, vertical

    def draw(self, mask, t):
        a = ease_out((t - self.t_in) / self.dur)
        out = 1 - smooth((t - self.t_out) / 0.5)
        if a <= 0 or out <= 0:
            return
        h = self.len * a / 2
        d = ImageDraw.Draw(mask)
        if self.vertical:
            d.line((self.x, self.y - h, self.x, self.y + h), fill=int(230 * out), width=2)
        else:
            d.line((self.x - h, self.y, self.x + h, self.y), fill=int(230 * out), width=2)


def render_text(frame, items, t):
    """items: list of (element, colour). Soft shadow then fill."""
    groups = {}
    for el, col in items:
        groups.setdefault(col, []).append(el)
    shadow = Image.new("L", (W, H), 0)
    masks = []
    for col, els in groups.items():
        m = Image.new("L", (W, H), 0)
        for el in els:
            el.draw(m, t)
        if m.getbbox():
            masks.append((col, m))
            shadow = ImageChops.lighter(shadow, m)
    if not masks:
        return frame
    sh = shadow.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.75))
    frame = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), frame, sh)
    for col, m in masks:
        frame = Image.composite(Image.new("RGB", (W, H), col), frame, m)
    return frame


# ---------------------------------------------------------------- transitions
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
DIAG = (xx * 0.6 + yy * 0.8)
DIAG = (DIAG - DIAG.min()) / (DIAG.max() - DIAG.min())
RADIAL = np.sqrt((xx - W / 2) ** 2 + (yy - H * 0.55) ** 2)
RADIAL /= RADIAL.max()
SPLIT = np.abs(yy - H / 2) / (H / 2)
GLOW = np.clip(1 - np.sqrt((xx - W * 0.7) ** 2 + (yy - H * 0.35) ** 2) / (H * 0.75), 0, 1) ** 1.6


def _mask_mix(a, b, field, p, soft=0.18):
    m = np.clip((p * (1 + soft) - field) / soft, 0, 1)
    return Image.composite(b, a, Image.fromarray((m * 255).astype(np.uint8)))


def tr_light(a, b, p):          # dissolve through a warm light leak
    out = Image.blend(a, b, smooth(p))
    k = math.sin(math.pi * p) * 0.85
    glow = (GLOW[..., None] * np.array([255, 214, 160]) * k).astype(np.uint8)
    return ImageChops.screen(out, Image.fromarray(glow, "RGB"))


def tr_diag(a, b, p):           # soft-edged diagonal sweep
    return _mask_mix(a, b, DIAG, ease_in_out(p), 0.25)


def tr_blur(a, b, p):           # defocus dissolve
    r = math.sin(math.pi * p) * 22
    if r > 0.5:
        a, b = a.filter(ImageFilter.GaussianBlur(r)), b.filter(ImageFilter.GaussianBlur(r))
    return Image.blend(a, b, smooth(p))


def tr_shoji(a, b, p):          # opens from the centre like sliding screens
    return _mask_mix(a, b, SPLIT, ease_in_out(p), 0.12)


def tr_push(a, b, p):           # curtain rise: new shot slides up, old one recedes
    e = ease_in_out(p)
    out = Image.new("RGB", (W, H), NAVY)
    out.paste(Image.blend(a, Image.new("RGB", (W, H), NAVY), e * 0.7), (0, int(-e * H * 0.3)))
    out.paste(b, (0, int((1 - e) * H)))
    return out


def tr_iris(a, b, p):           # soft iris opening on the plate
    return _mask_mix(a, b, RADIAL, ease_in_out(p), 0.2)


def tr_zoom(a, b, p):           # cross-zoom dissolve
    e = ease_in_out(p)

    def scaled(im, s):
        w, h = int(W * s), int(H * s)
        im = im.resize((w, h), Image.BILINEAR)
        l, t = (w - W) // 2, (h - H) // 2
        return im.crop((l, t, l + W, t + H))

    return Image.blend(scaled(a, 1 + 0.18 * e), scaled(b, 1.12 - 0.12 * e), smooth(p))


def tr_fade(a, b, p):
    return Image.blend(a, b, smooth(p))


# ---------------------------------------------------------------- storyboard
J, S, I = MINCHO, SERIF, ITALIC
CX = W // 2


class Shot:
    def __init__(self, start, end, render, texts, trans_in=None):
        self.start, self.end, self.render = start, end, render
        self.texts, self.trans_in = texts, trans_in


def photo_shot(num, z0, z1, dx=0.0, dy=0.0):
    ph = Photo(num)
    return lambda p: ph.frame(p, z0, z1, dx, dy)


def build():
    shots = []
    # 01 — Opening title (0165, portrait: dark cloth above the plate)
    shots.append(Shot(0.0, 4.0, photo_shot("0165", 1.10, 1.0, 0, 0.02), [
        (Text("ある日のディナーより", J, 38, 0.32, CX, 380, 0.6, 3.2, stagger=0.05), GOLD),
        (Line(CX, 430, 260, 1.0, 3.2), GOLD),
        (Text("L'Artisan", I, 96, 0.04, CX, 550, 1.2, 3.2, stagger=0.05), IVORY),
        (Text("KANOYA", S, 84, 0.42, CX, 655, 1.5, 3.2, stagger=0.07), IVORY),
    ]))
    # 02 — Ora King Salmon (0155)
    shots.append(Shot(3.4, 7.4, photo_shot("0155", 1.0, 1.07, 0.02, 0), [
        (Text("Ora King Salmon", I, 86, 0.02, CX, 400, 4.2, 6.7, stagger=0.035), GOLD),
        (Text("オーラキングサーモン", J, 50, 0.22, CX, 485, 4.6, 6.7, stagger=0.045), IVORY),
    ], tr_light))
    # 03 — texture (0153, closest shot)
    shots.append(Shot(6.8, 10.6, photo_shot("0153", 1.06, 1.0, -0.02, 0.01), [
        (Text("澄んだ海が育んだ、", J, 48, 0.16, CX, 1420, 7.6, 9.9, stagger=0.06), IVORY),
        (Text("とろけるような脂の甘み", J, 48, 0.16, CX, 1500, 8.1, 9.9, stagger=0.06), IVORY),
    ], tr_diag))
    # 04 — Sauce Gribiche (0150, portrait)
    shots.append(Shot(10.0, 13.8, photo_shot("0150", 1.0, 1.06, 0, -0.02), [
        (Text("Sauce Gribiche", I, 84, 0.02, CX, 380, 10.8, 13.1, stagger=0.035), GOLD),
        (Text("グリビッシュソース", J, 50, 0.22, CX, 465, 11.2, 13.1, stagger=0.045), IVORY),
    ], tr_blur))
    # 05 — sauce details (0145)
    shots.append(Shot(13.2, 17.0, photo_shot("0145", 1.07, 1.0, 0.02, 0), [
        (Text("茹で卵、ケッパー、香草。", J, 48, 0.14, CX, 1420, 14.0, 16.3, stagger=0.05), IVORY),
        (Text("フランス古典のソースを、軽やかに", J, 44, 0.12, CX, 1495, 14.6, 16.3, stagger=0.045), IVORY),
    ], tr_shoji))
    # 06 — asparagus (0147)
    shots.append(Shot(16.4, 20.2, photo_shot("0147", 1.0, 1.07, -0.02, 0.01), [
        (Line(CX, 395, 120, 17.2, 19.5), GOLD),
        (Text("瑞々しいアスパラガスを添えて", J, 48, 0.14, CX, 480, 17.4, 19.5, stagger=0.05), IVORY),
    ], tr_push))
    # 07 — vertical copy (0152, portrait)
    shots.append(Shot(19.6, 23.6, photo_shot("0152", 1.08, 1.0, 0, 0.02), [
        (Text("職人の手で、", J, 50, 0.32, 905, 230, 20.4, 22.9, stagger=0.09, vertical=True, rise=0), IVORY),
        (Text("その日だけの一皿を", J, 50, 0.32, 820, 290, 21.0, 22.9, stagger=0.09, vertical=True, rise=0), IVORY),
        (Line(990, 470, 360, 20.4, 22.9, vertical=True), GOLD),
    ], tr_iris))
    # 08 — tagline (0157)
    shots.append(Shot(23.0, 26.8, photo_shot("0157", 1.0, 1.06, 0.01, -0.01), [
        (Text("その日限りのフレンチを", J, 54, 0.2, CX, 450, 23.8, 26.0, stagger=0.06), IVORY),
        (Text("Une assiette, un jour.", I, 52, 0.03, CX, 1450, 24.5, 26.0, stagger=0.03), GOLD),
    ], tr_zoom))
    # End card (blurred 0157 behind)
    end_bg = Photo("0157").bg.filter(ImageFilter.GaussianBlur(10))
    end_bg = Image.blend(end_bg, Image.new("RGB", (W, H), NAVY), 0.35)
    shots.append(Shot(26.0, 30.0, lambda p: end_bg, [
        (Text("ある日のディナーより", J, 32, 0.32, CX, 760, 26.6, 99, stagger=0.04), GOLD),
        (Text("L'Artisan", I, 112, 0.04, CX, 900, 26.8, 99, stagger=0.05), IVORY),
        (Text("KANOYA", S, 92, 0.42, CX, 1020, 27.1, 99, stagger=0.07), IVORY),
        (Line(CX, 1085, 300, 27.5, 99), GOLD),
        (Text("奈良春日 鹿のや 内", J, 38, 0.24, CX, 1165, 27.8, 99, stagger=0.04), IVORY),
        (Text("lartisankanoya.com", I, 44, 0.05, CX, 1250, 28.2, 99, stagger=0.02), GOLD),
    ], tr_fade))
    return shots


def shot_frame(sh, t):
    p = (t - sh.start) / (sh.end - sh.start)
    return render_text(sh.render(clamp(p)), sh.texts, t)


VIGNETTE = Image.fromarray(
    (np.clip(1.05 - 0.55 * np.sqrt(((xx - W / 2) / W) ** 2 * 1.6 + ((yy - H / 2) / H) ** 2 * 2.2), 0, 1)
     * 255).astype(np.uint8)).convert("RGB")


def main():
    shots = build()
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
           "-t", str(DUR), "-c:v", "libx264", "-preset", "slow", "-crf", "18",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "128k", "-shortest", OUT]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(N):
        t = f / FPS
        live = [s for s in shots if s.start <= t < s.end]
        if len(live) == 1:
            img = shot_frame(live[0], t)
        else:
            a, b = live[0], live[-1]
            p = (t - b.start) / (a.end - b.start)
            img = b.trans_in(shot_frame(a, t), shot_frame(b, t), clamp(p))
        img = ImageChops.multiply(img, VIGNETTE)
        # fade in from black / fade out at the very end
        k = smooth(t / 0.9) * (1 - smooth((t - (DUR - 0.5)) / 0.5))
        if k < 1:
            img = Image.blend(Image.new("RGB", (W, H)), img, k)
        ff.stdin.write(img.tobytes())
        if f % 60 == 0:
            print(f"{t:5.1f}s", flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
