/** Shared, versioned non-destructive layers. All times are output seconds;
 * spatial coordinates are fractions of the output canvas. Asset URLs are
 * resolved by the owning workspace, never persisted in this project. */
export type Layer = {
  id: string;
  kind: "text" | "image" | "video" | "audio";
  name: string;
  start: number;
  end: number;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  opacity: number;
  visible: boolean;
  locked: boolean;
  text: string;
  asset_id: string | null;
  font_size: number;
  font_family: "Noto Sans" | "serif" | "monospace";
  font_weight: number;
  color: string;
  background: string;
  outline_color: string;
  outline_width: number;
  shadow: boolean;
  align: "left" | "center" | "right";
  animation: "none" | "fade" | "pop" | "slide";
  volume: number;
  fade_in: number;
  fade_out: number;
  trim_start: number;
  duck: boolean;
};
export type CaptionStyle = {
  preset: string;
  size: number;
  color: string;
  highlight: string;
  outline: string;
  outline_width: number;
  background: string;
  y: number;
  opacity: number;
  rotation: number;
  letter_spacing: number;
  line_height: number;
  weight: number;
  uppercase: boolean;
  font_family?: "Noto Sans" | "serif" | "monospace";
  align?: "left" | "center" | "right";
  shadow?: boolean;
  animation: "none" | "fade" | "pop" | "karaoke";
};
export type EditorState = {
  schema_version: 1;
  layers: Layer[];
  caption: CaptionStyle;
  source_volume: number;
  background: string;
  source_rotation: number;
  source_scale: number;
  source_x: number;
  source_y: number;
  brightness: number;
  contrast: number;
  saturation: number;
  blur: number;
};
export const captionPresets: Record<string, Partial<CaptionStyle>> = {
  "Viral bold": {
    size: 76,
    weight: 900,
    uppercase: true,
    animation: "pop",
    background: "#00000000",
  },
  "Hormozi-inspired": {
    size: 74,
    weight: 900,
    highlight: "#FFE600",
    uppercase: true,
    animation: "karaoke",
  },
  Gaming: {
    size: 68,
    weight: 800,
    color: "#FFFFFF",
    highlight: "#A3FF12",
    animation: "pop",
  },
  "Neon glow": {
    size: 66,
    color: "#E9D5FF",
    highlight: "#22D3EE",
    outline: "#7E22CE",
    outline_width: 3,
    animation: "fade",
  },
  "Minimal cinematic": {
    size: 48,
    weight: 500,
    background: "#00000000",
    animation: "fade",
  },
  "Word-by-word karaoke": {
    size: 68,
    highlight: "#FFE600",
    animation: "karaoke",
  },
  Podcast: {
    size: 60,
    weight: 600,
    background: "#000000B0",
    animation: "none",
  },
  "Highlighted keywords": {
    size: 66,
    highlight: "#B6A7FA",
    animation: "karaoke",
  },
  "Animated pop-up": { size: 72, weight: 800, animation: "pop" },
  "Colorful entertainment": {
    size: 72,
    color: "#FFFFFF",
    highlight: "#FF5BA6",
    animation: "karaoke",
  },
};
export function emptyEditor(): EditorState {
  return {
    schema_version: 1,
    layers: [],
    source_volume: 1,
    background: "#000000",
    source_rotation: 0,
    source_scale: 1,
    source_x: 0,
    source_y: 0,
    brightness: 1,
    contrast: 1,
    saturation: 1,
    blur: 0,
    caption: {
      preset: "Gaming",
      size: 68,
      color: "#FFFFFF",
      highlight: "#FFE600",
      outline: "#111111",
      outline_width: 2,
      background: "#000000B0",
      y: 0.82,
      opacity: 1,
      rotation: 0,
      letter_spacing: 0,
      line_height: 1.2,
      weight: 700,
      uppercase: false,
      animation: "none",
    },
  };
}
export function newLayer(
  kind: Layer["kind"],
  duration: number,
  asset_id: string | null = null,
): Layer {
  return {
    id: crypto.randomUUID(),
    kind,
    name:
      kind === "text"
        ? "Custom text"
        : kind === "image"
          ? "Logo / image"
          : kind === "audio"
            ? "Audio track"
            : "Video layer",
    text: kind === "text" ? "Your text" : "",
    asset_id,
    start: 0,
    end: duration,
    x: 0.1,
    y: 0.35,
    width: 0.8,
    height: 0.15,
    rotation: 0,
    opacity: 1,
    visible: true,
    locked: false,
    font_size: 64,
    font_family: "Noto Sans",
    font_weight: 700,
    color: "#FFFFFF",
    background: "#00000000",
    outline_color: "#111111",
    outline_width: 1,
    shadow: true,
    align: "center",
    animation: "none",
    volume: 1,
    fade_in: 0,
    fade_out: 0,
    trim_start: 0,
    duck: false,
  };
}
export function validateEditor(value: any, duration: number): EditorState {
  if (
    !value ||
    value.schema_version !== 1 ||
    !Array.isArray(value.layers) ||
    value.layers.length > 60
  )
    throw new Error("Unsupported editor project or too many layers.");
  const v = { ...emptyEditor(), ...structuredClone(value) },
    ids = new Set();
  function bound(n: any, min: number, max: number, label: string) {
    if (typeof n !== "number" || !Number.isFinite(n) || n < min || n > max)
      throw new Error(label + " is outside supported bounds.");
  }
  function color(c: any) {
    if (typeof c !== "string" || !/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(c))
      throw new Error("Use a hexadecimal layer color.");
  }
  bound(v.source_volume, 0, 2, "Source volume");
  color(v.background);
  bound(v.source_rotation, -180, 180, "Video rotation");
  bound(v.source_scale, 0.5, 2, "Video scale");
  bound(v.source_x, -0.5, 0.5, "Video X");
  bound(v.source_y, -0.5, 0.5, "Video Y");
  bound(v.brightness, 0.2, 2, "Brightness");
  bound(v.contrast, 0.2, 2, "Contrast");
  bound(v.saturation, 0, 3, "Saturation");
  bound(v.blur, 0, 30, "Blur");
  for (const l of v.layers) {
    if (
      !l ||
      typeof l.id !== "string" ||
      ids.has(l.id) ||
      !["text", "image", "video", "audio"].includes(l.kind)
    )
      throw new Error("Every layer needs a unique ID and supported type.");
    ids.add(l.id);
    bound(l.start, 0, duration, "Layer start");
    bound(l.end, l.start + 0.001, duration + 0.001, "Layer end");
    for (const k of ["x", "y", "opacity"]) bound(l[k], 0, 1, k);
    for (const k of ["width", "height"]) bound(l[k], 0.01, 1, k);
    bound(l.rotation, -180, 180, "Rotation");
    bound(l.font_size, 12, 200, "Font size");
    bound(l.font_weight, 100, 900, "Font weight");
    bound(l.outline_width, 0, 12, "Outline");
    bound(l.volume, 0, 2, "Volume");
    bound(l.trim_start, 0, 7200, "Asset offset");
    bound(l.fade_in, 0, 5, "Fade in");
    bound(l.fade_out, 0, 5, "Fade out");
    if (
      typeof l.text !== "string" ||
      l.text.length > 2000 ||
      typeof l.name !== "string" ||
      l.name.length > 100 ||
      !["Noto Sans", "serif", "monospace"].includes(l.font_family) ||
      !["left", "center", "right"].includes(l.align) ||
      !["none", "fade", "pop", "slide"].includes(l.animation)
    )
      throw new Error("Invalid layer text, font or animation.");
    if (
      l.kind !== "text" &&
      (typeof l.asset_id !== "string" ||
        !/^[a-zA-Z0-9-]{1,64}$/.test(l.asset_id))
    )
      throw new Error("Media layers require an owned library asset.");
    for (const k of ["visible", "locked", "shadow", "duck"])
      if (typeof l[k] !== "boolean") throw new Error("Invalid layer switch.");
    for (const c of [l.color, l.background, l.outline_color]) color(c);
  }
  const c = v.caption;
  if (!c || !["none", "fade", "pop", "karaoke"].includes(c.animation))
    throw new Error("Invalid caption style.");
  if (
    (c.font_family != null &&
      !["Noto Sans", "serif", "monospace"].includes(c.font_family)) ||
    (c.align != null && !["left", "center", "right"].includes(c.align)) ||
    (c.shadow != null && typeof c.shadow !== "boolean")
  )
    throw new Error("Invalid caption font, alignment or shadow.");
  bound(c.size, 30, 120, "Caption size");
  bound(c.weight, 100, 900, "Caption weight");
  bound(c.y, 0.05, 0.95, "Caption position");
  bound(c.opacity, 0, 1, "Caption opacity");
  bound(c.rotation, -180, 180, "Caption rotation");
  bound(c.letter_spacing, -3, 15, "Letter spacing");
  bound(c.line_height, 0.8, 2, "Line spacing");
  bound(c.outline_width, 0, 12, "Caption outline");
  for (const x of [c.color, c.highlight, c.outline, c.background]) color(x);
  return v;
}
export function editorForPlan(plan: any): EditorState {
  return plan.editor
    ? { ...emptyEditor(), ...structuredClone(plan.editor) }
    : emptyEditor();
}
export function planDuration(plan: any): number {
  return plan.scenes.reduce((total: number, s: any) => {
    if (s.speed_end != null && Math.abs(s.speed_end - (s.speed || 1)) > 0.001) {
      let duration = 0;
      for (let i = 0; i < 4; i++)
        duration +=
          (s.end - s.start) /
          4 /
          ((s.speed || 1) + ((s.speed_end - (s.speed || 1)) * (i + 0.5)) / 4);
      return total + duration + (s.freeze || 0);
    }
    return total + (s.end - s.start) / (s.speed || 1) + (s.freeze || 0);
  }, 0);
}
export function applyTemplate(
  editor: EditorState,
  duration: number,
  originalDuration: number,
) {
  const copy = structuredClone(editor);
  for (const layer of copy.layers) {
    layer.start = Math.min(layer.start, duration - 0.05);
    layer.end = Math.min(
      duration,
      Math.abs(layer.end - originalDuration) < 0.05 ? duration : layer.end,
    );
  }
  return validateEditor(copy, duration);
}
