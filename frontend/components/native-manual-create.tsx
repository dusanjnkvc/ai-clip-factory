"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
type Row = Record<string, any>;
export default function NativeManualCreate({
  onQueued,
}: {
  onQueued: () => void;
}) {
  const [sources, setSources] = useState<Row[]>([]),
    [campaigns, setCampaigns] = useState<Row[]>([]),
    [source, setSource] = useState(""),
    [campaign, setCampaign] = useState(""),
    [start, setStart] = useState(0),
    [end, setEnd] = useState(10),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    Promise.all([api("/sources"), api("/campaigns")])
      .then(([s, c]) => {
        setSources(s);
        setCampaigns(c);
      })
      .catch((e) => setError(e.message));
  }, []);
  return (
    <section className="panel form-body">
      <h3>Start a manual clip from your library</h3>
      <p>
        Import new footage in Automatic AI Mode first. Manual clipping uses the
        same source, clip plans and versioned editor.
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        Original video
        <select
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            setEnd(
              Math.min(
                10,
                sources.find((s) => s.id === e.target.value)?.media_info
                  .duration || 10,
              ),
            );
          }}
        >
          <option value="">Select an authorized source</option>
          {sources.map((s) => (
            <option value={s.id} key={s.id}>
              {s.filename}
            </option>
          ))}
        </select>
      </label>
      <label>
        Campaign
        <select value={campaign} onChange={(e) => setCampaign(e.target.value)}>
          <option value="">General clipping</option>
          {campaigns.map((c) => (
            <option value={c.id} key={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <div className="generation-settings">
        <label>
          Source start
          <input
            type="number"
            min={0}
            step={0.1}
            value={start}
            onChange={(e) => setStart(+e.target.value)}
          />
        </label>
        <label>
          Source end
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={end}
            onChange={(e) => setEnd(+e.target.value)}
          />
        </label>
      </div>
      <button
        className="button primary"
        disabled={!source || busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            let cid = campaign;
            if (!cid)
              cid = (
                await api("/campaigns", {
                  method: "POST",
                  body: JSON.stringify({
                    name: "General manual clips",
                    brief:
                      "General authorized clipping. No external campaign rules supplied.",
                  }),
                })
              ).id;
            await api("/jobs", {
              method: "POST",
              body: JSON.stringify({
                source_id: source,
                campaign_id: cid,
                clip_count: 1,
                mode: "fast",
                manual_selection: { start, end },
              }),
            });
            onQueued();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Preparing…" : "Create editable clip"}
      </button>
    </section>
  );
}
