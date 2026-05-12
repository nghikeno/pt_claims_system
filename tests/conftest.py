import os
import sys
from pathlib import Path
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="pt_claims_pytest_"))
TEST_DB_PATH = TEST_DB_DIR / "pt_claims_test.db"
os.environ["PT_CLAIMS_DB_PATH"] = str(TEST_DB_PATH)
