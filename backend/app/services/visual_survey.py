"""Bounded source-wide motion survey and conservative persistent face proposals.

These measurements do not establish kills, victories, emotions or identity.
Only a stable, repeatedly observed corner face can propose a facecam crop.
"""
from __future__ import annotations

import math
import subprocess
import threading
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .editor_schema import CropBox
from . import media
from .ollama_provider import InferenceCancelled

SURVEY_VERSION = "motion-corner-face-v1"




class MotionSample(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    timestamp: float = Field(ge=0)
    change: float = Field(ge=0, le=1)


class VisualSurvey(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: str = SURVEY_VERSION
    interval: float = Field(gt=0)
    samples: list[MotionSample] = Field(max_length=1200)
    face_samples: int = Field(ge=0)
    facecam: CropBox | None = None
    face_support: float = Field(ge=0, le=1)
    limitations: list[str]


def persistent_face(detections: list[list[tuple]], sample_count: int):
    """Cluster normalized face boxes by position; reject transient/larger faces."""
    import numpy as np
    tracks: list[list[tuple]] = []
    for index, boxes in enumerate(detections):
        assigned = set()
        for x, y, w, h in boxes:
            cx, cy = x + w / 2, y + h / 2
            if not (.025 <= w <= .25 and .04 <= h <= .4):
                continue
            if not ((cx < .3 or cx > .7) and (cy < .4 or cy > .6)):
                continue
            best = None
            for n, track in enumerate(tracks):
                if n in assigned:
                    continue
                median = np.median([item[1:] for item in track], axis=0)
                distance = math.hypot(cx - (median[0] + median[2] / 2), cy - (median[1] + median[3] / 2))
                if distance < .055 and .6 < w / median[2] < 1.7:
                    best = n
                    break
            if best is None:
                tracks.append([])
                best = len(tracks) - 1
            tracks[best].append((index, x, y, w, h))
            assigned.add(best)
    if not tracks or sample_count < 6:
        return None, 0.0
    track = max(tracks, key=len)
    support = len(track) / sample_count
    span = (track[-1][0] - track[0][0]) / max(1, sample_count - 1)
    if len(track) < 5 or support < .5 or span < .6:
        return None, support
    values = np.array([item[1:] for item in track])
    if np.max(np.std(values[:, :2], axis=0)) > .025:
        return None, support
    x, y, w, h = np.median(values, axis=0)
    # Include head/shoulder context. This is a proposal, not overlay-border detection.
    left, top = max(0, x - .65 * w), max(0, y - .45 * h)
    right, bottom = min(1, x + 1.65 * w), min(1, y + 1.8 * h)
    return {"x": float(left), "y": float(top), "width": float(right-left), "height": float(bottom-top)}, support


def survey_video(path: Path, duration: float, cancel=None) -> dict:
    import cv2
    import numpy as np
    interval = max(1.0, duration / 1199)
    width, height = 640, 360
    classifier = getattr(cv2, 'CascadeClassifier', None)
    detector = classifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml") if classifier else None
    if detector is not None and detector.empty():
        detector = None
    command = [media.ffmpeg_binary(), "-hide_banner", "-loglevel", "error", *media.safe_input_options(path), "-i", str(path),
               "-an", "-vf", f"fps=1/{interval:.8f},scale={width}:{height},format=gray", "-frames:v", "1200", "-threads", "2", "-f", "rawvideo", "pipe:1"]
    stopped, interrupted = threading.Event(), []
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        def watch():
            import time
            deadline = time.monotonic() + max(120, min(1800, duration * 2))
            while not stopped.wait(.1):
                cancelled = cancel.is_set() if hasattr(cancel, "is_set") else cancel() if callable(cancel) else False
                if cancelled or time.monotonic() > deadline:
                    interrupted.append("cancelled" if cancelled else "timeout")
                    process.terminate()
                    return
        watcher = threading.Thread(target=watch, name="acf-visual-survey", daemon=True)
        watcher.start()
        samples, detections, previous = [], [], None
        try:
            while len(samples) < 1200:
                raw = process.stdout.read(width * height)
                if not raw:
                    break
                if len(raw) != width * height:
                    raise media.PipelineError("Incomplete visual survey frame")
                gray = np.frombuffer(raw, np.uint8).reshape(height, width)
                small = cv2.resize(gray, (80, 45))
                change = float(np.abs(small.astype(np.float32)-previous).mean()/255) if previous is not None else 0.0
                timestamp = min(duration-.001, len(samples)*interval+interval/2)
                samples.append({"timestamp": max(0, timestamp), "change": change})
                previous = small.astype(np.float32)
                # Bound CPU face detection to at most 300 evenly distributed samples.
                if detector is not None and (len(samples)-1) % max(1, math.ceil(duration/interval/300)) == 0:
                    boxes = detector.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6, minSize=(20, 20))
                    detections.append([(x/width, y/height, w/width, h/height) for x, y, w, h in boxes])
            code = process.wait(timeout=10)
            if interrupted:
                if interrupted[0] == "cancelled":
                    raise InferenceCancelled("Visual survey cancelled; original media preserved")
                raise media.PipelineError("Visual survey exceeded its time limit")
            if code or not samples:
                raise media.PipelineError("FFmpeg could not measure the visual survey")
        finally:
            stopped.set()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            process.stdout.close()
            watcher.join(timeout=1)
    facecam, support = persistent_face(detections, len(detections))
    return VisualSurvey(interval=interval, samples=samples, face_samples=len(detections), facecam=facecam, face_support=support,
                        limitations=(["Face detection unavailable in this OpenCV build; install requirements-local-ai.txt. Motion survey remains available."] if detector is None else []) + ["Downscaled periodic motion samples are not semantic event detections and can miss brief events.",
                                     "A persistent corner-face crop is an uncertain proposal; it can mistake game characters for a facecam and miss small, moving or obscured webcams."]).model_dump()
