import type { CreativeConcept, CreativeCheck, PreflightResult, Row, SourceDescriptor } from "./types";
import { captionSettings, styleById } from "./styles";

export function classifyRequirements(rules: Row): { field:string; classification:CreativeCheck["classification"]; value:any; evidence:any[] }[] {
  const result:{field:string;classification:CreativeCheck["classification"];value:any;evidence:any[]}[]=[];
  for(const [field,value] of Object.entries(rules)){
    if(["evidence","campaign_name","campaign_type"].includes(field)||value==null||Array.isArray(value)&&!value.length)continue;
    let classification:CreativeCheck["classification"]="mandatory";
    if(["uncertainties","contradictions"].includes(field))classification="unclear";
    else if(field.startsWith("recommended_"))classification="recommended";
    else if(field.startsWith("prohibited_")||field.endsWith("_allowed")&&value===false||["audio_restrictions","audience_restrictions"].includes(field))classification="prohibited";
    result.push({field,classification,value,evidence:(rules.evidence||[]).filter((item:Row)=>item.field===field)});
  }
  return result;
}

export function validateConcept(concept: CreativeConcept, sources: SourceDescriptor[], rules: Row): PreflightResult {
  const checks:CreativeCheck[]=[]; const missing_footage:string[]=[];
  const add=(rule:string,status:CreativeCheck["status"],detail:string,blocking=false,classification:CreativeCheck["classification"]="mandatory")=>checks.push({rule,status,detail,blocking,classification});
  const byId=new Map(sources.map(source=>[source.id,source]));
  let duration=0;
  if(!concept.shots.length||concept.shots.length>20)add("storyboard","FAIL","Use between one and twenty real-source shots.",true);
  for(const shot of concept.shots){
    const source=byId.get(shot.source_id);
    if(!source){missing_footage.push(shot.source_id);add("source_footage","FAIL","A storyboard shot references unavailable footage.",true);continue;}
    if(source.rights_confirmed===false)add("source_rights","FAIL","Source rights have not been confirmed for this shot.",true);
    else if(source.rights_confirmed!==true)add("source_rights","REVIEW_REQUIRED","Verify the source-rights record before publishing this footage.");
    if(![shot.start,shot.end,shot.crop_x,shot.crop_y,shot.zoom].every(Number.isFinite)||shot.start<0||shot.end<=shot.start||shot.end>source.media_info.duration+.001)add("timestamps","FAIL","A shot has invalid source timestamps or extends beyond its real source.",true);
    else duration+=shot.end-shot.start;
    if(shot.crop_x<0||shot.crop_x>1||shot.crop_y<0||shot.crop_y>1||shot.zoom<1||shot.zoom>1.5||[shot.crop_x_end,shot.crop_y_end].some(value=>value!=null&&(!Number.isFinite(value)||value<0||value>1)))add("reframe_bounds","FAIL","Crop positions must stay inside the source and zoom between 1 and 1.5.",true);
    if(!["fill","fit_blur","split"].includes(shot.composition)||!["cut","fade"].includes(shot.transition)||!["none","contrast","retro"].includes(shot.effect))add("effect_parameters","FAIL","The storyboard contains an unsupported composition, transition, or effect.",true);
    if(shot.composition==="split"){
      const second=shot.secondary_source_id?byId.get(shot.secondary_source_id):undefined;
      if(!second){missing_footage.push(shot.secondary_source_id||"original creator footage");add("split_footage","FAIL","Split-screen needs a separately supplied authorized source.",true);}
      else {
        const secondaryStart=shot.secondary_start??NaN;
        if(!Number.isFinite(secondaryStart)||secondaryStart<0||secondaryStart+(shot.end-shot.start)>second.media_info.duration+.001)add("secondary_timestamps","FAIL","The paired source does not contain the requested shot range.",true);
        if(second.rights_confirmed===false)add("secondary_rights","FAIL","Confirm permission for the paired source before rendering.",true);
        else if(second.rights_confirmed!==true)add("secondary_rights","REVIEW_REQUIRED","Verify the paired source-rights record before publishing this footage.");
      }
    }
    if(shot.overlay_text.length>140)add("overlay_readability","FAIL","Keep contextual labels at most 140 characters.",true);
  }
  if(duration<1||duration>180)add("duration","FAIL","A browser storyboard must total 1–180 seconds.",true);
  else if(rules.min_duration!=null&&duration<rules.min_duration-.05||rules.max_duration!=null&&duration>rules.max_duration+.05)add("campaign_duration","FAIL","The storyboard duration violates a supplied campaign bound.",true);
  else add("duration","PASS",`The proposed source cuts total ${duration.toFixed(1)} seconds.`);
  try{captionSettings(concept.caption_settings);styleById(concept.style_id);}catch(error){add("style_and_safe_zones","FAIL",(error as Error).message,true);}
  const sizes=new Map([[1080,1920],[720,1280],[540,960]]);
  if(sizes.get(concept.output_width)!==concept.output_height)add("output_format","FAIL","Choose a supported undistorted vertical export size.",true);
  else add("output_format","PASS",`${concept.output_width} × ${concept.output_height} vertical output selected; the actual encoded file still needs verification.`);
  const assisted=rules.automated_clipping_allowed===false||rules.ai_generated_allowed===false;
  if(assisted&&concept.manual_decisions.trim().length<8)add("manual_creative_decisions","REVIEW_REQUIRED","This campaign restricts automation. Record the real manual decisions you made before rendering; suggestions are not approval.",true,"prohibited");
  else if(assisted)add("manual_creative_decisions","REVIEW_REQUIRED","Manual decisions were recorded. A person must verify that the campaign permits this assisted workflow.",false,"prohibited");
  if(rules.original_footage_required===true){
    const originals=concept.shots.flatMap(shot=>[shot.source_id,shot.secondary_source_id]).filter(Boolean).map(id=>byId.get(id!)).filter(source=>source?.original_creator);
    if(!originals.length){missing_footage.push("verified original creator footage");add("original_footage","FAIL","The campaign requires original creator footage. Add and use the required original footage.",true);}
    else add("original_footage","REVIEW_REQUIRED","Original footage is declared and used. Verify ownership and campaign suitability against the actual source.");
  }
  if(rules.music_allowed===false&&concept.audio_treatment!=="mute")add("music_restriction","REVIEW_REQUIRED","Original source audio may contain music. Review it or mute the audio; no automatic music detector is available.",false,"prohibited");
  if(rules.ai_voice_allowed===false)add("ai_voice_restriction","REVIEW_REQUIRED","This workflow adds no AI voice. Verify that the original source audio also meets the campaign rule.",false,"prohibited");
  if(!["source","mute"].includes(concept.audio_treatment))add("audio_treatment","FAIL","Only original source audio or mute is supported; no external soundtrack is added.",true);
  if(rules.required_links?.some((link:string)=>!isHttps(link)))add("required_links","FAIL","Required promotional links must be valid HTTPS URLs without embedded credentials.",true);
  if(rules.required_branding?.length)add("branding","REVIEW_REQUIRED","Verify required logos/branding in the actual footage. The editor does not invent brand assets.");
  if(rules.prohibited_content?.length)add("prohibited_content","REVIEW_REQUIRED","Review the actual source and proposed cuts against prohibited content: "+rules.prohibited_content.join("; "),false,"prohibited");
  if(rules.prohibited_footage?.length)add("prohibited_footage","REVIEW_REQUIRED","Check every referenced source against prohibited footage: "+rules.prohibited_footage.join("; "),false,"prohibited");
  if(rules.audience_restrictions?.length)add("audience_restrictions","REVIEW_REQUIRED","Confirm the actual footage and intended audience meet: "+rules.audience_restrictions.join("; "),false,"prohibited");
  if(rules.paid_promotion_allowed===false)add("paid_promotion","REVIEW_REQUIRED","The campaign restricts paid promotion. Review the proposed use and disclosures against the original terms; no promotion eligibility is inferred.",false,"prohibited");
  if(rules.required_footage?.length)add("required_footage","REVIEW_REQUIRED","Verify the required footage is genuinely present: "+rules.required_footage.join("; "));
  if(rules.draft_approval_required===true)add("draft_approval","REVIEW_REQUIRED","Confirm the campaign owner's draft approval before publishing.");
  if(rules.allowed_platforms?.length===0)add("platforms","REVIEW_REQUIRED","Permitted publishing platforms are unknown.");
  if(rules.uncertainties?.length||rules.contradictions?.length)add("campaign_unknowns","REVIEW_REQUIRED","Campaign uncertainties or contradictions remain unresolved.",false,"unclear");
  if(concept.caption_settings.enabled&&!concept.shots.some(shot=>shot.source_evidence.some(item=>item.startsWith("Caption cue:"))))add("caption_source","REVIEW_REQUIRED","No supplied caption cue supports these shots. Speech captions will not be invented.");
  add("semantic_review","REVIEW_REQUIRED","A person must verify narrative meaning, subject framing, source rights, claims, and campaign suitability. Local metrics do not understand events or dialogue.");
  const state=checks.some(check=>check.status==="FAIL")?"FAIL":checks.some(check=>check.status==="REVIEW_REQUIRED")?"REVIEW_REQUIRED":"PASS";
  return {status:state,render_allowed:!checks.some(check=>check.blocking&&check.status!=="PASS"),publish_ready:false,assisted_manual_required:assisted,checks,missing_footage:[...new Set(missing_footage)]};
}

export function isHttps(value:string):boolean{try{const url=new URL(value);return url.protocol==="https:"&&!url.username&&!url.password;}catch{return false;}}
