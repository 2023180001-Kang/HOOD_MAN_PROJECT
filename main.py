"""Run HOOD_MAN_PROJECT with Python and pico2d."""

import argparse


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description="HOOD_MAN_PROJECT")
    parser.add_argument("--smoke-test", type=positive_int, metavar="FRAMES",
                        help="render a finite number of frames, then close normally")
    args = parser.parse_args()

    import pico2d

    import config
    from game import Game

    game = None
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    try:
        game = Game()
        if args.smoke_test is None:
            game.show_main_menu()
        frames = game.run(args.smoke_test)
        if args.smoke_test:
            print(f"Smoke test complete: {frames} frames.")
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
