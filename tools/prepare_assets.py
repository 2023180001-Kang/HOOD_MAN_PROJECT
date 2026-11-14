"""Generate clip metadata from the original transparent PNGs (development only)."""

import json
from pathlib import Path
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config


SHEETS = {
    config.PLAYER_IMAGE: 6,
    config.ENEMY_IMAGE: 6,
    config.COMBAT_IMAGE: 4,
    config.COUNTER_PLAYER_IMAGE: 4,
    config.COUNTER_ENEMY_IMAGE: 4,
    config.PLAYER_CAR_HIT_IMAGE: 1,
    config.ENEMY_CAR_HIT_IMAGE: 1,
}


def main():
    metadata = {}
    for name, row_count in SHEETS.items():
        with Image.open(ROOT / name) as image:
            if image.size != (2048, row_count * 256):
                raise ValueError(f"Unexpected sprite grid: {name} {image.size}")
            rows = []
            for row in range(row_count):
                frames = []
                bounds = [image.crop((col * 256, row * 256,
                                      (col + 1) * 256, (row + 1) * 256)).getbbox()
                          for col in range(8)]
                ground_anchor = max(box[3] for box in bounds)
                for col, (left, top, right, bottom) in enumerate(bounds):
                    frame = {
                        "clip": [col * 256 + left, image.height - row * 256 - bottom,
                                 right - left, bottom - top],
                        "offset_x": (left + right) / 2 - 128,
                    }
                    if name in (config.COUNTER_PLAYER_IMAGE, config.COUNTER_ENEMY_IMAGE,
                                config.PLAYER_CAR_HIT_IMAGE, config.ENEMY_CAR_HIT_IMAGE):
                        # Keep airborne throws above the floor instead of moving
                        # every cropped frame's bottom down to the same feet y.
                        frame["offset_y"] = ground_anchor - bottom
                    frames.append(frame)
                rows.append(frames)
            metadata[name] = rows
    destination = ROOT / "assets"
    destination.mkdir(exist_ok=True)
    (destination / "frames.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Prepared sprite clips: {len(SHEETS)} sheets, {sum(SHEETS.values()) * 8} frames; "
          "source PNGs unchanged.")


if __name__ == "__main__":
    main()
