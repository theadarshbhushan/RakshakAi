"""
Train lightweight classification head on YAMNet embeddings for custom distress detection.
Saves calibrated classifier to ml/models/audio_head.joblib.
Runs in under 2 minutes on CPU.
"""
import os
import sys
from pathlib import Path
from typing import List, Tuple

# Add backend and project root to sys.path so app imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import librosa
import numpy as np
import soundfile as sf
import tensorflow as tf
import tensorflow_hub as hub
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

from app.core.config import settings
from app.detectors.synthetic_media import generate_audio_file


def extract_yamnet_embedding(model, file_path: Path) -> np.ndarray:
    """Load audio file at 16kHz mono and return mean 1024-dim YAMNet embedding."""
    wav, sr = librosa.load(str(file_path), sr=16000, mono=True)
    if len(wav) < 15360:
        pad = np.zeros(15360 - len(wav), dtype=np.float32)
        wav = np.concatenate([wav, pad])
    wav_tensor = tf.convert_to_tensor(wav, dtype=tf.float32)
    _, embeddings, _ = model(wav_tensor)
    return np.mean(embeddings.numpy(), axis=0)


def gather_training_samples() -> Tuple[List[np.ndarray], List[int]]:
    data_dir = settings.DATA_DIR
    raw_dir = data_dir / "raw_datasets"
    train_dir = data_dir / "audio_train"
    train_dir.mkdir(parents=True, exist_ok=True)
    (train_dir / "scream").mkdir(exist_ok=True)
    (train_dir / "non_scream").mkdir(exist_ok=True)

    pos_files: List[Path] = list((train_dir / "scream").glob("*.wav"))
    neg_files: List[Path] = list((train_dir / "non_scream").glob("*.wav"))

    # Also add files from data/audio/distress and data/audio/hard_negative
    pos_files.extend(list((data_dir / "audio" / "distress").glob("*.wav")))
    neg_files.extend(list((data_dir / "audio" / "hard_negative").glob("*.wav")))
    neg_files.extend(list((data_dir / "audio" / "normal").glob("*.wav")))

    # Pull ESC-50 samples if available
    esc_dir = raw_dir / "ESC-50-master" / "audio"
    esc_meta = raw_dir / "ESC-50-master" / "meta" / "esc50.csv"
    if esc_dir.exists() and esc_meta.exists():
        import pandas as pd
        df = pd.read_csv(esc_meta)
        pos_cats = ["glass_breaking", "crying_baby"]
        neg_cats = ["laughing", "clapping", "footsteps", "coughing", "door_wood_knock", "sneezing", "breathing"]

        for _, row in df[df["category"].isin(pos_cats)].head(15).iterrows():
            f = esc_dir / row["filename"]
            if f.exists():
                pos_files.append(f)

        for _, row in df[df["category"].isin(neg_cats)].head(25).iterrows():
            f = esc_dir / row["filename"]
            if f.exists():
                neg_files.append(f)

    # If dataset has fewer than 15 in each, generate synthetic samples to augment
    idx = 0
    while len(pos_files) < 15:
        idx += 1
        syn_pos = train_dir / "scream" / f"syn_distress_{idx}.wav"
        generate_audio_file(syn_pos, sound_type="distress", duration_s=3.0)
        pos_files.append(syn_pos)

    while len(neg_files) < 20:
        idx += 1
        syn_neg = train_dir / "non_scream" / f"syn_cheering_{idx}.wav"
        generate_audio_file(syn_neg, sound_type="cheering", duration_s=3.0)
        neg_files.append(syn_neg)

    print(f"Collected {len(pos_files)} positive distress samples and {len(neg_files)} negative samples.")

    print("Loading YAMNet feature extractor...")
    model = hub.load("https://tfhub.dev/google/yamnet/1")

    X, y = [], []
    print("Extracting embeddings for positive samples...")
    for pf in pos_files:
        try:
            emb = extract_yamnet_embedding(model, pf)
            X.append(emb)
            y.append(1)
        except Exception as e:
            print(f"Skipping {pf}: {e}")

    print("Extracting embeddings for negative samples...")
    for nf in neg_files:
        try:
            emb = extract_yamnet_embedding(model, nf)
            X.append(emb)
            y.append(0)
        except Exception as e:
            print(f"Skipping {nf}: {e}")

    return np.array(X), np.array(y)


def main():
    print("=== Training YAMNet Audio Head Classifier ===")
    X, y = gather_training_samples()

    print(f"Dataset shape: X={X.shape}, y={y.shape} (Positives: {np.sum(y)}, Negatives: {len(y) - np.sum(y)})")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )

    clf = LogisticRegression(C=1.0, max_iter=500, solver="lbfgs")
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    print("\n--- Validation Performance (Stratified 80/20) ---")
    print(classification_report(y_test, y_pred, target_names=["Non-Distress", "Distress"]))
    print(f"Precision: {prec:.3f} | Recall: {rec:.3f} | F1: {f1:.3f}")

    models_dir = PROJECT_ROOT / "ml" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    out_path = models_dir / "audio_head.joblib"
    joblib.dump(clf, str(out_path))
    print(f"Model saved successfully to: {out_path}")

    # Also keep sync with legacy backend path if needed
    legacy_dir = PROJECT_ROOT / "models"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, str(legacy_dir / "audio_head.joblib"))


if __name__ == "__main__":
    main()
