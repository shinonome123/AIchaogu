from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim_trading.cli import main_serve_webhook


if __name__ == "__main__":
    raise SystemExit(main_serve_webhook())
