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
    config.ENEMY02_IMAGE: 7,
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
            cell_size = 384 if name == config.ENEMY02_IMAGE else 256
            if image.size != (8 * cell_size, row_count * cell_size):
                raise ValueError(f"Unexpected sprite grid: {name} {image.size}")
            rows = []
            for row in range(row_count):
                frames = []
                bounds = [image.crop((col * cell_size, row * cell_size,
                                      (col + 1) * cell_size, (row + 1) * cell_size)).getbbox()
                          for col in range(8)]
                ground_anchor = max(box[3] for box in bounds)
                for col, (left, top, right, bottom) in enumerate(bounds):
                    frame = {
                        "clip": [col * cell_size + left, image.height - row * cell_size - bottom,
                                 right - left, bottom - top],
                        "offset_x": (left + right) / 2 - cell_size / 2,
                    }
                    if name == config.ENEMY02_IMAGE and row == 4:
                        # The fifth row's lift drives real jump/collision height.
                        # Do not also add offset_y when drawing that attack.
                        frame["jump_height"] = ground_anchor - bottom
                    elif name in (config.ENEMY02_IMAGE,
                                  config.COUNTER_PLAYER_IMAGE, config.COUNTER_ENEMY_IMAGE,
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
