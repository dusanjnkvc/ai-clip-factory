import React from "react";
import {
  Img,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { Audio, Video } from "@remotion/media";
import type { Layer, EditorState } from "../lib/editor-project";
import type { Caption } from "@remotion/captions";

function LayerContent({
  layer,
  src,
  captions,
}: {
  layer: Layer;
  src?: string;
  captions: Caption[];
}) {
  const frame = useCurrentFrame(),
    { fps, width, height } = useVideoConfig();
  const entrance = interpolate(frame, [0, Math.max(1, 0.25 * fps)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const volume = (f: number) => {
    const t = f / fps,
      absolute = t + layer.start,
      total = layer.end - layer.start;
    const fade = Math.min(
      1,
      layer.fade_in ? t / layer.fade_in : 1,
      layer.fade_out ? (total - t) / layer.fade_out : 1,
    );
    const duck =
      layer.duck &&
      captions.some(
        (c) => absolute * 1000 >= c.startMs && absolute * 1000 < c.endMs,
      )
        ? 0.25
        : 1;
    return Math.max(0, layer.volume * fade * duck);
  };
  if (layer.kind === "audio")
    return src ? (
      <Audio
        src={src}
        trimBefore={Math.round(layer.trim_start * fps)}
        volume={volume}
        premountFor={fps}
      />
    ) : null;
  const style: React.CSSProperties = {
    position: "absolute",
    left: layer.x * width,
    top: layer.y * height,
    width: layer.width * width,
    height: layer.height * height,
    opacity: layer.opacity * (layer.animation === "fade" ? entrance : 1),
    rotate: `${layer.rotation}deg`,
    scale: layer.animation === "pop" ? 0.8 + 0.2 * entrance : 1,
    translate:
      layer.animation === "slide" ? `0 ${(1 - entrance) * 30}px` : "0 0",
    overflowWrap: "anywhere",
    whiteSpace: "pre-wrap",
    fontFamily:
      layer.font_family === "Noto Sans"
        ? "ClipFactoryCaption,Arial,sans-serif"
        : layer.font_family,
    fontSize: (layer.font_size * width) / 1080,
    fontWeight: layer.font_weight,
    color: layer.color,
    backgroundColor: layer.background,
    textAlign: layer.align,
    lineHeight: 1.2,
    textShadow: layer.shadow ? "0 2px 6px #000" : undefined,
    WebkitTextStroke: `${(layer.outline_width * width) / 1080}px ${layer.outline_color}`,
    paintOrder: "stroke fill",
  };
  return (
    <div data-editor-layer={layer.id} style={style}>
      {layer.kind === "text" ? (
        layer.text
      ) : layer.kind === "image" && src ? (
        <Img
          src={src}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
      ) : layer.kind === "video" && src ? (
        <Video
          src={src}
          trimBefore={Math.round(layer.trim_start * fps)}
          volume={volume}
          premountFor={fps}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : null}
    </div>
  );
}
export function EditorLayers({
  editor,
  assets,
  captions,
}: {
  editor?: EditorState | null;
  assets: Record<string, string>;
  captions: Caption[];
}) {
  const { fps } = useVideoConfig();
  return (
    <>
      {editor?.layers
        .filter((l) => l.visible)
        .map((layer) => (
          <Sequence
            key={layer.id}
            name={layer.name}
            from={Math.round(layer.start * fps)}
            durationInFrames={Math.max(
              1,
              Math.round((layer.end - layer.start) * fps),
            )}
            premountFor={fps}
          >
            <LayerContent
              layer={layer}
              src={layer.asset_id ? assets[layer.asset_id] : undefined}
              captions={captions}
            />
          </Sequence>
        ))}
    </>
  );
}
