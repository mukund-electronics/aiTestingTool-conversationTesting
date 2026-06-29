import sys
from pathlib import Path

# Make `backend` importable when tests run from anywhere.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
