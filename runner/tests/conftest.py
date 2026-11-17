import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))      # reprova_runner
sys.path.insert(0, str(HERE))             # fakes
sys.path.insert(0, str(HERE.parents[1] / "fixtures"))  # demo targets
