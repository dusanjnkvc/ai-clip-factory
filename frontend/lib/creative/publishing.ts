import type { CreativeConcept, Platform, Row } from "./types";
import { isHttps } from "./compliance";

/** Source/editor-grounded copy variants, not model-generated performance claims. */
export function publishingSuggestions(concept:CreativeConcept,rules:Row,platform:Platform){
  if(!["youtube","tiktok","instagram"].includes(platform))throw new Error("Choose YouTube, TikTok, or Instagram.");
  const title=String(concept.selected_title||concept.title).trim().slice(0,100);
  const supplied=String(concept.description||"").trim();
  const hooks=[concept.hook,...concept.hook_alternatives,title].filter(Boolean);
  const unique=[...new Set(hooks)];
  const titles=[title,unique[0]||title,unique[1]||`${title} · selected moment`].map(value=>value.slice(0,100));
  // Exact duplicate user text is retained rather than fabricating a claim merely
  // to produce three superficially different titles.
  let description=supplied;
  const required=[...(rules.required_mentions||[]),...(rules.required_disclosures||[]),...(rules.required_links||[])];
  for(const value of rules.required_links||[])if(!isHttps(value))throw new Error("Required publishing links must use HTTPS without credentials.");
  for(const value of required)if(!description.toLocaleLowerCase().includes(String(value).toLocaleLowerCase()))description=(description+"\n\n"+value).trim();
  const hashtags=[...new Set([...(rules.required_hashtags||[]),...(concept.hashtags||[])])];
  const prefix=[...(rules.required_hashtags||[]),...(rules.required_mentions||[])].join(' ');
  if(prefix&&!description.startsWith(prefix))description=prefix+'\n\n'+description;
  if(hashtags.length>30)throw new Error("Use at most 30 relevant campaign/topic hashtags.");
  if(description.length>2200)throw new Error("Shorten the description while preserving required campaign text.");
  const cover=concept.shots[0]?(concept.shots[0].start+Math.min(3,concept.shots[0].end-concept.shots[0].start)/2):0;
  const strategies={youtube:"Use an accurate searchable title and concise source-grounded description. Review the chosen source cover frame and required campaign text.",tiktok:"Use natural supplied wording and only relevant topic/campaign tags. The first source moment, not an invented promise, supplies the opening.",instagram:"Keep the supplied caption readable, retain required mentions/disclosures, and choose a representative real source cover frame."};
  return {platform,variants:titles.map((option,index)=>({title:option,description,caption:description,hashtags,opening_hook:unique[index]||concept.hook||"",cover_timestamp:cover,strategy:strategies[platform]+" These are locally formatted editorial options, not AI optimization or a trend claim."})),provenance:"local_editorial",requires_review:true};
}
