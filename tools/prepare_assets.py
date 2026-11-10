"""Generate clip metadata from the original transparent PNGs (development only)."""

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SHEETS = {
    "HoodMan_Sprite.png": 6,
    "HoodMan_StreetThug_FINAL_2048x1536.png": 6,
    "HoodMan_BasicCombat_9Moves_8Frames_2048x2304.png": 9,
}


def main():
    metadata = {}
    for name, row_count in SHEETS.items():
        with Image.open(ROOT / name) as image:
            rows = []
            for row in range(row_count):
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
    print("Prepared sprite clips: 3 sheets, 168 frames; source PNGs unchanged.")


if __name__ == "__main__":
    main()
