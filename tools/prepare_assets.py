"""Generate clip metadata from the original transparent PNGs (development only)."""

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SHEETS = ("HoodMan_Sprite.png", "HoodMan_StreetThug_FINAL_2048x1536.png")


def main():
    metadata = {}
    for name in SHEETS:
        with Image.open(ROOT / name) as image:
            rows = []
            for row in range(6):
                frames = []
                for col in range(8):
                    tile = image.crop((col * 256, row * 256,
                                       (col + 1) * 256, (row + 1) * 256))
                    left, top, right, bottom = tile.getbbox()
                    frames.append({
                        "clip": [col * 256 + left, image.height - row * 256 - bottom,
                                 right - left, bottom - top],
                        "offset_x": (left + right) / 2 - 128,
                    })
                rows.append(frames)
            metadata[name] = rows
    destination = ROOT / "assets"
    destination.mkdir(exist_ok=True)
    (destination / "frames.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print("Prepared sprite clips: 2 sheets, 6 rows x 8 frames; source PNGs unchanged.")


if __name__ == "__main__":
    main()
