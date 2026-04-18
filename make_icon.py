#!/usr/bin/env python3
"""Generate DevGrow icon PNG using Pillow (no display required)."""
import math
import sys
from pathlib import Path


def draw_rounded_rect(draw, xy, radius, **kwargs):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, **kwargs)


def hexagon_points(cx, cy, r, rotation=-30):
    return [
        (cx + r * math.cos(math.radians(60 * i + rotation)),
         cy + r * math.sin(math.radians(60 * i + rotation)))
        for i in range(6)
    ]


def main(out_path: str) -> None:
    from PIL import Image, ImageDraw

    SIZE = 512
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background — deep dark with rounded corners
    draw.rounded_rectangle(
        [0, 0, SIZE, SIZE],
        radius=SIZE // 7,
        fill=(10, 10, 20, 255),
    )

    cx, cy = SIZE // 2, SIZE // 2

    # Outer hex glow (faint fill)
    r_outer = SIZE * 0.40
    draw.polygon(hexagon_points(cx, cy, r_outer), fill=(124, 58, 237, 35))

    # Outer hex border
    pts_outer = hexagon_points(cx, cy, r_outer)
    for i in range(6):
        draw.line([pts_outer[i], pts_outer[(i + 1) % 6]],
                  fill=(124, 58, 237, 200), width=4)

    # Inner hex fill
    r_inner = SIZE * 0.27
    draw.polygon(hexagon_points(cx, cy, r_inner), fill=(124, 58, 237, 60))

    # "DG" text — draw manually with thick strokes for crisp look
    # D
    lx = cx - SIZE * 0.14
    ty = cy - SIZE * 0.12
    by = cy + SIZE * 0.12
    stroke = max(4, SIZE // 60)
    color = (167, 139, 250, 255)

    # D — vertical bar
    draw.rectangle([lx, ty, lx + stroke, by], fill=color)
    # D — top/bottom bars
    draw.rectangle([lx, ty, lx + SIZE * 0.08, ty + stroke], fill=color)
    draw.rectangle([lx, by - stroke, lx + SIZE * 0.08, by], fill=color)
    # D — right curve (approximated with a rectangle)
    draw.rectangle([lx + SIZE * 0.07, ty + SIZE * 0.03,
                    lx + SIZE * 0.10, by - SIZE * 0.03], fill=color)

    # G
    gx = cx + SIZE * 0.02
    draw.rectangle([gx, ty, gx + SIZE * 0.10, ty + stroke], fill=color)         # top
    draw.rectangle([gx, by - stroke, gx + SIZE * 0.10, by], fill=color)         # bottom
    draw.rectangle([gx, ty, gx + stroke, by], fill=color)                        # left
    draw.rectangle([gx + SIZE * 0.09, cy - stroke // 2,                          # right notch
                    gx + SIZE * 0.10, by], fill=color)
    draw.rectangle([gx + SIZE * 0.055, cy - stroke // 2,                         # mid bar
                    gx + SIZE * 0.10, cy + stroke // 2], fill=color)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    print(f"  Icon → {out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
    main(out)
