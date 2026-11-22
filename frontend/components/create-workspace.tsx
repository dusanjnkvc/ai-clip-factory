"use client";
import { useEffect, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import CampaignManager from "./campaign-manager";
const AdvancedEditor = dynamic(() => import("./advanced-editor"), {
  ssr: false,
});
type Row = Record<string, any>;
export default function CreateWorkspace({
  automatic,
  manual,
  editing,
  onBack,
  onQueued,
  notify,
}: {
  automatic: ReactNode;
  manual?: ReactNode;
  editing?: Row | null;
  onBack: () => void;
  onQueued: () => void;
  notify: (s: string) => void;
}) {
  const [mode, setMode] = useState("automatic"),
    [clips, setClips] = useState<Row[]>([]),
    [current, setCurrent] = useState<Row | null>(editing || null),
    [error, setError] = useState("");
  useEffect(() => {
    api("/clips")
      .then(setClips)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (editing) {
      setCurrent(editing);
      setMode("manual");
    }
  }, [editing?.id, editing?.current_version]);
  return (
    <div className="create-workspace">
      <div
        className="segmented editor-mode-switch"
        role="group"
        aria-label="Creation mode"
      >
        <button
          type="button"
          aria-pressed={mode === "automatic"}
          className={mode === "automatic" ? "selected" : ""}
          onClick={() => setMode("automatic")}
        >
          Automatic AI Mode
        </button>
        <button
          type="button"
          aria-pressed={mode === "manual"}
          className={mode === "manual" ? "selected" : ""}
          onClick={() => setMode("manual")}
        >
          Advanced Manual Mode
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      <CampaignManager />
      <div hidden={mode !== "automatic"}>{automatic}</div>
      <div hidden={mode !== "manual"}>
        {current ? (
          <AdvancedEditor
            key={current.id + ":" + current.current_version}
            clip={current}
            onClose={onBack}
            onQueued={onQueued}
            notify={notify}
          />
        ) : (
          <>
            <section className="panel form-body">
              <h2>Advanced manual editor</h2>
              <p>
                Load an existing clip to edit its text, subtitles, logos, audio
                and timeline. Originals and cached AI analysis are preserved.
              </p>
              <label>
                Editable clip
                <select
                  defaultValue=""
                  onChange={async (e) => {
                    if (e.target.value) {
                      try {
                        setCurrent(await api(`/clips/${e.target.value}`));
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }
                  }}
                >
                  <option value="">Choose a generated clip</option>
                  {clips.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title} · v{c.current_version}
                    </option>
                  ))}
                </select>
              </label>
            </section>
            {manual}
          </>
        )}
      </div>
    </div>
  );
}
