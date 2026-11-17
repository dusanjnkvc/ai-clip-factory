"use client";

type Props = { value: string; onChange: (value: string) => void };

export default function ManualRuleFields({ value, onChange }: Props) {
  let rules: Record<string, any> = {};
  try { rules = JSON.parse(value); } catch { return <div className="notice warning"><span>Correct the advanced JSON below before using the quick rule controls.</span></div>; }
  function change(key: string, next: unknown) { onChange(JSON.stringify({ ...rules, [key]: next }, null, 2)); }
  return <section className="manual-rule-fields">
    <h3>Review the essential rules</h3>
    <p>Copy only requirements you can verify in the campaign. Unknown values should stay blank. These controls do not establish compliance by themselves.</p>
    <div className="manual-platforms"><span>Permitted platforms</span>{[{ value: "youtube", label: "YouTube" }, { value: "tiktok", label: "TikTok" }, { value: "instagram", label: "Instagram" }].map(platform => <label className="checkbox-label" key={platform.value}><input type="checkbox" checked={(rules.allowed_platforms || []).includes(platform.value)} onChange={event => change("allowed_platforms", event.target.checked ? [...(rules.allowed_platforms || []), platform.value] : (rules.allowed_platforms || []).filter((name: string) => name !== platform.value))}/><span>{platform.label}</span></label>)}</div>
    <div className="generation-settings"><label>Minimum duration (seconds)<input type="number" min="0" max="3600" step="0.1" value={rules.min_duration ?? ""} onChange={event => change("min_duration", event.target.value === "" ? null : Number(event.target.value))}/></label><label>Maximum duration (seconds)<input type="number" min="0.1" max="3600" step="0.1" value={rules.max_duration ?? ""} onChange={event => change("max_duration", event.target.value === "" ? null : Number(event.target.value))}/></label></div>
    <label>Required hashtags<input value={(rules.required_hashtags || []).join(" ")} onChange={event => change("required_hashtags", event.target.value.split(/\s+/).filter(Boolean))} placeholder="#campaign #disclosure"/></label>
    <label>Required mentions<input value={(rules.required_mentions || []).join(" ")} onChange={event => change("required_mentions", event.target.value.split(/\s+/).filter(Boolean))} placeholder="@campaign"/></label>
    <label>Required disclosures<textarea rows={2} value={(rules.required_disclosures || []).join("\n")} onChange={event => change("required_disclosures", event.target.value.split("\n").map(item => item.trim()).filter(Boolean))} placeholder="One exact required disclosure per line"/></label>
    <label>Draft approval required?<select value={rules.draft_approval_required === true ? "yes" : rules.draft_approval_required === false ? "no" : "unknown"} onChange={event => change("draft_approval_required", event.target.value === "unknown" ? null : event.target.value === "yes")}><option value="unknown">Unknown — review required</option><option value="yes">Yes — approval must be confirmed</option><option value="no">No — explicitly confirmed by the brief</option></select></label>
    <label>Submission window after publication (minutes)<input type="number" min="1" max="10080" step="1" value={rules.submission_window_minutes ?? ""} onChange={event => change("submission_window_minutes", event.target.value === "" ? null : Number(event.target.value))}/></label>
    <label>Required links<textarea rows={2} value={(rules.required_links || []).join("\n")} onChange={event => change("required_links", event.target.value.split("\n").map(item => item.trim()).filter(Boolean))} placeholder="One exact HTTPS link per line"/></label>
    <details><summary>Creative restrictions</summary><div className="generation-settings">{[
      ["automated_clipping_allowed", "Automated clipping allowed?"], ["ai_generated_allowed", "AI generated video allowed?"], ["music_allowed", "Music allowed?"], ["ai_voice_allowed", "AI voice allowed?"], ["original_footage_required", "Original creator footage required?"], ["paid_promotion_allowed", "Paid promotion allowed?"],
    ].map(([key, label]) => <label key={key}>{label}<select value={rules[key] === true ? "yes" : rules[key] === false ? "no" : "unknown"} onChange={event => change(key, event.target.value === "unknown" ? null : event.target.value === "yes")}><option value="unknown">Unknown — review required</option><option value="yes">Yes — confirmed by brief</option><option value="no">No — confirmed by brief</option></select></label>)}</div>
    <label>Prohibited footage<textarea rows={2} value={(rules.prohibited_footage || []).join("\n")} onChange={event => change("prohibited_footage", event.target.value.split("\n").map(item => item.trim()).filter(Boolean))} placeholder="One restriction per line"/></label>
    <label>Audience restrictions<textarea rows={2} value={(rules.audience_restrictions || []).join("\n")} onChange={event => change("audience_restrictions", event.target.value.split("\n").map(item => item.trim()).filter(Boolean))} placeholder="One restriction per line"/></label></details>
    <small>Record your evidence note below, then save the reviewed rules. Use the advanced JSON for branding, prohibited content, or other detailed requirements.</small>
  </section>;
}
