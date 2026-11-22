"use client";
import { useState } from "react";
import { api } from "@/lib/api";
type Row = Record<string, any>;
export default function ClipReview({
  clip,
  onSaved,
}: {
  clip: Row;
  onSaved: () => Promise<void>;
}) {
  const [note, setNote] = useState(""),
    [checked, setChecked] = useState<string[]>([]),
    [reviewed, setReviewed] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  async function save() {
    setBusy(true);
    try {
      const evidence = Object.fromEntries(
        checked.map((key) => [key, { confirmed: true, note }]),
      );
      const result = await api(`/clips/${clip.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          version: clip.current_version,
          note,
          evidence,
          draft_approved: true,
        }),
      });
      if (result.compliance.status === "PASS") {
        await api(`/studio/drafts/${clip.id}/decision`, {
          method: "POST",
          body: JSON.stringify({
            version: clip.current_version,
            decision: "approved",
            note,
          }),
        });
        setMessage(
          "Current version approved. Publishing still requires your authorization.",
        );
      } else
        setMessage(
          "Review saved. Resolve the remaining checks before approval.",
        );
      await onSaved();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="form-body">
      <h3>Review and approve version {clip.current_version}</h3>
      {(clip.compliance.checks || []).map((c: Row) => (
        <div key={c.rule}>
          <p>
            <strong>{c.status}</strong> · {c.detail}
          </p>
          {c.status === "REVIEW_REQUIRED" && (
            <label>
              <input
                type="checkbox"
                checked={checked.includes(c.rule)}
                onChange={(e) =>
                  setChecked(
                    e.target.checked
                      ? [...checked, c.rule]
                      : checked.filter((k) => k !== c.rule),
                  )
                }
              />{" "}
              I verified this requirement against the source and final clip.
            </label>
          )}
        </div>
      ))}
      <label>
        Review evidence
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
        />
      </label>
      <label>
        <input
          type="checkbox"
          checked={reviewed}
          onChange={(e) => setReviewed(e.target.checked)}
        />{" "}
        I watched this version and reviewed its publication text.
      </label>
      <button
        className="button primary"
        disabled={busy || !reviewed || note.trim().length < 8}
        onClick={() => void save()}
      >
        Save review and approve eligible clip
      </button>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
