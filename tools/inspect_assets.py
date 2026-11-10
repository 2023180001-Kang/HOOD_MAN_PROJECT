"""Print source image dimensions and occupied sprite bounds for asset setup."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in (
        "HoodMan_Sprite.png",
        "HoodMan_StreetThug_FINAL_2048x1536.png",
        "HoodMan_HP_pico2d.png",
        "stage.png",
    ):
        with Image.open(ROOT / name) as source:
            image = source.convert("RGBA")
            print(name, source.size, source.mode, "alpha", image.getextrema()[3])
            print("corners", image.getpixel((0, 0)), image.getpixel((image.width - 1, 0)))
            if "Sprite" in name or "StreetThug" in name:
                for row in range(6):
                    bounds = []
                    for col in range(8):
                        left = col * image.width // 8
                        top = row * image.height // 6
                        tile = image.crop((left, top, (col + 1) * image.width // 8,
                                           (row + 1) * image.height // 6))
                        bounds.append(tile.getbbox())
                    print("row", row + 1, bounds)


if __name__ == "__main__":
    main()
