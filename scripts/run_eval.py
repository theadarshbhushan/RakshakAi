"""
Forwarder script to ml/eval/run_eval.py for backward compatibility.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ml.eval.run_eval import main

if __name__ == "__main__":
    main()
