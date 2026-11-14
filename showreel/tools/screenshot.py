"""Screenshot a demo's real Qt window without a display.

    python showreel/tools/screenshot.py showreel/demos/jpeg.py out.png [--delay 3.0] [--size 1280x800]

The script is run as `python demo.py -b qt` on Qt's offscreen platform, the
window is grabbed after `--delay` seconds, then the application quits.
"""

import argparse
import os
import runpy
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--delay", type=float, default=3.0, help="seconds to wait before grabbing the window")
    parser.add_argument("--size", default=None, help="window size WxH (default: the size the demo asks for)")
    args = parser.parse_args()
    if args.size is not None:
        os.environ["INTERACTIVE_PIPE_SIZE"] = args.size

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([str(args.script)])
    saved = []

    def grab():
        windows = [widget for widget in app.topLevelWidgets() if widget.isVisible()]
        if windows:
            window = max(windows, key=lambda widget: widget.width() * widget.height())
            args.output.parent.mkdir(parents=True, exist_ok=True)
            saved.append(window.grab().save(str(args.output)))
        app.quit()

    QTimer.singleShot(int(args.delay * 1000), grab)
    sys.argv = [str(args.script), "-b", "qt"]
    sys.path.insert(0, str(args.script.resolve().parent))
    runpy.run_path(str(args.script), run_name="__main__")
    if not any(saved):
        print(f"no window to grab for {args.script}", file=sys.stderr)
        return 1
    print(f"saved {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
