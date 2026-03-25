"""Genere l'icone WinBoost en .ico a partir d'un PNG genere par code.

Necessite Pillow : pip install Pillow
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow requis : pip install Pillow")
    sys.exit(1)


def generate_icon(output_dir: Path | None = None) -> Path:
    """Genere une icone WinBoost simple."""
    out = output_dir or Path(__file__).parent
    sizes = [16, 32, 48, 64, 128, 256]

    images = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fond rond gradient-like
        margin = max(1, size // 16)
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=size // 4,
            fill=(233, 69, 96),  # accent color #e94560
        )

        # Lettre "W"
        font_size = int(size * 0.55)
        try:
            font = ImageFont.truetype("segoeui.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        text = "W"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (size - tw) // 2 - bbox[0]
        y = (size - th) // 2 - bbox[1]
        draw.text((x, y), text, fill=(255, 255, 255), font=font)

        images.append(img)

    # Sauvegarde .ico
    ico_path = out / "icon.ico"
    images[0].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
    print(f"Icone generee : {ico_path}")

    # Sauvegarde PNG 256x256
    png_path = out / "icon.png"
    images[-1].save(png_path, format="PNG")
    print(f"PNG genere : {png_path}")

    return ico_path


if __name__ == "__main__":
    generate_icon()
