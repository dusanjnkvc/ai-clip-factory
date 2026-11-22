"use client";
import { useEffect, useState } from "react";
import { api, downloadArtifact } from "@/lib/api";
import ClipEditor from "./clip-editor";
import ClipReview from "./clip-review";
import { PublishDraft } from "./social-studio";
type Row = Record<string, any>;

export default function GeneratedGallery({
  projectId,
  notify,
  onEdit,
}: {
  projectId: string;
  notify: (s: string) => void;
  onEdit?: (clip: Row) => void;
}) {
  const [clips, setClips] = useState<Row[]>([]),
    [projects, setProjects] = useState<Row[]>([]),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState(""),
    [editing, setEditing] = useState<Row | null>(null),
    [preview, setPreview] = useState<Row | null>(null),
    [error, setError] = useState("");
  const [performance, setPerformance] = useState<Row[]>([]);
  async function load() {
    const [c, p] = await Promise.all([
      api("/studio/clips"),
      api("/studio/projects"),
    ]);
    setClips(c);
    setProjects(p);
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
    api("/performance/dashboard")
      .then((r) => setPerformance(r.posts))
      .catch(() => {});
    const timer = setInterval(
      () => load().catch((e) => setError(e.message)),
      4000,
    );
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const timer = setInterval(
      () =>
        api("/performance/dashboard")
          .then((r) => setPerformance(r.posts))
          .catch(() => {}),
      60000,
    );
    return () => clearInterval(timer);
  }, []);
  const visible = clips.filter(
    (c) =>
      (!filter || c.campaign_id === filter) &&
      `${c.title} ${c.campaign_name}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const groups = Object.groupBy(visible, (c) =>
    c.campaign_name === "No Campaign"
      ? "no-campaign"
      : c.campaign_id || "no-campaign",
  );
  return (
    <div className="studio">
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {projects
        .filter(
          (p) =>
            ["queued", "processing", "failed", "blocked", "cancelled"].includes(
              p.job?.status,
            ) || p.id === projectId,
        )
        .map((p) => (
          <section key={p.id} className="panel generation-progress">
            <h3>{p.name}</h3>
            <p role="status">
              {p.job?.status} · {p.job?.progress || 0}% ·{" "}
              {p.job?.error || p.job?.stage}
            </p>
            <progress max={100} value={p.job?.progress || 0} />
            {["failed", "blocked", "cancelled"].includes(p.job?.status) && (
              <button
                className="button secondary"
                onClick={() =>
                  api(`/jobs/${p.job.id}/retry`, { method: "POST" })
                    .then(load)
                    .catch((e) => setError(e.message))
                }
              >
                Retry failed portion
              </button>
            )}
            {["queued", "processing"].includes(p.job?.status) && (
              <button
                className="button secondary"
                onClick={() =>
                  api(`/auto/jobs/${p.job.id}/cancel`, { method: "POST" })
                    .then(load)
                    .catch((e) => setError(e.message))
                }
              >
                Cancel
              </button>
            )}
          </section>
        ))}
      <div className="gallery-filters">
        <label>
          Search clips
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Game, title or campaign"
          />
        </label>
        <label>
          Campaign
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All campaigns</option>
            {Array.from(
              new Map(clips.map((c) => [c.campaign_id, c])).values(),
            ).map((c) => (
              <option key={c.campaign_id} value={c.campaign_id}>
                {c.campaign_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!clips.length && (
        <section className="panel empty">
          <h2>Your finished clips appear here</h2>
          <p>Generate clips from an authorized gaming video to get started.</p>
        </section>
      )}
      {Object.entries(groups).map(([group, items]) => (
        <details key={group} open className="campaign-group">
          <summary>
            {items?.[0]?.campaign_name || "No Campaign"}{" "}
            <span>{items?.length} clips</span>
          </summary>
          <div className="generated-grid">
            {items?.map((c) => {
              const scores = Object.values(c.evaluation?.platforms || {})
                .map((s: any) => s.score)
                .filter(
                  (s: any) => typeof s === "number" && Number.isFinite(s),
                );
              return (
                <article key={c.id} className="panel generated-card">
                  <button
                    className="gallery-preview"
                    aria-label={`Preview ${c.title}`}
                    onClick={() => setPreview(c)}
                  >
                    <video
                      src={c.preview_url}
                      preload="metadata"
                      muted
                      playsInline
                    />
                    <span>
                      Preview · {Number(c.media_info?.duration || 0).toFixed(1)}
                      s
                    </span>
                  </button>
                  <div className="generated-card-body">
                    <h3>{c.title}</h3>
                    <p>
                      {c.campaign_name} ·{" "}
                      {c.destination === "both"
                        ? "YouTube + TikTok"
                        : c.destination}
                    </p>
                    <p>
                      {c.editing_style ||
                        c.plan?.edit_dna?.visual_effects ||
                        "Saved edit"}
                    </p>
                    <div className="clip-badges">
                      <span>{c.compliance?.status}</span>
                      <span>
                        {c.decision} · v{c.current_version}
                      </span>
                      <span>
                        Potential{" "}
                        {scores.length
                          ? Math.max(...scores) + "/100"
                          : "unavailable"}
                      </span>
                    </div>
                    <small>Editorial heuristic; not guaranteed views.</small>
                    <div className="button-row">
                      <button
                        className="button secondary"
                        onClick={() => setPreview(c)}
                      >
                        Review / approve
                      </button>
                      <button
                        className="button secondary"
                        onClick={() => (onEdit ? onEdit(c) : setEditing(c))}
                      >
                        Edit Clip
                      </button>
                      <button
                        className="button secondary"
                        onClick={() =>
                          void downloadArtifact(`/clips/${c.id}/download`)
                        }
                      >
                        Download
                      </button>
                      <button
                        className="button secondary"
                        onClick={() =>
                          api(`/editor/drafts/${c.id}/duplicate`, {
                            method: "POST",
                          })
                            .then(() => {
                              notify(
                                "Independent editable copy saved. The original is preserved.",
                              );
                              return load();
                            })
                            .catch((e) => setError(e.message))
                        }
                      >
                        Duplicate
                      </button>
                      <PublishDraft draft={c} notify={notify} />
                    </div>
                    {performance
                      .filter((p) => p.clip_id === c.id)
                      .map((p) => (
                        <div key={p.post_id} className="clip-kpis">
                          <strong>{p.platform}</strong>
                          <p>
                            Views {p.lifetime?.views ?? "Unavailable"} · Likes{" "}
                            {p.lifetime?.likes ?? "Unavailable"} · Comments{" "}
                            {p.lifetime?.comments ?? "Unavailable"}
                          </p>
                          <p>
                            Available engagement{" "}
                            {p.engagement_rate == null
                              ? "Unavailable"
                              : (p.engagement_rate * 100).toFixed(2) + "%"}
                          </p>
                          <a href={p.url} target="_blank" rel="noreferrer">
                            View published video
                          </a>
                        </div>
                      ))}
                    {c.publishing_jobs?.map((j: Row) => (
                      <p key={j.id}>
                        {j.platform}: {j.status} · v{j.version}
                        {j.error ? " · " + j.error : ""}
                      </p>
                    ))}
                    {!c.publications.length && !c.publishing_jobs?.length && (
                      <small>Not published</small>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </details>
      ))}
      {editing && (
        <ClipEditor
          draft={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            await load();
            notify("Saved. Review the new version before publishing.");
          }}
        />
      )}
      {preview && (
        <div className="modal-backdrop">
          <div
            className="modal form-body studio preview-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Clip preview"
          >
            <button
              className="button secondary"
              onClick={() => setPreview(null)}
            >
              Close preview
            </button>
            <h2>{preview.title}</h2>
            <video src={preview.preview_url} controls autoPlay playsInline />
            {["youtube", "tiktok"].map((p) => {
              const b = preview.metadata[p],
                m = b.variants[b.recommended_index];
              return (
                <div key={p}>
                  <h3>{p}</h3>
                  <strong>{m.title}</strong>
                  <p>{p === "tiktok" ? m.caption : m.description}</p>
                  <p>{m.hashtags.join(" ")}</p>
                </div>
              );
            })}
            <ClipReview
              key={preview.id + ":" + preview.current_version}
              clip={preview}
              onSaved={async () => {
                await load();
                const all = await api("/studio/clips");
                setPreview(all.find((c: Row) => c.id === preview.id));
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
