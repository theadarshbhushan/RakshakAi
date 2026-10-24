# RakshakAI Datasets & Attribution Registry

This document lists all external, synthetic, and benchmark datasets utilized in the **RakshakAI** intelligent multi-tenant hostel security platform, including their data formats, purpose, and licensing terms.

---

## 1. Simuletic CCTV Aggressive Pose & Fight Detection Dataset (Free Sample)

- **Source / Provider**: [Simuletic](https://simuletic.com/)
- **Local Directory**: `data/raw_datasets/cctv_aggressive_poses/Aggressive_Poses_Dataset/`
- **Configuration**: [`ml/configs/cctv_pose.yaml`](file:///d:/RakshakAi/rakshak/ml/configs/cctv_pose.yaml)
- **Modality**: High-resolution synthetic CCTV image frames with 2D pose annotations
- **Dataset Size**:
  - **Images**: 103 synthetic CCTV frames (hallway, room, and corridor angles)
  - **Instances**: 207 labeled person instances
  - **Labels Format**: YOLO pose format (`<class_id> <x_center> <y_center> <width> <height> <kpt_1_x> <kpt_1_y> <v_1> ... <kpt_17_x> <kpt_17_y> <v_17>`)
  - **Keypoint Topology**: 17 COCO keypoints (`kpt_shape: [17, 3]`, visibility flags $v \in \{0, 1, 2\}$)
- **Licence**: **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**
  - *Non-Commercial*: For evaluation, academic research, and offline testing only.
  - *Synthetic*: No real individual imagery or identifiable human biometric data.
- **Role in RakshakAI**:
  - Serves as the independent ground truth benchmark for evaluating `yolov8n-pose.pt` keypoint accuracy on aggressive, hostile, and fighting physical postures (pushing, shoving, falls, grappling) from overhead security camera angles.
- **Benchmark Performance (`yolov8n-pose.pt` on CPU)**:
  - **Bounding Box mAP@50**: **99.50%**
  - **Bounding Box mAP@50-95**: **96.29%**
  - **Keypoint Pose mAP@50**: **99.50%**
  - **Keypoint Pose mAP@50-95**: **80.35%**
  - **Inference Latency**: **~63.3 ms / frame on CPU** (~15.8 FPS)
  - Visual samples: [`ml/eval/results/pose_examples/`](file:///d:/RakshakAi/rakshak/ml/eval/results/pose_examples/)
  - Full metrics artifact: [`ml/eval/results/pose_benchmark.json`](file:///d:/RakshakAi/rakshak/ml/eval/results/pose_benchmark.json)

---

## 2. ESC-50: Dataset for Environmental Sound Classification

- **Source**: [Karol J. Piczak / ESC-50](https://github.com/karolpiczak/ESC-50)
- **Local Directory**: `data/raw_datasets/ESC-50-master/`
- **Modality**: 5-second environmental and acoustic audio clips at 44.1 kHz mono/stereo
- **Total Samples**: 2,000 labeled environmental recordings (50 semantically balanced classes)
- **Licence**: **Creative Commons Attribution-NonCommercial 3.0 (CC BY-NC 3.0)**
- **Role in RakshakAI**:
  - **Distress Sound Benchmarks**: Cry, scream, and glass shattering audio samples for YAMNet audio distress pipeline calibration.
  - **Hard Negative Calibration**: Cheering, laughter, applause, and background ambient sounds used to test contextual ratio suppression filters (`context_ratio: 0.80`), ensuring false positive rates stay below 5%.

---

## 3. RakshakAI Synthetic Multi-Modal Scenarios & Camera Feeds

- **Generator Module**: [`backend/app/detectors/synthetic_media.py`](file:///d:/RakshakAi/rakshak/backend/app/detectors/synthetic_media.py)
- **Local Directories**:
  - `data/videos/intrusion/`: Restricted roof/terrace boundary intrusion clips
  - `data/videos/tailgating/`: Turnstile and door line crossing sequences
  - `data/videos/normal/`: Common room daytime baseline behavior
  - `data/audio/distress/` & `data/audio/hard_negative/`: Synthetic distress and cheering WAV audio files
- **Modality**: Multi-modal paired video (MP4) and audio (WAV) timelines
- **Licence**: Apache 2.0 / RakshakAI Internal Test Fixtures
- **Privacy Design**:
  - Automatically synthesized using procedural humanoids and frequency-modulated audio synthesis.
  - Contains **zero real biometric recordings, zero raw facial imagery, and zero student PII**.
