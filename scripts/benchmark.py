"""Measure a real queued local render against a running API.

Create/review a campaign and upload authorized media in the native local edition
first. Free local mode needs no login. The default is one manually selected clip;
no AI provider is called. Hosted jobs require --allow-hosted. Optional hosted
passwords use a hidden prompt or BENCHMARK_PASSWORD, never a CLI argument.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import json
import math
import os
from pathlib import Path
import sys
import time

import httpx


class SetupError(RuntimeError):
    """Safe locally generated configuration message, without request data."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--origin", help="Allowed frontend origin; defaults to base URL")
    parser.add_argument("--email", help="Optional account email for a server that requires authentication")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--mode", choices=["fast", "quality"], default="fast")
    parser.add_argument("--clips", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--start", type=float, default=0, help="Manual source start in seconds")
    parser.add_argument("--end", type=float, help="Manual source end; blank uses up to 30 seconds from --start")
    parser.add_argument("--title", default="Local render benchmark", help="User-authored clip title")
    parser.add_argument("--description", default="User-selected local rendering benchmark.")
    parser.add_argument("--subtitles-file", type=Path, help="Optional source-timed SRT/VTT file to upload before timing")
    parser.add_argument("--allow-hosted", action="store_true", help="Explicitly allow a configured hosted job that may incur charges")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--download-first", action="store_true", help="Download and fully decode the first rendered clip")
    parser.add_argument("--output-dir", type=Path, default=Path(".runtime/benchmarks"))
    args = parser.parse_args()
    if args.timeout < 1 or args.poll_seconds < .5:
        parser.error("Use a positive timeout and a poll interval of at least 0.5 seconds.")
    if not math.isfinite(args.start) or args.start < 0 or args.end is not None and (not math.isfinite(args.end) or args.end <= args.start):
        parser.error("The manual source range must start at zero or later and end after its start.")
    if args.subtitles_file and args.subtitles_file.suffix.lower() not in {".srt", ".vtt"}:
        parser.error("Use an SRT or VTT subtitle file.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    password = ""
    base_url = args.base_url.rstrip("/")
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "campaign_id": args.campaign_id,
        "source_id": args.source_id,
        "mode": args.mode,
        "requested_clips": args.clips,
        "measurement_starts": "Before POST /api/jobs; excludes campaign analysis and source upload",
        "first_rendered_seconds": None,
        "first_compliant_seconds": None,
        "three_compliant_seconds": None,
        "five_compliant_seconds": None,
        "download_verified": False,
    }
    started = time.monotonic()
    final_status = "not_started"
    try:
        with httpx.Client(base_url=base_url, headers={"Origin": args.origin or base_url}, timeout=60, follow_redirects=True) as client:
            session = client.get("/api/auth/me")
            if session.status_code == 401:
                if not args.email:
                    raise SetupError("This optional server requires authentication; supply --email. The default free local workspace does not require it.")
                password = os.getenv("BENCHMARK_PASSWORD") or getpass.getpass("Account password: ")
                response = client.post("/api/auth/login", json={"email": args.email, "password": password})
                if response.status_code != 200:
                    raise RuntimeError(f"Login failed with HTTP {response.status_code}; check the account and frontend origin.")
            elif session.status_code != 200:
                raise SetupError("The benchmark requires the native local API/worker edition. For GitHub Pages, measure rendering in its browser UI.")
            # Never retain or log the password or cookie values.
            password = ""
            settings_response = client.get("/api/settings")
            settings_response.raise_for_status()
            free_mode = settings_response.json().get("free_mode", True)
            report["processing_provider"] = "local_manual" if free_mode else "hosted"
            if not free_mode and not args.allow_hosted:
                raise SetupError("This server has hosted processing enabled. The benchmark will not start a paid operation without --allow-hosted.")
            if free_mode and args.clips != 1:
                raise SetupError("The local benchmark uses one manually selected clip; use --clips 1.")
            if args.subtitles_file:
                with args.subtitles_file.open("rb") as subtitles:
                    subtitle_response = client.post(f"/api/sources/{args.source_id}/subtitles", files={"file": (args.subtitles_file.name, subtitles, "text/plain")})
                subtitle_response.raise_for_status()
            payload = {"campaign_id": args.campaign_id, "source_id": args.source_id, "mode": args.mode, "clip_count": args.clips}
            if free_mode:
                payload["manual_selection"] = {"start": args.start, "end": args.end, "title": args.title, "description": args.description, "crop_x": .5, "crop_y": .5, "zoom": 1, "subtitle_style": "clean", "show_hook": False}
                report["manual_selection"] = {"start": args.start, "end": args.end}
            started = time.monotonic()
            report["started_at"] = datetime.now(timezone.utc).isoformat()
            response = client.post("/api/jobs", json=payload)
            response.raise_for_status()
            job_id = response.json()["id"]
            report["job_id"] = job_id
            print(f"Measuring job {job_id}; {args.clips} clip(s), {args.mode} mode.", flush=True)
            previous_state = None
            first_clip_id = None
            while time.monotonic() - started < args.timeout:
                job_response = client.get("/api/jobs")
                job_response.raise_for_status()
                job = next((row for row in job_response.json() if row["id"] == job_id), None)
                if job is None:
                    raise RuntimeError("The queued job disappeared from this account.")
                clips_response = client.get("/api/clips")
                clips_response.raise_for_status()
                clips = [row for row in clips_response.json() if row.get("job_id") == job_id]
                elapsed = round(time.monotonic() - started, 3)
                compliant = [row for row in clips if row.get("compliance", {}).get("status") == "PASS"]
                if clips and report["first_rendered_seconds"] is None:
                    report["first_rendered_seconds"] = elapsed
                    first_clip_id = clips[0]["id"]
                if compliant and report["first_compliant_seconds"] is None:
                    report["first_compliant_seconds"] = elapsed
                for count, key in [(3, "three_compliant_seconds"), (5, "five_compliant_seconds")]:
                    if len(compliant) >= count and report[key] is None:
                        report[key] = elapsed
                state = (job["status"], job.get("stage"), len(clips), len(compliant))
                if state != previous_state:
                    print(f"{elapsed:.1f}s: {job['status']} · {job.get('stage', '')} · {len(clips)} rendered / {len(compliant)} PASS", flush=True)
                    previous_state = state
                if job["status"] in {"completed", "failed", "blocked"}:
                    final_status = job["status"]
                    report["job_error"] = job.get("error")
                    report["worker_first_clip_seconds"] = job.get("first_clip_seconds")
                    break
                time.sleep(args.poll_seconds)
            else:
                final_status = "benchmark_timeout"
            report["generation_observation_seconds"] = round(time.monotonic() - started, 3)
            if final_status == "completed" and report["first_rendered_seconds"] is None:
                raise SetupError("The job completed without an observable rendered clip. This is not a successful render benchmark.")
            # Download after timing the batch so verification does not delay polling.
            # Refresh the clip list because a long batch may outlive signed URLs.
            if args.download_first and first_clip_id:
                response = client.get("/api/clips")
                response.raise_for_status()
                clip = next(row for row in response.json() if row["id"] == first_clip_id)
                download_url = clip.get("download_url") or clip.get("preview_url")
                if not download_url:
                    raise RuntimeError("The first rendered clip has no download URL.")
                target = args.output_dir / f"{job_id}-first.mp4"
                with client.stream("GET", download_url, timeout=180) as stream:
                    stream.raise_for_status()
                    size = 0
                    with target.open("wb") as output:
                        for block in stream.iter_bytes():
                            size += len(block)
                            if size > 1024 * 1024 * 1024:
                                raise RuntimeError("Benchmark download exceeded the 1 GiB limit.")
                            output.write(block)
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
                from app.services.media import ffmpeg_binary, probe_media, run_media, safe_input_options
                media = probe_media(target)
                run_media([ffmpeg_binary(), "-v", "error", *safe_input_options(target), "-i", str(target.resolve()), "-f", "null", "-"], timeout=600)
                report["download_verified"] = True
                report["download_media"] = media
    except (httpx.HTTPError, RuntimeError, ValueError, OSError) as exc:
        final_status = "benchmark_error"
        # Avoid logging request headers, cookies, signed URLs, or response bodies.
        report["benchmark_error"] = type(exc).__name__
        detail = str(exc) if isinstance(exc, SetupError) else f"{type(exc).__name__}. Inspect application logs for details."
        print(f"Benchmark failed: {detail}", file=sys.stderr)
    finally:
        report["status"] = final_status
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        target = args.output_dir / f"benchmark-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved measurements to {target}")
    return 0 if final_status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
