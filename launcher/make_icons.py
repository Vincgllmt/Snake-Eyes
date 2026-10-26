"""Génère les icônes de l'application (deux dés « snake eyes »).

    static/icons/icon-192.png, icon-512.png   manifest PWA / favicon
    launcher/snake-eyes.ico                   raccourcis Windows

Nécessite Pillow (pip install pillow), uniquement pour régénérer les icônes.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BG = (0x1D, 0x1F, 0x24, 255)
DIE = (0xF2, 0xEE, 0xE6, 255)
PIP = (0xC8, 0x42, 0x3B, 255)
SS = 4  # suréchantillonnage pour l'anticrénelage


def die(size: int, angle: float) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.2, fill=DIE)
    pip = size * 0.26
    c = size / 2
    d.ellipse((c - pip / 2, c - pip / 2, c + pip / 2, c + pip / 2), fill=PIP)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True)


def icon(px: int) -> Image.Image:
    s = px * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.22, fill=BG)
    for cx, cy, angle in ((0.29, 0.55, 12), (0.71, 0.45, -10)):
        d = die(int(s * 0.35), angle)
        img.alpha_composite(d, (int(s * cx - d.width / 2), int(s * cy - d.height / 2)))
    return img.resize((px, px), Image.LANCZOS)


if __name__ == "__main__":
    icons = ROOT / "static" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    for px in (192, 512):
        icon(px).save(icons / f"icon-{px}.png")
    icon(256).save(
        ROOT / "launcher" / "snake-eyes.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)],
    )
    print("Icônes générées.")
