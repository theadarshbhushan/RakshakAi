# RakshakAI Machine Learning Package (`ml/`)

This package contains all offline machine learning pipelines, dataset calibration, offline benchmark evaluations, model configuration profiles, and trained weights for the **RakshakAI** campus and hostel safety intelligence system.

Live detector inference code is maintained in [`backend/app/detectors/`](file:///d:/RakshakAi/backend/app/detectors/) and imported directly by both the FastAPI backend and this ML package, ensuring **zero code duplication**.

---

## 1. Directory Structure

```
ml/
├── __init__.py
├── README.md                  # Complete model and evaluation documentation
├── configs/                   # Model and heuristic parameter configurations
│   ├── audio_yamnet.yaml      # YAMNet thresholds, classes, context ratio
│   ├── video_yolo.yaml        # YOLOv8n-pose FPS, tracking, keypoint polygons
│   └── detection_rules.yaml   # Multi-modal fusion weights and severity rules
├── models/                    # Trained model weights (git-ignored)
│   ├── .gitkeep
│   └── audio_head.joblib      # Calibrated distress classification head
├── train/                     # Offline model training pipelines
│   ├── __init__.py
│   └── train_audio_head.py    # Stratified logistic regression on YAMNet embeddings
└── eval/                      # Offline evaluation suite & benchmark dataset
    ├── __init__.py
    ├── run_eval.py            # Offline benchmark runner across all tasks
    ├── labels.csv             # Ground truth evaluation matrix with fairness slices
    └── results/               # Generated evaluation artifacts consumed by /eval API
        ├── .gitkeep
        ├── results.json       # Benchmark metrics, PR scores, and fairness slices
        ├── fpr_comparison.png # Bar chart comparing single vs multi-modal FPR
        └── confusion_matrices.png # Confusion matrices for each task
```

---

## 2. Models & Architecture

### A. Video Pose & Tracking (`app/detectors/video_pose.py`)
- **Base Architecture**: YOLOv8n-pose (`yolov8n-pose.pt`, 3.3M parameters, CPU-only execution).
- **Tracker**: ByteTrack (`bytetrack.yaml`) with persistent track IDs.
- **Pre-processing**: Frames resized to max 640px width; processed at ~8 FPS (skipping intermediate frames).
- **Zone Intrusion**:
  - Calculates the midpoint of the person's left and right ankle keypoints (indices 15 & 16), with bounding-box bottom-center as fallback.
  - Performs `cv2.pointPolygonTest` against normalized camera polygon vertices defined in Mongo/calibration.
  - Requires $\ge 5$ consecutive processed frames inside the zone to emit `zone_intrusion` (20-second cooldown per track).
- **Line Crossing**: Centroid trajectory intersection against camera door line in the `"in"` direction. Emits `line_crossing` for tailgating corroboration.
- **Loitering Heuristic**: Emits `loitering` when a track persists inside a corridor or restricted zone longer than `loiter_seconds` (default 45s) during active curfew hours.
- **Fight Heuristic (Experimental, `FIGHT_DETECTION=true`)**:
  - Two tracks with box center distance $< 1.2 \times \text{mean box width}$.
  - Mean normalized wrist speed exceeds motion threshold for $\ge 1.0\text{s}$.
- **Camera Tamper Detection**:
  - **Lens Covered/Blackout**: Mean frame brightness $< 15$.
  - **Heavy Defocus/Blur**: Variance of Laplacian drops significantly below rolling camera baseline.
  - **View Redirection**: Color histogram correlation drops below threshold for $> 3.0\text{s}$.
- **Privacy Enforcement**:
  - **Public Evidence**: Skeleton render (keypoints + bones on black canvas with polygon overlay) saved to `data/evidence/public/`.
  - **Restricted Evidence**: Strictly face-blurred frame (Gaussian blur over bounding region spanned by nose, eyes, and ears) saved to `data/evidence/restricted/`.
  - **Live Stream**: `GET /api/v1/stream/{camera_id}?mode=skeleton` (MJPEG) and `mode=blurred` (requires active break-glass grant).

### B. Audio Distress Pipeline (`app/detectors/audio_distress.py`)
- **Base Architecture**: Google YAMNet loaded via TensorFlow Hub (`google/yamnet/1`). Audio resampled to 16 kHz mono; analyzed in 0.96s windows with 0.48s hops.
- **Dynamic Class Mapping**: Reads class names from YAMNet's runtime CSV (521 classes; zero hardcoded indices).
- **Distress Classes**: Screaming, Shout, Yell, Children shouting, Crying/sobbing, Wail/moan, Glass, Shatter.
- **Confusable Classes**: Laughter, Giggle, Chuckle/chortle, Cheering, Applause, Crowd, Music, Singing, Children playing.
- **3-Stage Contextual Filtering Pipeline**:
  1. **Stage 1 (Threshold)**: Distress score $= \max(\text{distress classes}) \ge \text{threshold}$.
  2. **Stage 2 (Context Filter)**: Suppressed if $\text{confusable\_max} \ge \text{distress\_max} \times \text{context\_ratio}$ (default 0.8), logging explainable reason (e.g. `"Laughter 0.37 >= 0.8 x Crying, sobbing 0.37"`).
  3. **Stage 3 (Temporal Persistence)**: Requires $\ge 2$ of the last 3 sliding windows to pass Stages 1 & 2; otherwise suppressed with reason `"not persistent"`.
- **Evidence**: Restricts saving to a 3-second audio clip in `data/evidence/restricted/`. **Never stores transcripts**.
- **Optional Calibrated Audio Head (`AUDIO_CLASSIFIER=yamnet_head`)**:
  - Trained via `ml/train/train_audio_head.py`. A calibrated Logistic Regression classifier fitted on mean 1024-dim YAMNet embeddings. Saved to `ml/models/audio_head.joblib`.
- **Optional Keyword Spotter (`HELP_KEYWORDS=true`)**:
  - Uses `faster-whisper` (`tiny`, CPU) to detect emergency distress words (`"help"`, `"bachao"`). Adds $+0.15$ score boost on hit without logging transcripts.

---

## 3. Datasets Used

1. **ESC-50 (Dataset for Environmental Sound Classification)**:
   - Used for calibration, audio head training, and hard-negative evaluation.
   - Positive distress categories: `crying_baby`, `glass_breaking`.
   - Hard-negative / confusable categories: `laughing`, `clapping`, `coughing`, `sneezing`, `breathing`.
2. **Real Life Violence Dataset**:
   - Violence vs non-violence CCTV footage used to evaluate multi-person movement and loitering.
3. **Synthetic Humanoid & Calibrated Audio Fixtures (`backend/app/detectors/synthetic_media.py`)**:
   - Procedural stick-figure humanoid generation rendering natural walking motion into camera polygons, two figures crossing door lines, and corridor traversals.
   - Calibrated acoustic audio generation with modulated formant frequencies, ensuring tests run from a fresh clone even without pre-downloaded external datasets.

---

## 4. Evaluation Metrics & Benchmark Results

Offline evaluation is run without database dependencies via `ml/eval/run_eval.py`.

### A. Task-by-Task Performance

| Task / Pipeline | Precision | Recall | F1 Score | False Positive Rate | Latency (s / s media) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **audio_distress** | 0.75 | 1.00 | 0.86 | 20.0% | **0.131x** |
| **access_rules** | 1.00 | 1.00 | 1.00 | 0.0% | N/A |
| **loitering** | 0.50 | 1.00 | 0.67 | 100.0% | **0.754x** |
| **tailgating** | 1.00 | 1.00 | 1.00 | 0.0% | **0.452x** |
| **zone_intrusion** | 1.00 | 1.00 | 1.00 | 0.0% | **0.405x** |

*Note: Processing latencies are on standard CPU. All detectors process media faster than real-time ($< 1.0\text{x}$).*

### B. Multi-Modal Corroboration Comparison

The core premise of RakshakAI is corroborating multiple modalities to eliminate single-modality false alarms:

| Modality Alert | Precision | Recall | F1 Score | False Positive Rate (FPR) |
| :--- | :---: | :---: | :---: | :---: |
| **Audio Only** | 0.33 | 0.50 | 0.40 | **33.3%** |
| **Video Only** | 0.50 | 1.00 | 0.67 | **33.3%** |
| **RakshakAI Multi-Modal Fused** | **1.00** | **1.00** | **1.00** | **0.0%** |

**Result**: Multi-modal fusion reduces false positive rate from **33.3% down to 0.0%** while retaining 100% detection recall.

### C. Demographic Fairness Slice: Audio by Voice Gender

| Voice Slice | Samples | Precision | Recall | False Positive Rate (FPR) |
| :--- | :---: | :---: | :---: | :---: |
| **Female** | 3 | 1.00 | 1.00 | 0.0% |
| **Male** | 2 | 1.00 | 1.00 | 0.0% |
| **Mixed / Crowd** | 1 | 0.00 | 0.00 | 100.0% |
| **N/A (Ambient)** | 2 | 1.00 | 0.00 | 0.0% |

---

## 5. How to Run

### Run Training
To train the custom YAMNet distress classification head:
```powershell
py -3.11 ml/train/train_audio_head.py
```
Outputs saved to `ml/models/audio_head.joblib`.

### Run Evaluation Suite
To execute full offline benchmarking across all tasks, access rules, and multi-modal fusion:
```powershell
py -3.11 ml/eval/run_eval.py
```
Results and charts are saved directly into `ml/eval/results/`:
- `ml/eval/results/results.json`
- `ml/eval/results/fpr_comparison.png`
- `ml/eval/results/confusion_matrices.png`

### Consume from Backend API
The FastAPI backend serves these benchmark results:
- `GET /api/v1/eval/results`: Returns `ml/eval/results/results.json`
- `POST /api/v1/eval/run`: Runs `ml/eval/run_eval.py` asynchronously in the background (requires `rules:write` permission).
