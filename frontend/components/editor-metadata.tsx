"use client";
import { useState } from "react";
type Row = Record<string, any>;
export default function EditorMetadata({
  value,
  onChange,
}: {
  value: Row;
  onChange: (value: Row) => void;
}) {
  const [platform, setPlatform] = useState("youtube");
  const b = value[platform],
    v = b?.variants?.[b.recommended_index];
  function update(key: string, next: any) {
    onChange({
      ...value,
      [platform]: {
        ...b,
        generation_status: "manual",
        variants: b.variants.map((item: Row, i: number) =>
          i === b.recommended_index ? { ...item, [key]: next } : item,
        ),
      },
    });
  }
  return (
    <div className="form-body">
      <label>
        Publishing platform
        <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
          <option value="youtube">YouTube Shorts</option>
          <option value="tiktok">TikTok</option>
        </select>
      </label>
      {v && (
        <>
          <label>
            Proposed option
            <select
              value={b.recommended_index}
              onChange={(e) =>
                onChange({
                  ...value,
                  [platform]: { ...b, recommended_index: +e.target.value },
                })
              }
            >
              {b.variants.map((m: Row, i: number) => (
                <option value={i} key={i}>
                  {m.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Publication title
            <input
              value={v.title}
              maxLength={100}
              onChange={(e) => update("title", e.target.value)}
            />
          </label>
          <label>
            {platform === "youtube" ? "Description" : "Caption"}
            <textarea
              rows={5}
              value={platform === "youtube" ? v.description : v.caption}
              onChange={(e) =>
                update(
                  platform === "youtube" ? "description" : "caption",
                  e.target.value,
                )
              }
            />
          </label>
          <label>
            Hashtags
            <input
              value={v.hashtags.join(" ")}
              onChange={(e) =>
                update("hashtags", e.target.value.split(/\s+/).filter(Boolean))
              }
            />
          </label>
          <p>
            Campaign hashtags and mentions are put first when saved. These
            proposals do not guarantee views.
          </p>
          <small>{v.reasoning}</small>
        </>
      )}
    </div>
  );
}
