"use client";
import { useState, type ReactNode } from "react";
import { api } from "@/lib/api";
type Row = Record<string, any>;
export default function BrowserClipGallery({
  clips,
  campaigns,
  renderClip,
  onRefresh,
  notify,
}: {
  clips: Row[];
  campaigns: Row[];
  renderClip: (clip: Row) => ReactNode;
  onRefresh: () => void;
  notify: (text: string) => void;
}) {
  const [query, setQuery] = useState(""),
    [campaign, setCampaign] = useState(""),
    [sort, setSort] = useState("newest"),
    [status, setStatus] = useState("");
  const name = (id: string) =>
    campaigns.find((c) => c.id === id)?.name || "No campaign";
  const visible = clips
    .filter(
      (c) =>
        (!campaign || c.campaign_id === campaign) &&
        (!status || c.compliance?.status === status) &&
        `${c.title} ${name(c.campaign_id)}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "title"
        ? a.title.localeCompare(b.title)
        : sort === "duration"
          ? Number(b.media_info.duration) - Number(a.media_info.duration)
          : Date.parse(b.created_at) - Date.parse(a.created_at),
    );
  const groups = Object.groupBy(visible, (c) => c.campaign_id || "none");
  return (
    <>
      <div className="gallery-filters">
        <label>
          Search clips
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label>
          Campaign
          <select
            value={campaign}
            onChange={(e) => setCampaign(e.target.value)}
          >
            <option value="">All campaigns</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Review status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="PASS">Passed</option>
            <option value="REVIEW_REQUIRED">Needs review</option>
            <option value="FAIL">Needs corrections</option>
          </select>
        </label>
        <label>
          Sort clips
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="newest">Newest first</option>
            <option value="title">Title</option>
            <option value="duration">Duration</option>
          </select>
        </label>
      </div>
      {!visible.length && <p>No clips match these filters.</p>}
      {Object.entries(groups).map(([id, items]) => (
        <details key={id} className="campaign-group" open>
          <summary>
            {name(id)} · {items?.length} clips
          </summary>
          <div className="clip-grid">
            {items?.map((c) => (
              <article key={c.id}>
                {renderClip(c)}
                <button
                  className="button secondary"
                  onClick={() =>
                    api(`/editor/drafts/${c.id}/duplicate`, { method: "POST" })
                      .then(() => {
                        onRefresh();
                        notify(
                          "Editable copy saved. The original is preserved.",
                        );
                      })
                      .catch((e) => notify(e.message))
                  }
                >
                  Duplicate editable project
                </button>
              </article>
            ))}
          </div>
        </details>
      ))}
    </>
  );
}
