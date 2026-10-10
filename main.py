"""Windows entry point."""
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.smoke_test:
        # Imports the complete GUI dependency chain in the packaged executable.
        # The Windows build script uses this to catch omitted local packages.
        from automation import worker  # noqa: F401
        from reports import html_report  # noqa: F401
        from storage import history, settings  # noqa: F401
        return

    from gui.main_window import App
    App(data_dir=args.data_dir).mainloop()


if __name__ == '__main__':
    main()
