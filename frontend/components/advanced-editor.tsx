"use client";

import { useEffect, useRef, useState, type PointerEvent } from "react";

import { Player, type PlayerRef } from "@remotion/player";

import { api } from "@/lib/api";

import {
  ClipComposition,
  type ClipCompositionProps,
} from "../remotion/ClipComposition";

import {
  editorForPlan,
  newLayer,
  captionPresets,
  validateEditor,
  planDuration,
  applyTemplate,
  type Layer,
  type EditorState,
} from "@/lib/editor-project";

import { prepareEditorImage } from "@/lib/editor-assets";
import EditorMetadata from "./editor-metadata";

type Row = Record<string, any>;

type Snapshot = { plan: Row; metadata: Row };

const browserMode = process.env.NEXT_PUBLIC_BROWSER_MODE === "true";

const bound = (n: number, min: number, max: number) =>
  Math.min(max, Math.max(min, n));

export default function AdvancedEditor({
  clip,
  onClose,
  onQueued,
  notify,
}: {
  clip: Row;
  onClose: () => void;
  onQueued: () => void;
  notify: (s: string) => void;
}) {
  const [state, setState] = useState<Snapshot>({
    plan: { ...structuredClone(clip.plan), editor: editorForPlan(clip.plan) },
    metadata: structuredClone(clip.metadata),
  });

  const [selected, setSelected] = useState("source"),
    [assets, setAssets] = useState<Row[]>([]),
    [templates, setTemplates] = useState<Row[]>([]),
    [sources, setSources] = useState<Row[]>([]),
    [props, setProps] = useState<ClipCompositionProps | null>(null);

  const [ready, setReady] = useState(false),
    [message, setMessage] = useState("Loading editable project…"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [time, setTime] = useState(0),
    [zoom, setZoom] = useState(1),
    [snap, setSnap] = useState(true),
    [past, setPast] = useState<Snapshot[]>([]),
    [future, setFuture] = useState<Snapshot[]>([]),
    [templateName, setTemplateName] = useState(""),
    [versions, setVersions] = useState<Row[]>([]);

  const player = useRef<PlayerRef>(null),
    revision = useRef(0),
    serial = useRef(Promise.resolve()),
    latest = useRef(state);

  latest.current = state;

  const plan = state.plan,
    editor = plan.editor as EditorState,
    duration = planDuration(plan),
    fps = clip.media_info.fps || plan.output_fps || 30;

  const layer = editor.layers.find((l) => l.id === selected);

  async function library() {
    const [a, t, s] = await Promise.all([
      api("/editor/assets"),
      api("/editor/templates"),
      api("/sources"),
    ]);
    setAssets(a);
    setTemplates(t);
    setSources(s);
  }

  useEffect(() => {
    let live = true;

    void Promise.all([
      api(`/editor/drafts/${clip.id}`),
      api(`/clips/${clip.id}`),
      api(
        browserMode
          ? `/clips/${clip.id}/remotion`
          : `/studio/drafts/${clip.id}/remotion`,
      ),
      library(),
    ])
      .then(([draft, full, p]) => {
        if (!live) return;

        revision.current = draft?.revision || 0;
        setVersions(full.versions || []);

        if (draft?.base_version === clip.current_version)
          setState({ plan: draft.plan, metadata: draft.metadata });

        if (p)
          setProps({
            ...p,
            fontUrl: new URL(
              `${process.env.NEXT_PUBLIC_BASE_PATH || ""}/ffmpeg/NotoSans.ttf`,
              location.origin,
            ).href,
          });

        setMessage(
          draft?.base_version === clip.current_version
            ? "Recovered autosaved draft"
            : "Ready · originals preserved",
        );
        setReady(true);
      })
      .catch((e) => setError(e.message));

    return () => {
      live = false;
    };
  }, [clip.id]);

  useEffect(() => {
    if (!ready) return;

    const timer = setTimeout(() => {
      const snapshot = structuredClone(state);
      setMessage("Autosaving…");

      serial.current = serial.current.then(async () => {
        try {
          const r = await api(`/editor/drafts/${clip.id}`, {
            method: "PUT",
            body: JSON.stringify({ ...snapshot, revision: revision.current }),
          });
          revision.current = r.revision;
          setMessage("Draft autosaved · no AI analysis or render");
        } catch (e) {
          setError((e as Error).message);
        }
      });
    }, 700);
    return () => clearTimeout(timer);
  }, [state, ready, clip.id]);

  useEffect(() => {
    const p = player.current;
    if (!p) return;
    const update = ({ detail }: any) => setTime(detail.frame / fps);
    p.addEventListener("frameupdate", update);
    return () => p.removeEventListener("frameupdate", update);
  }, [props, fps]);

  function change(next: Snapshot, history = true) {
    if (history) {
      setPast((v) => [...v.slice(-59), structuredClone(latest.current)]);
      setFuture([]);
    }
    setState(next);
  }

  function patchPlan(values: Row) {
    change({ ...state, plan: { ...plan, ...values } });
  }

  function patchEditor(values: Partial<EditorState>) {
    patchPlan({ editor: { ...editor, ...values } });
  }

  function patchLayer(values: Partial<Layer>) {
    if (!layer || layer.locked) return;
    patchEditor({
      layers: editor.layers.map((l) =>
        l.id === selected ? { ...l, ...values } : l,
      ),
    });
  }

  function undo() {
    if (!past.length) return;
    setFuture((v) => [structuredClone(state), ...v]);
    setState(past[past.length - 1]);
    setPast(past.slice(0, -1));
  }

  function redo() {
    if (!future.length) return;
    setPast((v) => [...v, structuredClone(state)]);
    setState(future[0]);
    setFuture(future.slice(1));
  }

  function add(kind: Layer["kind"], a?: Row) {
    const l = newLayer(
      kind,
      Math.min(duration, a?.duration || duration),
      a?.id || null,
    );
    if (a) {
      l.name = a.name;
      if (kind === "image") {
        l.width = 0.25;
        l.height =
          0.25 *
          (a.height / a.width) *
          (clip.media_info.width / clip.media_info.height);
        l.y = 0.1;
        l.x = 0.65;
      }
      if (kind === "video") {
        l.width = 0.45;
        l.height = 0.35;
        l.x = 0.5;
        l.y = 0.1;
      }
    }
    patchEditor({ layers: [...editor.layers, l] });
    setSelected(l.id);
  }

  async function upload(file: File) {
    setBusy(true);
    setError("");
    try {
      const data = new FormData();
      data.set(
        "file",
        /\.(png|jpe?g|webp|svg)$/i.test(file.name)
          ? await prepareEditorImage(file)
          : file,
      );
      const a = await api("/editor/assets", { method: "POST", body: data });
      await library();
      add(a.kind, a);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const gesture = useRef<{
    x: number;
    y: number;
    initial: Snapshot;
    layer: Layer;
    resize: boolean;
  } | null>(null);

  function beginDrag(e: PointerEvent<HTMLElement>, resize = false) {
    if (!layer || layer.locked) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setPast((v) => [...v.slice(-59), structuredClone(state)]);
    setFuture([]);
    gesture.current = {
      x: e.clientX,
      y: e.clientY,
      initial: structuredClone(state),
      layer: structuredClone(layer),
      resize,
    };
  }

  function drag(e: PointerEvent<HTMLElement>) {
    const g = gesture.current;
    if (!g) return;
    const canvas = e.currentTarget
        .closest(".editor-canvas")!
        .getBoundingClientRect(),
      dx = (e.clientX - g.x) / canvas.width,
      dy = (e.clientY - g.y) / canvas.height;
    let x = bound(g.layer.x + dx, 0, 1 - g.layer.width),
      y = bound(g.layer.y + dy, 0, 1 - g.layer.height);
    if (snap) {
      if (Math.abs(x + g.layer.width / 2 - 0.5) < 0.025)
        x = 0.5 - g.layer.width / 2;
      if (Math.abs(y + g.layer.height / 2 - 0.5) < 0.025)
        y = 0.5 - g.layer.height / 2;
    }

    const values = g.resize
      ? {
          width: bound(g.layer.width + dx, 0.03, 1 - g.layer.x),
          height: bound(g.layer.height + dy, 0.03, 1 - g.layer.y),
        }
      : { x, y };

    setState({
      ...g.initial,
      plan: {
        ...g.initial.plan,
        editor: {
          ...g.initial.plan.editor,
          layers: g.initial.plan.editor.layers.map((l: Layer) =>
            l.id === g.layer.id ? { ...l, ...values } : l,
          ),
        },
      },
    });
  }

  function duplicate() {
    if (!layer) return;
    const l = {
      ...structuredClone(layer),
      id: crypto.randomUUID(),
      name: layer.name + " copy",
      locked: false,
    };
    patchEditor({ layers: [...editor.layers, l] });
    setSelected(l.id);
  }

  const timelineGesture = useRef<{
    x: number;
    width: number;
    initial: Snapshot;
    layer: Layer;
    mode: "move" | "start" | "end";
  } | null>(null);

  function beginTimeline(
    e: PointerEvent<HTMLElement>,
    l: Layer,
    mode: "move" | "start" | "end",
  ) {
    if (l.locked) return;
    e.stopPropagation();
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setSelected(l.id);
    setPast((v) => [...v.slice(-59), structuredClone(state)]);
    setFuture([]);
    timelineGesture.current = {
      x: e.clientX,
      width: e.currentTarget.closest(".timeline-lane")!.getBoundingClientRect()
        .width,
      initial: structuredClone(state),
      layer: structuredClone(l),
      mode,
    };
  }

  function dragTimeline(e: PointerEvent<HTMLElement>) {
    const g = timelineGesture.current;
    if (!g) return;
    let delta = ((e.clientX - g.x) / g.width) * duration;
    if (snap) delta = Math.round(delta * fps) / fps;
    const l = g.layer;
    let values: Partial<Layer> = {};

    if (g.mode === "move") {
      const start = bound(l.start + delta, 0, duration - (l.end - l.start));
      values = { start, end: start + l.end - l.start };
    } else if (g.mode === "start") {
      const start = bound(l.start + delta, 0, l.end - 0.05);
      values = {
        start,
        ...(l.kind === "audio" || l.kind === "video"
          ? { trim_start: Math.max(0, l.trim_start + start - l.start) }
          : {}),
      };
    } else values = { end: bound(l.end + delta, l.start + 0.05, duration) };

    setState({
      ...g.initial,
      plan: {
        ...g.initial.plan,
        editor: {
          ...g.initial.plan.editor,
          layers: g.initial.plan.editor.layers.map((v: Layer) =>
            v.id === l.id ? { ...v, ...values } : v,
          ),
        },
      },
    });
  }

  function splitLayer() {
    if (
      !layer ||
      layer.locked ||
      time <= layer.start + 0.05 ||
      time >= layer.end - 0.05
    )
      return;
    const other = {
      ...structuredClone(layer),
      id: crypto.randomUUID(),
      start: time,
      trim_start:
        layer.trim_start +
        (layer.kind === "audio" || layer.kind === "video"
          ? time - layer.start
          : 0),
    };
    patchEditor({
      layers: editor.layers.flatMap((l) =>
        l.id === layer.id ? [{ ...l, end: time }, other] : [l],
      ),
    });
  }

  function splitVideo() {
    let offset = 0;
    const scenes = [];
    let did = false;
    for (const s of plan.scenes) {
      const d = (s.end - s.start) / (s.speed || 1) + (s.freeze || 0);
      if (
        !did &&
        time > offset + 0.05 &&
        time < offset + d - (s.freeze || 0) - 0.05
      ) {
        const cut = s.start + (time - offset) * (s.speed || 1);
        scenes.push({ ...s, end: cut, freeze: 0 }, { ...s, start: cut });
        did = true;
      } else scenes.push(s);
      offset += d;
    }
    if (did) patchPlan({ scenes });
    else
      setError(
        "Move the playhead inside a moving video segment before splitting.",
      );
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      validateEditor(editor, duration);
      await serial.current;
      const samePlan =
        JSON.stringify(plan) ===
        JSON.stringify({ ...clip.plan, editor: editorForPlan(clip.plan) });
      if (samePlan) {
        await api(`/clips/${clip.id}/metadata`, {
          method: "PATCH",
          body: JSON.stringify({ metadata: state.metadata }),
        });
        notify("Publication text saved. The existing video was reused.");
      } else if (browserMode) {
        await api(`/clips/${clip.id}/regenerate`, {
          method: "POST",
          body: JSON.stringify({
            plan: { ...plan, render_engine: "remotion" },
            metadata: state.metadata,
          }),
        });
        notify(
          "Only this clip is queued. Cached analysis and original footage are preserved.",
        );
      } else {
        await api(`/studio/drafts/${clip.id}/edit`, {
          method: "POST",
          body: JSON.stringify({
            version: clip.current_version,
            plan,
            metadata: state.metadata,
            render_engine: "remotion",
          }),
        });
        notify(
          "Only this clip is queued. Cached analysis and original footage are preserved.",
        );
      }
      onQueued();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveTemplate() {
    setBusy(true);
    try {
      await api("/editor/templates", {
        method: "POST",
        body: JSON.stringify({
          name: templateName,
          editor,
          duration,
          campaign_id: clip.campaign_id,
        }),
      });
      await library();
      notify("Design saved in Video Library.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshPreview() {
    setBusy(true);
    setError("");
    setMessage("Building the edited video proxy · no AI analysis");
    try {
      const p = await api(`/editor/drafts/${clip.id}/preview`, {
        method: "POST",
        body: JSON.stringify({ plan }),
      });
      setProps({
        ...p,
        fontUrl: new URL(
          `${process.env.NEXT_PUBLIC_BASE_PATH || ""}/ffmpeg/NotoSans.ttf`,
          location.origin,
        ).href,
      });
      setMessage("Video proxy updated · text and layers preview immediately");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function changeScene(index: number, values: Row) {
    const scenes = plan.scenes.map((s: Row, i: number) =>
      i === index ? { ...s, ...values } : s,
    );
    const d = planDuration({ scenes });
    patchPlan({
      scenes,
      start: Math.min(...scenes.map((s: Row) => s.start)),
      end: Math.max(...scenes.map((s: Row) => s.end)),
      editor: {
        ...editor,
        layers: editor.layers.map((l) => ({
          ...l,
          start: Math.min(l.start, Math.max(0, d - 0.1)),
          end: Math.min(l.end, d),
        })),
      },
      manual_captions: (plan.manual_captions || [])
        .filter((c: Row) => c.start < d)
        .map((c: Row) => ({ ...c, end: Math.min(c.end, d) })),
    });
  }

  const resolvedAssets = Object.fromEntries(assets.map((a) => [a.id, a.url]));

  const preview = props
    ? {
        ...props,
        hook: plan.hook,
        showHook: plan.show_hook,
        overlays: plan.text_overlays || [],
        editor,
        assets: resolvedAssets,
        ...(plan.manual_captions?.length
          ? {
              captions: plan.manual_captions.map((c: Row) => ({
                text: c.text,
                startMs: c.start * 1000,
                endMs: c.end * 1000,
                timestampMs: null,
                confidence: null,
              })),
            }
          : {}),
      }
    : null;

  return (
    <section
      className="professional-editor"
      aria-label="Advanced manual video editor"
    >
      <header className="editor-toolbar">
        <div>
          <h2>{clip.title}</h2>
          <small role="status">{message}</small>
        </div>
        <div className="button-row">
          <button
            className="button secondary"
            disabled={!past.length}
            onClick={undo}
          >
            Undo
          </button>
          <button
            className="button secondary"
            disabled={!future.length}
            onClick={redo}
          >
            Redo
          </button>
          <button className="button secondary" onClick={onClose}>
            Back to Generated Clips
          </button>
          <button
            className="button primary"
            disabled={busy || !ready}
            onClick={() => void save()}
          >
            {busy ? "Saving…" : "Save & render this clip"}
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}

      <div className="editor-columns">
        <aside className="editor-assets">
          <h3>Media & design</h3>
          <button className="button secondary full" onClick={() => add("text")}>
            ＋ Add text
          </button>
          <label className="button secondary file-button">
            ＋ Image, logo or audio
            <input
              type="file"
              accept=".png,.jpg,.jpeg,.webp,.svg,.mp3,.wav,.ogg,.flac,.m4a"
              onChange={(e) => {
                if (e.target.files?.[0]) void upload(e.target.files[0]);
                e.target.value = "";
              }}
            />
          </label>
          <small>
            Use assets you own or have permission to use. Images are safely
            rasterized.
          </small>
          <details open>
            <summary>Library assets</summary>
            {assets.map((a) => (
              <button
                className="editor-asset"
                key={a.id}
                onClick={() => add(a.kind, a)}
              >
                {a.kind === "image" && <img alt="" src={a.url} />}
                <span>
                  {a.name}
                  <small>{a.kind}</small>
                </span>
              </button>
            ))}
          </details>
          <details>
            <summary>Add existing video layer</summary>
            {sources.map((s) => (
              <button
                className="editor-asset"
                key={s.id}
                onClick={async () => {
                  try {
                    const a = await api("/editor/assets/from-source", {
                      method: "POST",
                      body: JSON.stringify({ source_id: s.id }),
                    });
                    await library();
                    add("video", a);
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                {s.filename}
              </button>
            ))}
          </details>
          <details>
            <summary>Reusable designs</summary>
            {templates.map((t) => (
              <button
                className="editor-asset"
                key={t.id}
                onClick={() =>
                  patchPlan({
                    editor: applyTemplate(t.editor, duration, t.duration),
                  })
                }
              >
                Apply {t.name}
              </button>
            ))}
            <label>
              Design name
              <input
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                maxLength={120}
              />
            </label>
            <button
              className="button secondary"
              disabled={!templateName.trim() || busy}
              onClick={() => void saveTemplate()}
            >
              Save current design
            </button>
          </details>
        </aside>

        <div className="editor-preview">
          <div
            className="editor-canvas"
            style={{
              aspectRatio: `${clip.media_info.width}/${clip.media_info.height}`,
            }}
          >
            {preview ? (
              <Player
                ref={player}
                component={ClipComposition}
                inputProps={preview}
                compositionWidth={clip.media_info.width}
                compositionHeight={clip.media_info.height}
                durationInFrames={Math.max(
                  1,
                  Math.round(
                    (props as any)?.duration || clip.media_info.duration * fps,
                  ),
                )}
                fps={fps}
                controls
                style={{ width: "100%", height: "100%" }}
              />
            ) : (
              <video
                src={clip.preview_url}
                controls
                style={{ width: "100%", height: "100%" }}
              />
            )}

            {snap && <div className="editor-center-guide" />}

            {layer &&
              layer.kind !== "audio" &&
              layer.visible &&
              time >= layer.start &&
              time < layer.end && (
                <div
                  tabIndex={0}
                  role="group"
                  aria-label="Position selected layer"
                  onKeyDown={(e) => {
                    const step = e.shiftKey ? 0.05 : 0.005;
                    if (e.key === "ArrowLeft")
                      patchLayer({
                        x: bound(layer.x - step, 0, 1 - layer.width),
                      });
                    else if (e.key === "ArrowRight")
                      patchLayer({
                        x: bound(layer.x + step, 0, 1 - layer.width),
                      });
                    else if (e.key === "ArrowUp")
                      patchLayer({
                        y: bound(layer.y - step, 0, 1 - layer.height),
                      });
                    else if (e.key === "ArrowDown")
                      patchLayer({
                        y: bound(layer.y + step, 0, 1 - layer.height),
                      });
                    else return;
                    e.preventDefault();
                  }}
                  className="layer-selection"
                  style={{
                    left: layer.x * 100 + "%",
                    top: layer.y * 100 + "%",
                    width: layer.width * 100 + "%",
                    height: layer.height * 100 + "%",
                    rotate: layer.rotation + "deg",
                  }}
                  onPointerDown={(e) => beginDrag(e)}
                  onPointerMove={drag}
                  onPointerUp={() => {
                    gesture.current = null;
                  }}
                >
                  <span>
                    {layer.name}
                    {layer.locked ? " · locked" : ""}
                  </span>
                  <button
                    aria-label="Resize selected layer"
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      beginDrag(e, true);
                    }}
                    onPointerMove={drag}
                    onPointerUp={() => {
                      gesture.current = null;
                    }}
                  />
                </div>
              )}
          </div>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void refreshPreview()}
          >
            Refresh timing & framing preview
          </button>
          <p>
            Text, branding, captions and layer changes preview immediately.
            Refresh the video proxy after changing source timing or framing; no
            AI analysis is repeated.
          </p>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={snap}
              onChange={(e) => setSnap(e.target.checked)}
            />{" "}
            Alignment snapping
          </label>
        </div>

        <aside className="editor-properties">
          <h3>Properties</h3>
          <button
            className="button secondary"
            onClick={() => setSelected("metadata")}
          >
            Publishing text
          </button>
          {selected === "metadata" && (
            <EditorMetadata
              value={state.metadata}
              onChange={(metadata) => change({ ...state, metadata })}
            />
          )}
          <div className="button-row">
            <button
              className="button secondary"
              onClick={() => setSelected("source")}
            >
              Video
            </button>
            <button
              className="button secondary"
              onClick={() => setSelected("captions")}
            >
              Subtitles
            </button>
          </div>

          {selected === "source" && (
            <>
              <label>
                Opening headline
                <input
                  value={plan.hook || ""}
                  onChange={(e) =>
                    patchPlan({
                      hook: e.target.value,
                      show_hook: !!e.target.value,
                    })
                  }
                />
              </label>
              <label>
                Original audio volume
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={editor.source_volume}
                  onChange={(e) =>
                    patchEditor({ source_volume: +e.target.value })
                  }
                />
              </label>
              <button className="button secondary" onClick={splitVideo}>
                Split video at playhead
              </button>
              {[
                "source_rotation",
                "source_scale",
                "source_x",
                "source_y",
                "brightness",
                "contrast",
                "saturation",
                "blur",
              ].map((key) => (
                <label key={key}>
                  {key.replaceAll("_", " ")}
                  <input
                    type="number"
                    step=".05"
                    value={
                      (editor as any)[key] ??
                      ([
                        "source_scale",
                        "brightness",
                        "contrast",
                        "saturation",
                      ].includes(key)
                        ? 1
                        : 0)
                    }
                    onChange={(e) => patchEditor({ [key]: +e.target.value })}
                  />
                </label>
              ))}
              <label>
                Background color
                <input
                  value={editor.background}
                  onChange={(e) => patchEditor({ background: e.target.value })}
                />
              </label>
              {plan.scenes.map((s: Row, i: number) => (
                <fieldset key={i}>
                  <legend>Video segment {i + 1}</legend>
                  {[
                    "start",
                    "end",
                    "crop_x",
                    "crop_y",
                    "zoom",
                    "speed",
                    "freeze",
                  ].map((key) => (
                    <label key={key}>
                      {key.replaceAll("_", " ")}
                      <input
                        type="number"
                        step=".05"
                        value={
                          s[key] ??
                          (["zoom", "speed"].includes(key)
                            ? 1
                            : key === "freeze"
                              ? 0
                              : 0.5)
                        }
                        onChange={(e) =>
                          changeScene(i, { [key]: +e.target.value,...(key==="speed"?{speed_end:null}:{}) })
                        }
                      />
                    </label>
                  ))}
                  <label>
                    Transition
                    <select
                      value={s.transition || "cut"}
                      onChange={(e) =>
                        changeScene(i, { transition: e.target.value })
                      }
                    >
                      <option value="cut">Cut</option>
                      <option value="fade">Fade</option>
                    </select>
                  </label>
                  <label>
                    Effect
                    <select
                      value={s.effect || "none"}
                      onChange={(e) =>
                        changeScene(i, { effect: e.target.value })
                      }
                    >
                      <option value="none">None</option>
                      <option value="contrast">Contrast</option>
                      <option value="retro">Retro</option>
                    </select>
                  </label>
                  <button
                    className="button secondary"
                    disabled={plan.scenes.length < 2}
                    onClick={() =>
                      patchPlan({
                        scenes: plan.scenes.filter(
                          (_: Row, n: number) => n !== i,
                        ),
                      })
                    }
                  >
                    Remove segment
                  </button>
                </fieldset>
              ))}
              <label>
                Layout
                <select
                  value={plan.framing || "crop"}
                  onChange={(e) =>
                    patchPlan({
                      framing: e.target.value,
                      ...(e.target.value === "facecam"
                        ? {
                            facecam: plan.facecam || {
                              x: 0,
                              y: 0,
                              width: 0.25,
                              height: 0.3,
                            },
                            facecam_height: plan.facecam_height || 0.28,
                          }
                        : {}),
                      scenes: plan.scenes.map((s: Row) => ({
                        ...s,
                        composition:
                          e.target.value === "fit" ? "fit_blur" : "fill",
                      })),
                    })
                  }
                >
                  <option value="fit">Full source over blur</option>
                  <option value="crop">Fill vertical canvas</option>
                  <option value="facecam">Facecam above full gameplay</option>
                </select>
              </label>
              {plan.framing === "facecam" && (
                <fieldset>
                  <legend>Facecam crop · original source</legend>
                  <p>
                    Review the original footage and adjust this rectangle.
                    Refresh framing preview to see the result.
                  </p>
                  {["x", "y", "width", "height"].map((k) => (
                    <label key={k}>
                      {k}
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step=".01"
                        value={plan.facecam?.[k] ?? 0}
                        onChange={(e) =>
                          patchPlan({
                            facecam: { ...plan.facecam, [k]: +e.target.value },
                          })
                        }
                      />
                    </label>
                  ))}
                  <label>
                    Facecam share of output height
                    <input
                      type="number"
                      min=".15"
                      max=".45"
                      step=".01"
                      value={plan.facecam_height || 0.28}
                      onChange={(e) =>
                        patchPlan({ facecam_height: +e.target.value })
                      }
                    />
                  </label>
                </fieldset>
              )}
            </>
          )}

          {selected === "captions" && (
            <>
              <label>
                Subtitles enabled
                <input
                  type="checkbox"
                  checked={plan.subtitles_enabled}
                  onChange={(e) =>
                    patchPlan({ subtitles_enabled: e.target.checked })
                  }
                />
              </label>
              <label>
                Subtitle preset
                <select
                  value={editor.caption.preset}
                  onChange={(e) =>
                    patchEditor({
                      caption: {
                        ...editor.caption,
                        ...captionPresets[e.target.value],
                        preset: e.target.value,
                      },
                    })
                  }
                >
                  {Object.keys(captionPresets).map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
              {[
                "size",
                "weight",
                "y",
                "opacity",
                "rotation",
                "letter_spacing",
                "line_height",
                "outline_width",
              ].map((key) => (
                <label key={key}>
                  Caption {key.replaceAll("_", " ")}
                  <input
                    type="number"
                    step={key === "y" || key === "opacity" ? ".05" : ".1"}
                    value={(editor.caption as any)[key]}
                    onChange={(e) =>
                      patchEditor({
                        caption: { ...editor.caption, [key]: +e.target.value },
                      })
                    }
                  />
                </label>
              ))}
              {["color", "highlight", "outline", "background"].map((key) => (
                <label key={key}>
                  Caption {key}
                  <input
                    value={(editor.caption as any)[key]}
                    onChange={(e) =>
                      patchEditor({
                        caption: { ...editor.caption, [key]: e.target.value },
                      })
                    }
                  />
                </label>
              ))}
              <label>
                Caption font
                <select
                  value={editor.caption.font_family || "Noto Sans"}
                  onChange={(e) =>
                    patchEditor({
                      caption: {
                        ...editor.caption,
                        font_family: e.target.value as any,
                      },
                    })
                  }
                >
                  <option>Noto Sans</option>
                  <option>serif</option>
                  <option>monospace</option>
                </select>
              </label>
              <label>
                Caption alignment
                <select
                  value={editor.caption.align || "center"}
                  onChange={(e) =>
                    patchEditor({
                      caption: {
                        ...editor.caption,
                        align: e.target.value as any,
                      },
                    })
                  }
                >
                  <option>left</option>
                  <option>center</option>
                  <option>right</option>
                </select>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={editor.caption.uppercase}
                  onChange={(e) =>
                    patchEditor({
                      caption: {
                        ...editor.caption,
                        uppercase: e.target.checked,
                      },
                    })
                  }
                />{" "}
                Uppercase captions
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={editor.caption.shadow !== false}
                  onChange={(e) =>
                    patchEditor({
                      caption: { ...editor.caption, shadow: e.target.checked },
                    })
                  }
                />{" "}
                Caption shadow
              </label>
              <label>
                Caption animation
                <select
                  value={editor.caption.animation}
                  onChange={(e) =>
                    patchEditor({
                      caption: {
                        ...editor.caption,
                        animation: e.target.value as any,
                      },
                    })
                  }
                >
                  {["none", "fade", "pop", "karaoke"].map((a) => (
                    <option key={a}>{a}</option>
                  ))}
                </select>
              </label>
              <p>
                Word highlighting uses real word timestamps when available.
                Uploaded line cues highlight the supplied phrase; no word timing
                is invented.
              </p>
              <button
                className="button secondary"
                onClick={() => {
                  if (props)
                    patchPlan({
                      manual_captions: props.captions.map((c) => ({
                        start: c.startMs / 1000,
                        end: c.endMs / 1000,
                        text: c.text,
                      })),
                    });
                }}
              >
                Load captions for correction
              </button>
              {plan.manual_captions?.map((c: Row, i: number) => (
                <label key={i}>
                  {c.start.toFixed(2)}–{c.end.toFixed(2)}s
                  <textarea
                    value={c.text}
                    onChange={(e) =>
                      patchPlan({
                        manual_captions: plan.manual_captions.map(
                          (v: Row, n: number) =>
                            n === i ? { ...v, text: e.target.value } : v,
                        ),
                      })
                    }
                  />
                </label>
              ))}
            </>
          )}

          {layer && (
            <>
              <label>
                Layer name
                <input
                  value={layer.name}
                  onChange={(e) => patchLayer({ name: e.target.value })}
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={layer.locked}
                  onChange={(e) =>
                    patchEditor({
                      layers: editor.layers.map((l) =>
                        l.id === selected
                          ? { ...l, locked: e.target.checked }
                          : l,
                      ),
                    })
                  }
                />
                Lock layer
              </label>
              {layer.kind === "text" && (
                <>
                  <label>
                    Text
                    <textarea
                      value={layer.text}
                      onChange={(e) => patchLayer({ text: e.target.value })}
                    />
                  </label>
                  <label>
                    Font family
                    <select
                      value={layer.font_family}
                      onChange={(e) =>
                        patchLayer({
                          font_family: e.target.value as Layer["font_family"],
                        })
                      }
                    >
                      <option>Noto Sans</option>
                      <option>serif</option>
                      <option>monospace</option>
                    </select>
                  </label>
                </>
              )}
              {(layer.kind === "audio"
                ? [
                    "start",
                    "end",
                    "volume",
                    "trim_start",
                    "fade_in",
                    "fade_out",
                  ]
                : [
                    "start",
                    "end",
                    "x",
                    "y",
                    "width",
                    "height",
                    "rotation",
                    "opacity",
                    ...(layer.kind === "text"
                      ? ["font_size", "font_weight", "outline_width"]
                      : []),
                  ]
              ).map((key) => (
                <label key={key}>
                  {key.replaceAll("_", " ")}
                  <input
                    disabled={layer.locked}
                    type="number"
                    step={
                      key === "rotation" || key === "font_size" ? "1" : ".05"
                    }
                    value={(layer as any)[key]}
                    onChange={(e) => patchLayer({ [key]: +e.target.value })}
                  />
                </label>
              ))}
              {layer.kind === "text" && (
                <>
                  {["color", "background", "outline_color"].map((key) => (
                    <label key={key}>
                      {key.replaceAll("_", " ")}
                      <input
                        value={(layer as any)[key]}
                        onChange={(e) => patchLayer({ [key]: e.target.value })}
                      />
                    </label>
                  ))}
                  <label>
                    Alignment
                    <select
                      value={layer.align}
                      onChange={(e) =>
                        patchLayer({ align: e.target.value as Layer["align"] })
                      }
                    >
                      <option>left</option>
                      <option>center</option>
                      <option>right</option>
                    </select>
                  </label>
                </>
              )}
              <label>
                Animation
                <select
                  value={layer.animation}
                  onChange={(e) =>
                    patchLayer({
                      animation: e.target.value as Layer["animation"],
                    })
                  }
                >
                  <option>none</option>
                  <option>fade</option>
                  <option>pop</option>
                  <option>slide</option>
                </select>
              </label>
              {layer.kind === "audio" && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={layer.duck}
                    onChange={(e) => patchLayer({ duck: e.target.checked })}
                  />
                  Reduce music during supplied speech cues
                </label>
              )}
              <div className="button-row">
                <button className="button secondary" onClick={duplicate}>
                  Duplicate
                </button>
                <button className="button secondary" onClick={splitLayer}>
                  Split at playhead
                </button>
                <button
                  className="button secondary"
                  disabled={layer.locked}
                  onClick={() => {
                    patchEditor({
                      layers: editor.layers.filter((l) => l.id !== selected),
                    });
                    setSelected("source");
                  }}
                >
                  Remove
                </button>
                <button
                  className="button secondary"
                  onClick={() => {
                    const i = editor.layers.findIndex((l) => l.id === selected);
                    if (i < editor.layers.length - 1) {
                      const layers = [...editor.layers];
                      [layers[i], layers[i + 1]] = [layers[i + 1], layers[i]];
                      patchEditor({ layers });
                    }
                  }}
                >
                  Bring forward
                </button>
              </div>
            </>
          )}
        </aside>
      </div>

      <section className="editor-timeline" aria-label="Multi-track timeline">
        <header>
          <strong>
            {time.toFixed(2)} / {duration.toFixed(2)} s
          </strong>
          <label>
            Playhead
            <input
              type="range"
              min={0}
              max={duration}
              step={1 / fps}
              value={time}
              onChange={(e) => {
                setTime(+e.target.value);
                player.current?.seekTo(Math.round(+e.target.value * fps));
              }}
            />
          </label>
          <label>
            Timeline zoom
            <input
              type="range"
              min={1}
              max={5}
              step={0.25}
              value={zoom}
              onChange={(e) => setZoom(+e.target.value)}
            />
          </label>
        </header>
        <div className="timeline-scroll">
          <div style={{ minWidth: 600 * zoom }}>
            <div className="timeline-row">
              <button onClick={() => setSelected("source")}>Main video</button>
              <div className="timeline-lane">
                {plan.scenes.map((s: Row, i: number) => (
                  <button
                    key={i}
                    style={{
                      width: ((s.end - s.start) / duration) * 100 + "%",
                    }}
                    onClick={() => setSelected("source")}
                  >
                    {i + 1} · {(s.end - s.start).toFixed(1)}s
                  </button>
                ))}
              </div>
            </div>
            <div className="timeline-row">
              <button onClick={() => setSelected("captions")}>Subtitles</button>
              <div className="timeline-lane">
                <button
                  style={{ width: "100%" }}
                  onClick={() => setSelected("captions")}
                >
                  {plan.subtitles_enabled ? editor.caption.preset : "Hidden"}
                </button>
              </div>
            </div>
            {editor.layers.map((l) => (
              <div
                className={
                  "timeline-row " + (selected === l.id ? "selected" : "")
                }
                key={l.id}
              >
                <div>
                  <button onClick={() => setSelected(l.id)}>
                    {l.kind} · {l.name}
                  </button>
                  <button
                    aria-label={`Toggle visibility ${l.name}`}
                    onClick={() =>
                      patchEditor({
                        layers: editor.layers.map((v) =>
                          v.id === l.id ? { ...v, visible: !v.visible } : v,
                        ),
                      })
                    }
                  >
                    {l.visible ? "◉" : "○"}
                  </button>
                </div>
                <div className="timeline-lane">
                  <button
                    className={l.kind}
                    style={{
                      marginLeft: (l.start / duration) * 100 + "%",
                      width: ((l.end - l.start) / duration) * 100 + "%",
                      opacity: l.visible ? 1 : 0.3,
                    }}
                    onPointerDown={(e) => beginTimeline(e, l, "move")}
                    onPointerMove={dragTimeline}
                    onPointerUp={() => {
                      timelineGesture.current = null;
                    }}
                    onClick={() => setSelected(l.id)}
                  >
                    <span
                      className="timeline-trim start"
                      aria-label="Trim layer start"
                      onPointerDown={(e) => beginTimeline(e, l, "start")}
                      onPointerMove={dragTimeline}
                      onPointerUp={() => {
                        timelineGesture.current = null;
                      }}
                    >
                      │
                    </span>
                    {l.locked ? "🔒 " : ""}
                    {l.name}
                    <span
                      className="timeline-trim end"
                      aria-label="Trim layer end"
                      onPointerDown={(e) => beginTimeline(e, l, "end")}
                      onPointerMove={dragTimeline}
                      onPointerUp={() => {
                        timelineGesture.current = null;
                      }}
                    >
                      │
                    </span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <details className="editor-version-history">
        <summary>Saved render versions</summary>
        {versions.map((v) => (
          <button
            className="button secondary"
            key={v.version}
            onClick={async () => {
              if (browserMode) {
                const old = versions.find((n) => n.version === v.version);
                if (old)
                  change({
                    plan: old.plan,
                    metadata: old.metadata_json || state.metadata,
                  });
              } else {
                setBusy(true);
                try {
                  await api(`/studio/drafts/${clip.id}/edit`, {
                    method: "POST",
                    body: JSON.stringify({
                      version: clip.current_version,
                      restore_version: v.version,
                      render_engine: "remotion",
                    }),
                  });
                  onQueued();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }
            }}
          >
            Restore v{v.version}
          </button>
        ))}
      </details>
    </section>
  );
}
