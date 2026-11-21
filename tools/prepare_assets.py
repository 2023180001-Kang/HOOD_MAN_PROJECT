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
    config.AXE_ENEMY_IMAGE: 7,
    config.RESEARCHER_IMAGE: 7,
    config.RESEARCHER_BULLET_IMAGE: 1,
    config.ENEMY02_IMAGE: 7,
    config.COMBAT_IMAGE: 4,
    config.STRONG_ATTACK_IMAGE: 5,
    config.STRONG_HIT_IMAGE: 5,
    # Keep legacy vehicle clips reproducible without preloading their textures.
    **dict.fromkeys(config.ARCHIVED_CAR_HIT_IMAGES, 1),
    **{name: config.WEAPON_SHEET_ROWS[kind] for kind, name in config.WEAPON_POSE_IMAGES.items()},
}
AIRBORNE_WEAPON_ROWS = {config.WEAPON_POSE_IMAGES[kind]: row
                        for kind, row in config.WEAPON_AIRBORNE_ROWS.items()}


def main():
    metadata = {}
    for name, row_count in SHEETS.items():
        with Image.open(ROOT / name) as image:
            cell_width, cell_height = (384, 384) if name == config.ENEMY02_IMAGE else (256, 256)
            if image.size != (8 * cell_width, row_count * cell_height):
                raise ValueError(f"Unexpected sprite grid: {name} {image.size}")
            rows = []
            for row in range(row_count):
                frames = []
                bounds = [image.crop((col * cell_width, row * cell_height,
                                      (col + 1) * cell_width, (row + 1) * cell_height)).getbbox()
                          for col in range(8)]
                ground_anchor = max(box[3] for box in bounds)
                for col, (left, top, right, bottom) in enumerate(bounds):
                    frame = {
                        "clip": [col * cell_width + left, image.height - row * cell_height - bottom,
                                 right - left, bottom - top],
                        "offset_x": (left + right) / 2 - cell_width / 2,
                    }
                    if ((name == config.ENEMY02_IMAGE and row == 4)
                            or row + 1 == AIRBORNE_WEAPON_ROWS.get(name)):
                        # Keep the source-pose lift for inspection. The leap
                        # controller owns actual height; do not add offset_y too.
                        frame["jump_height"] = ground_anchor - bottom
                    elif name in (config.ENEMY02_IMAGE,
                                  config.STRONG_ATTACK_IMAGE, config.STRONG_HIT_IMAGE,
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
