"""
Forwarder script to ml/train/train_audio_head.py for backward compatibility.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ml.train.train_audio_head import main

if __name__ == "__main__":
    main()
