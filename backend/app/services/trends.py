"""Optional public YouTube research. No inference, scraping, or invented trends.

Search/video contracts: developers.google.com/youtube/data/reference/rest/v3
SQLite here is only a cache/quota ledger, not a replacement application database.
"""
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from ..config import settings


class TrendResearch:
    def __init__(self, cache_path=None, transport=None):
        self.path = Path(cache_path or settings.media_root / "research-cache.sqlite3")
        self.transport = transport

    def research(self, subject: str, platform="youtube") -> dict:
        try:
            return self._research(subject, platform)
        except (sqlite3.Error, OSError, ValueError, TypeError):
            return {"status": "unavailable", "classification": "general_relevant_suggestion", "sources": [],
                    "reason": "The local research cache or configuration is unavailable; use local content evidence."}

    def _research(self, subject: str, platform="youtube") -> dict:
        unavailable = lambda reason: {"status": "unavailable", "classification": "general_relevant_suggestion",
                                      "reason": reason, "sources": [], "subject": subject[:160]}
        key = os.getenv("YOUTUBE_DATA_API_KEY", "").strip()
        if not key:
            return unavailable("No YouTube Data API key configured; metadata will use local source evidence only.")
        subject = " ".join(subject.split())[:160]
        if not subject or subject.casefold().startswith("unidentified"):
            return unavailable("No sufficiently specific research subject was established.")
        if platform not in {"youtube", "tiktok", "instagram"}:
            return unavailable("Unsupported target platform.")
        now = datetime.now(timezone.utc)
        identity = hashlib.sha256(f"v1:{subject.casefold()}:{platform}:{now.date()}".encode()).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=15) as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, requests INTEGER NOT NULL)")
            cached = db.execute("SELECT payload FROM cache WHERE id=?", (identity,)).fetchone()
            if cached:
                return {**json.loads(cached[0]), "cached": True}
            # Reserve both requests before network work; ambiguous failures still count.
            db.execute("BEGIN IMMEDIATE")
            day = str(now.date())
            used = db.execute("SELECT requests FROM quota WHERE day=?", (day,)).fetchone()
            limit = min(90, max(2, int(os.getenv("YOUTUBE_RESEARCH_DAILY_REQUEST_LIMIT", "20"))))
            if used and used[0] + 2 > limit:
                return unavailable("The local daily research request allowance is exhausted.")
            db.execute("INSERT INTO quota VALUES (?,2) ON CONFLICT(day) DO UPDATE SET requests=requests+2", (day,))
            db.commit()
        try:
            # Google supports this system header; keep keys out of logged URLs.
            with httpx.Client(timeout=15, follow_redirects=False, trust_env=False, transport=self.transport,
                              headers={"X-Goog-Api-Key": key}) as client:
                base = "https://www.googleapis.com/youtube/v3/"
                search = client.get(base + "search", params={"part": "snippet", "type": "video",
                    "q": subject + " gaming shorts", "publishedAfter": (now-timedelta(days=30)).isoformat(), "maxResults": 10})
                search.raise_for_status()
                ids = [item.get("id", {}).get("videoId", "") for item in search.json().get("items", [])]
                ids = list(dict.fromkeys(value for value in ids if re.fullmatch(r"[A-Za-z0-9_-]{11}", value)))[:10]
                if not ids:
                    return unavailable("The bounded public search returned no usable video IDs.")
                response = client.get(base + "videos", params={"part": "snippet,statistics", "id": ",".join(ids)})
                response.raise_for_status()
                sources = []
                for item in response.json().get("items", []):
                    if item.get("id") not in ids:
                        continue
                    snippet, stats = item.get("snippet", {}), item.get("statistics", {})
                    published = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
                    if published.tzinfo is None or not now-timedelta(days=30) <= published <= now:
                        continue
                    def metric(name):
                        value = stats.get(name)
                        return int(value) if isinstance(value, (str, int)) and str(value).isdigit() else None
                    views, likes = metric("viewCount"), metric("likeCount")
                    age = max(1, (now-published).total_seconds()/86400)
                    sources.append({"url": "https://www.youtube.com/watch?v="+item["id"],
                        "title": str(snippet.get("title", ""))[:250], "description": str(snippet.get("description", ""))[:2000],
                        "published_at": published.isoformat(), "captured_at": now.isoformat(), "views": views,
                        "likes": likes, "comments": metric("commentCount"), "tags": snippet.get("tags", [])[:30],
                        "views_per_day_since_publication": round(views/age, 2) if views is not None else None,
                        "likes_per_view": round(likes/views, 6) if likes is not None and views else None})
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return unavailable("Public research failed or quota was refused. No substitute trend data was generated.")
        if not sources:
            return unavailable("No valid recent dated public sources were returned.")
        result = {"status": "available", "classification": "research_supported_suggestion", "subject": subject,
                  "captured_at": now.isoformat(), "sources": sources, "cached": False,
                  "limitation": "One public snapshot cannot verify growth, causal virality, or future performance. YouTube observations do not establish TikTok/Reels trends."}
        with sqlite3.connect(self.path, timeout=15) as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (identity, json.dumps(result)))
        return result
