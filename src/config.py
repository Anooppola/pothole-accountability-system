"""All settings in one place. Change values here, not inside the modules."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---------- Paths ----------
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EVIDENCE_DIR = DATA_DIR / "evidence"
DB_PATH = DATA_DIR / "potholes.db"
MODEL_DIR = ROOT / "models"

for _d in (UPLOAD_DIR, EVIDENCE_DIR, MODEL_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------- Model ----------
# Pretrained YOLOv8s pothole segmentation model (Hugging Face).
# To use your own trained weights, put the file in models/ and change MODEL_FILE.
MODEL_REPO = "keremberke/yolov8s-pothole-segmentation"
MODEL_REPO_FILE = "best.pt"
MODEL_FILE = MODEL_DIR / "pothole-yolov8s-seg.pt"
DEVICE = os.getenv("POTHOLE_DEVICE", "cpu")  # "cpu", "mps" (Apple GPU) or "0" (NVIDIA GPU)
IMG_SIZE = 640

# ---------- Video processing ----------
SAMPLE_FPS = 2.0          # frames analysed per second of video
BLUR_THRESHOLD = 60.0     # variance of Laplacian; frames below this are skipped as blurry
CONF_THRESHOLD = 0.35     # minimum detection confidence
MIN_MASK_AREA = 0.0015    # ignore masks smaller than 0.15% of the frame (noise)
ROI_TOP = 0.30            # ignore detections whose centre is in the top 30% (sky, buildings)

# ---------- Tracking / deduplication ----------
TRACK_IOU = 0.15          # box overlap needed to continue a track
TRACK_MAX_GAP_S = 1.5     # a track ends if the pothole is unseen for this long (seconds)
MERGE_GAP_S = 2.0         # tracks this close in time ...
MERGE_HIST_SIM = 0.80     # ... and this similar in appearance are merged into one pothole
MIN_HITS = 2              # a pothole must be seen in at least this many frames ...
SINGLE_HIT_CONF = 0.60    # ... unless one detection is at least this confident

# ---------- Severity (Estimated Visual Severity Proxy) ----------
SEVERITY_WEIGHTS = {"area": 0.45, "dark": 0.20, "irregular": 0.15, "persist": 0.20}
AREA_REF = 0.08           # corrected area that counts as "very large" (score 1.0)
PERSIST_REF = 6           # frames seen that counts as "very persistent" (score 1.0)
SEVERITY_LEVELS = [       # (upper score bound, name)
    (0.33, "Minor"),
    (0.66, "Moderate"),
    (1.01, "Critical"),
]
PRIORITY_NAMES = {1: "P1 Urgent", 2: "P2 Soon", 3: "P3 Routine"}

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_PLACEHOLDERS = {"", "your-bot-token-from-BotFather", "your-chat-id"}


def telegram_configured() -> bool:
    return (
        TELEGRAM_BOT_TOKEN not in TELEGRAM_PLACEHOLDERS
        and TELEGRAM_CHAT_ID not in TELEGRAM_PLACEHOLDERS
    )
