"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
type Row = Record<string, any>;
export default function LocalProcessingSettings() {
  const [caps, setCaps] = useState<Row | null>(null),
    [model, setModel] = useState<Row | null>(null),
    [defaults, setDefaults] = useState<Row>({
      processing_mode: "balanced",
      output_preset: "portrait_1080",
      output_fps: 30,
    }),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true);
    try {
      const [c, m, d] = await Promise.all([
        api("/studio/capabilities"),
        api("/local-ai/status"),
        api("/studio/preferences"),
      ]);
      setCaps(c);
      setModel(m);
      setDefaults(d);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);
  return (
    <section className="panel form-body">
      <h2>Local models and rendering defaults</h2>
      <button
        className="button secondary"
        disabled={busy}
        onClick={() => void refresh()}
      >
        Check local processing
      </button>
      {model && (
        <p>
          Vision model: {model.model} ·{" "}
          {model.available ? "Available" : model.error || "Setup needed"}
        </p>
      )}
      {caps && (
        <>
          <p>
            FFmpeg: {caps.ffmpeg ? "Ready" : "Missing"} · Vision library{" "}
            {caps.opencv} · Face detector:{" "}
            {caps.face_detector ? "Available" : "Setup needed"}
          </p>
          <p>
            GPU:{" "}
            {caps.gpu.length
              ? caps.gpu
                  .map(
                    (g: Row) => `${g.name} · ${g.used_mib} / ${g.total_mib} MB`,
                  )
                  .join("; ")
              : "Measurement unavailable"}
          </p>
          <p>
            Speech: {caps.speech_device} · Encoding: {caps.encoder_policy} ·
            Free disk: {(caps.storage_free_bytes / 1024 ** 3).toFixed(1)} GB
          </p>
          <p>{caps.model_policy}</p>
        </>
      )}
      <div className="creation-options">
        <label>
          Analysis detail
          <select
            value={defaults.processing_mode}
            onChange={(e) =>
              setDefaults({ ...defaults, processing_mode: e.target.value })
            }
          >
            <option value="fast">Fast · 6 vision frames</option>
            <option value="balanced">Balanced · 12 vision frames</option>
            <option value="quality">Detailed · 24 vision frames</option>
          </select>
        </label>
        <label>
          Vertical export
          <select
            value={defaults.output_preset}
            onChange={(e) =>
              setDefaults({ ...defaults, output_preset: e.target.value })
            }
          >
            <option value="portrait_1080">1080 × 1920</option>
            <option value="portrait_720">720 × 1280</option>
          </select>
        </label>
        <label>
          Output frame rate
          <select
            value={defaults.output_fps}
            onChange={(e) =>
              setDefaults({ ...defaults, output_fps: +e.target.value })
            }
          >
            <option value={30}>30 fps</option>
            <option value={60}>60 fps</option>
          </select>
        </label>
      </div>
      <button
        className="button primary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api("/studio/preferences", {
              method: "PUT",
              body: JSON.stringify(defaults),
            });
            setMessage("Defaults saved for new automatic projects.");
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Save editing defaults
      </button>
      <p>
        Defaults apply to new clips. Existing projects keep their saved
        settings. Local model files are managed through the included setup
        tools.
      </p>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
