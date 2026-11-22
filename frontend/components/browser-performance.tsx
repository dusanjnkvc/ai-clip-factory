"use client";
import { useState } from "react";
type Row = Record<string, any>;
export default function BrowserPerformance({ analytics }: { analytics: Row }) {
  const [platform, setPlatform] = useState("all");
  const posts = (analytics.posts || []).filter(
      (p: Row) => platform === "all" || p.platform === platform,
    ),
    observed = posts.filter((p: Row) => p.analytics);
  const views = observed.reduce(
    (n: number, p: Row) => n + Number(p.analytics.reported_views || 0),
    0,
  );
  return (
    <div className="form-body">
      <div className="notice muted">
        Only actual recorded publication observations appear here. Connect
        authorized accounts in the local service edition for automatic
        synchronization.
      </div>
      <div className="metric-grid">
        {[
          ["Published videos", posts.length],
          ["Observed views", observed.length ? views : "Unavailable"],
          ["Likes", "Unavailable"],
          ["Followers / subscribers", "Unavailable"],
        ].map(([label, value]) => (
          <div className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <section className="panel form-body">
        <label>
          Performance platform
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="all">All platforms</option>
            <option value="youtube">YouTube</option>
            <option value="tiktok">TikTok</option>
          </select>
        </label>
        <h2>Recorded publications</h2>
        {posts.length ? (
          posts.map((p: Row) => (
            <article className="source-row" key={p.id}>
              <div>
                <strong>{p.title || p.platform}</strong>
                <small>
                  {p.platform} · {p.published_at}
                </small>
                <p>Views {p.analytics?.reported_views ?? "Unavailable"}</p>
              </div>
              <a href={p.url} target="_blank" rel="noreferrer">
                Open actual post
              </a>
            </article>
          ))
        ) : (
          <p>No publication data yet. No results are simulated.</p>
        )}
      </section>
    </div>
  );
}
