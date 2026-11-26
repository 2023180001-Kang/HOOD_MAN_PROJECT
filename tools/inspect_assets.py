"""Print source image dimensions and occupied sprite bounds for asset setup."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in (
        "HoodMan_Sprite.png",
        "HoodMan_StreetThug_FINAL_2048x1536.png",
        "HOOD_MAN_enemy02.png",
        "HoodMan_BasicAttack_4Moves_8Frames_2048x1024.png",
        "HoodMan_StrongAttacks_Uppercut_IDLE_FINAL_2048x1280.png",
        "HoodMan_Enemy_StrongHit_2048x1280.png",
        "HoodMan_CombatKnife_changed_version_8x8.png",
        "HOOD_MAN_STEEL_PIPE_move and fight.png",
        "before_sheets/HoodMan_BasicCombat_9Moves_8Frames_2048x2304.png",
        "club_hit_effect_4x2.png",
        "punch_kick_hit_effect_4x2.png",
        "HoodMan_HP_pico2d.png",
        "newStage.png",
    ):
        with Image.open(ROOT / name) as source:
            image = source.convert("RGBA")
            print(name, source.size, source.mode, "alpha", image.getextrema()[3])
            print("corners", image.getpixel((0, 0)), image.getpixel((image.width - 1, 0)))
            if "HP" in name:
                for y in (140, 145, 150, 180, 210, 230, 234, 240):
                    blue = [x for x in range(400, 2010)
                            if image.getpixel((x, y))[2] > image.getpixel((x, y))[0] + 25
                            and image.getpixel((x, y))[3] > 200]
                    print("blue fill", y, (min(blue), max(blue)) if blue else None)
            if any(part in name for part in
                   ("Sprite", "StreetThug", "enemy02", "BasicAttack", "BasicCombat", "Strong",
                    "hit_effect", "move and fight", "CombatKnife")):
                columns = 4 if "hit_effect" in name else 8
                row_count = image.height // (image.width // columns)
                for row in range(row_count):
                    bounds = []
                    for col in range(columns):
                        left = col * image.width // columns
                        top = row * image.height // row_count
                        tile = image.crop((left, top, (col + 1) * image.width // columns,
                                           (row + 1) * image.height // row_count))
                        bounds.append(tile.getbbox())
                    print("row", row + 1, bounds)


if __name__ == "__main__":
    main()
