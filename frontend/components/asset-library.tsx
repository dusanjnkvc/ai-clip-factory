"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { prepareEditorImage } from "@/lib/editor-assets";
type Row = Record<string, any>;
export default function AssetLibrary() {
  const [assets, setAssets] = useState<Row[]>([]),
    [templates, setTemplates] = useState<Row[]>([]),
    [filter, setFilter] = useState("all"),
    [query, setQuery] = useState(""),
    [error, setError] = useState("");
  async function load() {
    const [a, t] = await Promise.all([
      api("/editor/assets"),
      api("/editor/templates"),
    ]);
    setAssets(a);
    setTemplates(t);
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  return (
    <section className="panel form-body">
      <h2>Branding, audio & reusable designs</h2>
      <p>
        Shared with Create Clips. Upload only assets you have permission to use.
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="generation-settings">
        <label>
          Search library
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label>
          Asset category
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All assets</option>
            <option value="image">Images & logos</option>
            <option value="audio">Audio</option>
            <option value="video">Video layers</option>
            <option value="template">Reusable designs</option>
          </select>
        </label>
      </div>
      <label className="button secondary file-button">
        Upload image, logo or audio
        <input
          type="file"
          accept=".png,.jpg,.jpeg,.webp,.svg,.mp3,.wav,.m4a,.ogg,.flac"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f)
              try {
                const form = new FormData();
                form.set(
                  "file",
                  /\.(png|jpe?g|webp|svg)$/i.test(f.name)
                    ? await prepareEditorImage(f)
                    : f,
                );
                await api("/editor/assets", { method: "POST", body: form });
                await load();
              } catch (e) {
                setError((e as Error).message);
              }
          }}
        />
      </label>
      <div className="editor-library-grid">
        {assets
          .filter(
            (a) =>
              (filter === "all" || filter === a.kind) &&
              a.name.toLowerCase().includes(query.toLowerCase()),
          )
          .map((a) => (
            <article key={a.id}>
              {a.kind === "image" ? (
                <img src={a.url} alt={a.name} />
              ) : a.kind === "audio" ? (
                <audio controls src={a.url} />
              ) : (
                <video controls src={a.url} preload="metadata" />
              )}
              <input
                aria-label={`Rename ${a.name}`}
                defaultValue={a.name}
                onBlur={async (e) => {
                  if (e.target.value !== a.name)
                    try {
                      await api(`/editor/assets/${a.id}`, {
                        method: "PATCH",
                        body: JSON.stringify({ name: e.target.value }),
                      });
                      await load();
                    } catch (e) {
                      setError((e as Error).message);
                    }
                }}
              />
              <small>
                {a.kind} · {(a.size_bytes / 1024 / 1024).toFixed(1)} MB
              </small>
              <button
                className="button secondary"
                onClick={async () => {
                  try {
                    await api(`/editor/assets/${a.id}`, { method: "DELETE" });
                    await load();
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                Archive unused asset
              </button>
            </article>
          ))}
        {(filter === "all" || filter === "template") &&
          templates
            .filter((t) => t.name.toLowerCase().includes(query.toLowerCase()))
            .map((t) => (
              <article key={t.id}>
                <strong>{t.name}</strong>
                <p>{t.editor.layers.length} layers · reusable design</p>
                <small>Apply from Advanced Manual Mode in Create Clips.</small>
              </article>
            ))}
      </div>
    </section>
  );
}
