"""Generate clip metadata from the original transparent PNGs (development only)."""

import json
from pathlib import Path
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config


ARCHIVED_COMBAT = ROOT / "before_sheets" / "HoodMan_BasicCombat_9Moves_8Frames_2048x2304.png"
SHEETS = {
    config.PLAYER_IMAGE: 6,
    config.ENEMY_IMAGE: 6,
    config.COMBAT_IMAGE: 4,
    config.BLOCK_IMAGE: 1,
}


def main():
    # Preserve H guarding without loading the archived nine-move sheet at runtime.
    with Image.open(ARCHIVED_COMBAT) as image:
        if image.size != (2048, 2304):
            raise ValueError("The archived combat sheet must be 2048x2304")
        block_path = ROOT / config.BLOCK_IMAGE
        block_path.parent.mkdir(exist_ok=True)
        image.crop((0, 8 * 256, 2048, 9 * 256)).save(block_path)
    metadata = {}
    for name, row_count in SHEETS.items():
        with Image.open(ROOT / name) as image:
            if image.size != (2048, row_count * 256):
                raise ValueError(f"Unexpected sprite grid: {name} {image.size}")
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
    print(f"Prepared sprite clips: {len(SHEETS)} sheets, {sum(SHEETS.values()) * 8} frames; "
          "source PNGs unchanged.")


if __name__ == "__main__":
    main()
