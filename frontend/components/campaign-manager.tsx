"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import ManualRuleFields from "./manual-rule-fields";
type Row = Record<string, any>;
export default function CampaignManager() {
  const [campaigns, setCampaigns] = useState<Row[]>([]),
    [id, setId] = useState(""),
    [name, setName] = useState(""),
    [brief, setBrief] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [rules, setRules] = useState("{}"),
    [note, setNote] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const chosen = campaigns.find((c) => c.id === id);
  async function reload() {
    setCampaigns(await api("/campaigns"));
  }
  useEffect(() => {
    reload().catch((e) => setMessage(e.message));
  }, []);
  function select(value: string) {
    setId(value);
    const c = campaigns.find((c) => c.id === value);
    setName(c?.name || "");
    setBrief(c?.brief || "");
    setRules(JSON.stringify(c?.rules || {}, null, 2));
    setNote("");
    setFile(null);
    setMessage("");
  }
  async function extract() {
    setBusy(true);
    setMessage("");
    try {
      let c = chosen;
      if (!c)
        c = await api("/campaigns", {
          method: "POST",
          body: JSON.stringify({ name: name.trim(), brief }),
        });
      if (file) {
        const form = new FormData();
        form.set("file", file);
        await api(`/campaigns/${c!.id}/attachments`, {
          method: "POST",
          body: form,
        });
      }
      c = await api(
        `${process.env.NEXT_PUBLIC_BROWSER_MODE === "true" ? "" : "/studio"}/campaigns/${c!.id}/analyze`,
        { method: "POST" },
      );
      await reload();
      setId(c!.id);
      setRules(JSON.stringify(c!.rules || {}, null, 2));
      setFile(null);
      setMessage(
        c!.analysis_error ||
          "Rules extracted. Review the requirements below and save your corrections.",
      );
      window.dispatchEvent(new Event("campaigns-changed"));
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    try {
      const c = await api(`/campaigns/${id}/rules`, {
        method: "PATCH",
        body: JSON.stringify({ rules: JSON.parse(rules), note }),
      });
      await reload();
      setRules(JSON.stringify(c.rules, null, 2));
      setMessage(
        "Reviewed campaign rules saved. They take priority in every clip.",
      );
      window.dispatchEvent(new Event("campaigns-changed"));
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="panel form-body campaign-manager">
      <summary>Campaigns · create, review and correct rules</summary>
      <label>
        Manage campaign
        <select value={id} onChange={(e) => select(e.target.value)}>
          <option value="">Create a campaign</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      {!chosen && (
        <>
          <label>
            Campaign name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
            />
          </label>
          <label>
            Campaign instructions
            <textarea
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              rows={4}
            />
          </label>
        </>
      )}
      {chosen && (
        <details>
          <summary>Original instructions and extraction evidence</summary>
          <p className="brief-text">{chosen.brief}</p>
          <pre>{JSON.stringify(chosen.rules?.evidence || [], null, 2)}</pre>
        </details>
      )}
      <label>
        Add PDF or text rules
        <input
          type="file"
          accept=".pdf,.txt,.docx"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>
      <button
        className="button secondary"
        disabled={busy || (!id && !name.trim())}
        onClick={() => void extract()}
      >
        {busy ? "Working…" : "Extract supplied rules"}
      </button>
      {chosen && (
        <>
          <ManualRuleFields value={rules} onChange={setRules} />
          <details>
            <summary>Detailed campaign requirements</summary>
            <label>
              Structured rules
              <textarea
                rows={12}
                value={rules}
                onChange={(e) => setRules(e.target.value)}
              />
            </label>
          </details>
          <label>
            Evidence for your review
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Which original instructions did you verify?"
            />
          </label>
          <button
            className="button primary"
            disabled={busy || note.trim().length < 8}
            onClick={() => void save()}
          >
            Save reviewed rules
          </button>
        </>
      )}
      {message && <p role="status">{message}</p>}
    </details>
  );
}
