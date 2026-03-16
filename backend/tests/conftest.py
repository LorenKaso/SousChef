import os
import sys
import tempfile
from pathlib import Path

# Ensure "backend/" is on sys.path so "import app" works in tests
ROOT = Path(__file__).resolve().parents[1]  # backend/
sys.path.insert(0, str(ROOT))

TEST_DB_PATH = Path(tempfile.gettempdir()) / "souschef_test.db"
os.environ["SOUSCHEF_DB_PATH"] = str(TEST_DB_PATH)
