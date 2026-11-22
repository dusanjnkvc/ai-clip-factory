import {
  listRecords,
  getRecord,
  getBlob,
  setRecord,
  putBlob,
  mediaUrl,
  recordId,
  timestamp,
} from "./browser-db";
import { validateEditor, planDuration } from "./editor-project";
import { validatePlan, validateMetadata, compliance } from "./browser-rules";

export async function browserEditorApi(
  path: string,
  options: RequestInit,
): Promise<any> {
  const p = path.split("/").filter(Boolean),
    method = (options.method || "GET").toUpperCase();
  const body = () => JSON.parse(String(options.body || "{}"));
  async function required(table: string, id: string) {
    const row = await getRecord(table, id);
    if (!row) throw new Error("The owned editor record was not found.");
    return row;
  }
  async function checkedEditor(editor: any, duration: number) {
    const result = validateEditor(editor, duration);
    for (const layer of result.layers) {
      if (layer.kind === "text") continue;
      const asset = await required("editor_assets", layer.asset_id!);
      if (asset.archived || asset.kind !== layer.kind)
        throw new Error(
          "Choose an available library asset of the matching type.",
        );
      if (
        asset.duration != null &&
        layer.trim_start + layer.end - layer.start > asset.duration + 0.05
      )
        throw new Error("A media layer extends beyond its original source.");
    }
    return result;
  }
  async function checkedPlan(plan: any, sourceId: string) {
    const available = await listRecords("sources"),
      source = await required("sources", sourceId),
      durations = Object.fromEntries(
        available.map((s) => [s.id, s.media_info.duration]),
      );
    const result = validatePlan(plan, source.media_info.duration, durations);
    if (result.editor)
      result.editor = await checkedEditor(result.editor, planDuration(result));
    return result;
  }
  if (p[1] === "assets") {
    if (p.length === 2 && method === "GET")
      return Promise.all(
        (await listRecords("editor_assets"))
          .filter((a) => !a.archived)
          .map(async (a) => ({ ...a, url: await mediaUrl(a.storage_key) })),
      );
    if (p[2] === "from-source" && method === "POST") {
      const s = await required("sources", body().source_id),
        existing = (await listRecords("editor_assets")).find(
          (a) => a.source_id === s.id,
        );
      if (existing)
        return { ...existing, url: await mediaUrl(existing.storage_key) };
      const a = {
        id: recordId(),
        source_id: s.id,
        name: s.filename,
        kind: "video",
        mime: "video/mp4",
        storage_key: s.storage_key,
        size_bytes: s.size_bytes,
        ...s.media_info,
      };
      await setRecord("editor_assets", a);
      return { ...a, url: await mediaUrl(a.storage_key) };
    }
    if (p.length === 2 && method === "POST") {
      const data = options.body as FormData,
        file = data.get("file");
      if (!(file instanceof File) || file.size > 50 * 1024 * 1024)
        throw new Error("Choose an image or audio asset up to 50 MB.");
      let blob: Blob = file,
        kind = "audio",
        info: any = {};
      if (/\.(png|jpe?g|webp|svg)$/i.test(file.name)) {
        const { prepareEditorImage } = await import("./editor-assets");
        blob = await prepareEditorImage(file);
        kind = "image";
        const image = await createImageBitmap(blob);
        info = { width: image.width, height: image.height };
        image.close();
      } else {
        if (!/\.(mp3|wav|m4a|ogg|flac)$/i.test(file.name))
          throw new Error("Choose a supported image or audio file.");
        const url = URL.createObjectURL(file);
        try {
          const audio = new Audio();
          audio.preload = "metadata";
          info.duration = await new Promise<number>((resolve, reject) => {
            const timer = setTimeout(
              () => reject(new Error("Audio metadata timed out.")),
              20000,
            );
            audio.onloadedmetadata = () => {
              clearTimeout(timer);
              resolve(audio.duration);
              audio.src = "";
            };
            audio.onerror = () => {
              clearTimeout(timer);
              reject(new Error("This browser cannot decode the audio."));
            };
            audio.src = url;
          });
        } finally {
          URL.revokeObjectURL(url);
        }
        if (
          !Number.isFinite(info.duration) ||
          info.duration <= 0 ||
          info.duration > 300
        )
          throw new Error(
            "Audio assets must be between zero and five minutes.",
          );
      }
      const id = recordId(),
        key = "editor-assets/" + id;
      await putBlob(key, blob);
      const a = {
        id,
        name: file.name,
        kind,
        mime: blob.type,
        storage_key: key,
        size_bytes: blob.size,
        ...info,
      };
      await setRecord("editor_assets", a);
      return { ...a, url: await mediaUrl(key) };
    }
    const a = await required("editor_assets", p[2]);
    if (method === "PATCH") {
      const name = String(body().name || "").trim();
      if (!name || name.length > 200)
        throw new Error("Use an asset name of 1–200 characters.");
      await setRecord("editor_assets", { ...a, name });
      return { ...a, name };
    }
    if (method === "DELETE") {
      const records = [
        ...(await listRecords("clips")),
        ...(await listRecords("editor_drafts")),
        ...(await listRecords("editor_templates")),
      ];
      if (records.some((record) => JSON.stringify(record).includes(a.id)))
        throw new Error(
          "This asset is used by a clip, version, draft or template. Keep it to preserve that project.",
        );
      await setRecord("editor_assets", { ...a, archived: true });
      return { archived: true, original_preserved: true };
    }
  }
  if (p[1] === "drafts") {
    const clip = await required("clips", p[2]),
      old = await getRecord("editor_drafts", clip.id);
    if (p[3] === "duplicate" && method === "POST") {
      const id = recordId(),
        key = `clips/${id}/v1.mp4`;
      await putBlob(key, await getBlob(clip.storage_key));
      const media_info = structuredClone(clip.media_info);
      if (media_info.remotion_base_key) {
        const base = `clips/${id}/v1-base.mp4`;
        await putBlob(base, await getBlob(media_info.remotion_base_key));
        media_info.remotion_base_key = base;
      }
      const source = await required("sources", clip.source_id),
        checks = compliance(
          clip.plan,
          clip.metadata_json,
          clip.rules_snapshot,
          media_info,
          source.rights_confirmed,
        );
      await setRecord("clips", {
        ...clip,
        compliance: checks,
        id,
        title: clip.title + " - copy",
        storage_key: key,
        media_info,
        status: "review",
        draft_approved: false,
        current_version: 1,
        created_at: timestamp(),
        versions: [
          {
            id: recordId(),
            version: 1,
            created_at: timestamp(),
            plan: clip.plan,
            metadata_json: clip.metadata_json,
            storage_key: key,
          },
        ],
      });
      return { id, current_version: 1, original_preserved: true };
    }
    if (p[3] === "preview" && method === "POST") {
      const source = await required("sources", clip.source_id),
        plan = await checkedPlan(body().plan, clip.source_id);
      const { renderBrowserClip } = await import("./browser-media");
      const { remotionProps } = await import("./remotion-plan");
      const cues = (await getRecord("subtitles", source.id))?.cues || [],
        sources: any = {};
      for (const id of new Set([
        source.id,
        ...plan.scenes.map((s: any) => s.source_id || source.id),
        ...plan.scenes.map((s: any) => s.secondary_source_id).filter(Boolean),
      ])) {
        const s = await required("sources", id as string);
        sources[id as string] = {
          blob: await getBlob(s.storage_key),
          cues: (await getRecord("subtitles", id as string))?.cues || [],
        };
      }
      const clean = {
        ...plan,
        editor: null,
        show_hook: false,
        subtitles_enabled: false,
        required_on_video_text: [],
        text_overlays: [],
        scenes: plan.scenes.map((s: any) => ({ ...s, overlay_text: "" })),
      };
      const base = await renderBrowserClip(
          await getBlob(source.storage_key),
          clean,
          [],
          "fast",
          async () => {},
          sources,
        ),
        key = "editor-proxies/" + clip.id + "/" + recordId();
      await putBlob(key, base.blob);
      return {
        ...remotionProps(
          { ...plan, source_id: source.id },
          sources,
          await mediaUrl(key),
          "",
        ),
        duration: Math.round(base.media_info.duration * 30),
        fps: 30,
        width: base.media_info.width,
        height: base.media_info.height,
      };
    }
    if (method === "GET") return old || null;
    if (method === "PUT") {
      const data = body();
      if (data.revision !== (old?.revision || 0))
        throw new Error(
          "This draft changed in another window. Reopen it before saving.",
        );
      const plan = await checkedPlan(data.plan, clip.source_id);
      const next = {
        id: clip.id,
        plan,
        metadata: validateMetadata(data.metadata),
        revision: data.revision + 1,
        base_version: clip.current_version,
        updated_at: timestamp(),
      };
      await setRecord("editor_drafts", next);
      return next;
    }
  }
  if (p[1] === "templates") {
    if (method === "GET") return listRecords("editor_templates");
    if (method === "POST") {
      const data = body();
      if (
        !data.name?.trim() ||
        data.name.length > 120 ||
        !Number.isFinite(data.duration) ||
        data.duration < 1 ||
        data.duration > 600
      )
        throw new Error("Supply a design name and valid duration.");
      if ((await listRecords("editor_templates")).length >= 50)
        throw new Error("The library supports up to 50 saved designs.");
      if (data.campaign_id) await required("campaigns", data.campaign_id);
      const editor = await checkedEditor(data.editor, data.duration);
      const next = {
        id: recordId(),
        name: data.name,
        editor,
        duration: data.duration,
        campaign_id: data.campaign_id || null,
      };
      await setRecord("editor_templates", next);
      return next;
    }
  }
  throw new Error("Unsupported editor operation.");
}
