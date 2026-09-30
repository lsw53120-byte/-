"""Windows entry point."""
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    from gui.main_window import App
    App(data_dir=args.data_dir).mainloop()


if __name__ == '__main__':
    main()
