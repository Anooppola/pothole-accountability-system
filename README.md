# AI-Powered Pothole Detection and Road Accountability System

Final-year project, Department of CSE (Data Science), Dayananda Sagar University.
Team: Anoop Pola (ENG23DS0003), Amrutalakshmi H K (ENG24DS3001). Guide: Prof. Manjula M.

Upload a pre-recorded road video. The system detects and segments potholes with YOLOv8-Seg,
merges repeated detections into unique potholes, rates each one by severity
(Minor / Moderate / Critical) and priority (P1 Urgent / P2 Soon / P3 Routine),
sends an alert with evidence to Telegram, and lists everything on a Review page.

## Status

Work in progress (Review 2 target: 80%).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your Telegram bot token and chat ID
streamlit run app.py
```
