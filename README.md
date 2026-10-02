# AI-Powered Pothole Detection and Road Accountability System

Final-year project, Department of CSE (Data Science), Dayananda Sagar University.
Team: Anoop Pola (ENG23DS0003), Amrutalakshmi H K (ENG24DS3001). Guide: Prof. Manjula M.

Upload a pre-recorded road video. The system detects and segments potholes with YOLOv8-Seg,
merges repeated detections into **unique potholes**, rates each one by **severity**
(Minor / Moderate / Critical) and **repair priority** (P1 Urgent / P2 Soon / P3 Routine),
sends an alert with photo evidence to **Telegram**, and lists everything on a **Review** page
where each detection can be approved or rejected.

## How it works

```
Road video ──> Frame sampler ──> YOLOv8-Seg ──> Tracker + dedup ──> Severity + priority
 (upload)      2 fps, skip blur    masks         unique pothole IDs    Minor/Moderate/Critical
                                                                        P1/P2/P3
                                                                            │
        Review page <── SQLite database <── Evidence image <────────────────┘
     approve / reject                      (mask overlay + crop)  ──> Telegram alert
```

| Step | File | What it does |
| --- | --- | --- |
| 1 | `src/video.py` | Takes about 2 frames per second; skips blurry frames (variance of Laplacian) |
| 2 | `src/detector.py` | YOLOv8-Seg finds and outlines potholes; drops tiny, sky-region and duplicate masks |
| 3 | `src/tracker.py` | Links detections across frames (overlap / downward motion + appearance) and merges re-detections, so each physical pothole is counted once (ID like `PH-2026-001`) |
| 4 | `src/severity.py` | Estimated Visual Severity Proxy from distance-corrected size, darkness, edge irregularity and persistence; priority also uses "in the driving path" |
| 5 | `src/evidence.py` | Saves the best frame with the pothole highlighted, plus a close-up |
| 6 | `src/telegram_notify.py` | Sends a summary + one photo alert per pothole (most urgent first) |
| 7 | `src/db.py` | Stores videos, potholes and review decisions in `data/potholes.db` |
| - | `app.py`, `views/` | Web app: Upload page and Review page |

### Severity and priority

```
S = 0.55 x size + 0.20 x darkness + 0.15 x ragged edges + 0.10 x persistence   (each 0-1)
```

| Severity | Score | | Priority | Rule |
| --- | --- | --- | --- | --- |
| Minor | S < 0.40 | | P1 Urgent | Critical, or Moderate in the driving path |
| Moderate | 0.40 to 0.65 | | P2 Soon | Moderate outside the path, or Minor in the path |
| Critical | S >= 0.65 | | P3 Routine | Minor outside the path |

A single camera cannot measure depth, so this is an **estimate from the image**, not a
physical measurement. Weights and cut-offs live in `src/config.py` and are meant to be
calibrated against human severity labels (research question RQ2).

## Setup (one time)

Requires Python 3.10 or newer (developed on 3.11).

```bash
cd pothole-accountability-system
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then edit .env (see Telegram below)
```

The pretrained model downloads automatically the first time (about 24 MB).

**VS Code:** open this folder, press `Cmd+Shift+P` → *Python: Select Interpreter* → choose `.venv`.

## Telegram setup

1. In Telegram, open **@BotFather**, send `/newbot`, follow the steps and copy the **bot token**.
2. Put the token in `.env`: `TELEGRAM_BOT_TOKEN=123456789:AA...` and save.
3. Open your bot in Telegram, press **Start** and send it any message (e.g. "hi").
4. Find and save your chat ID automatically (also sends a test message):
   ```bash
   python scripts/get_chat_id.py
   ```
5. Restart the app. The sidebar shows **Bot connected**.

`.env` is in `.gitignore`, so your token never goes to GitHub.

## Run

```bash
source .venv/bin/activate
streamlit run app.py
```

The app opens at http://localhost:8501.

1. **Upload video** page: choose a road video (MP4/MOV/AVI/MKV) and click **Detect potholes**.
2. Results show counts by severity and priority, a table and evidence images.
   With Telegram set up, alerts arrive in your chat.
3. **Review potholes** page: filter, see why each severity was given, **Approve** real potholes,
   **Reject** false alarms (shadows, patches), add notes, resend to Telegram, download CSV.

Command line (no web page):

```bash
python -m src.cli path/to/video.mp4              # add --no-telegram to skip alerts
```

### No road video yet?

Build a demo dashcam-style video from pothole photos:

```bash
python scripts/make_demo_video.py path/to/pothole_photos demo_road.mp4
```

## Tests

```bash
pytest -q
```

Covers tracking/deduplication, severity and priority rules, Telegram formatting and an
end-to-end pipeline run.

## Settings

All thresholds are in `src/config.py` (sampling rate, confidence, tracking, severity weights).
Set `POTHOLE_DEVICE=mps` (Apple GPU) or `POTHOLE_DEVICE=0` (NVIDIA GPU) for faster processing.
To use your own trained weights, put the `.pt` file in `models/` and change `MODEL_FILE`.

## Project status

**About 80% (Review 2).** Done: video upload, frame sampling, YOLOv8-Seg detection and segmentation,
temporal association and deduplication, severity and priority, evidence images, Telegram alerts,
review dashboard, tests.

Remaining 20%: re-inspection (before/after comparison of the same road), GPS and authority
routing (NHAI / PWD / BBMP), robustness evaluation (lighting, blur, speed), severity calibration
with human labels, final report.

## Credits

- Pretrained model: [keremberke/yolov8s-pothole-segmentation](https://huggingface.co/keremberke/yolov8s-pothole-segmentation)
  (YOLOv8s, trained on the Roboflow pothole segmentation dataset)
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics), OpenCV, Streamlit
- Full plan: [docs/PRD.pdf](docs/PRD.pdf)
