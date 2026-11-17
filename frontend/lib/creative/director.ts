import type { CreativeConcept, CreativeOptions, GenerateInput, HookAssessment, Row, Shot, SourceAnalysis, SourceDescriptor, StyleId } from "./types";
import { captionSettings, recommendStyle, styleById } from "./styles";
import { validateConcept } from "./compliance";

const clamp=(value:number,min:number,max:number)=>Math.min(max,Math.max(min,value));
const normalized=(text:string)=>text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu," ").trim();
const round=(value:number)=>Math.round(value*1000)/1000;
function uid(){return typeof crypto!=="undefined"&&crypto.randomUUID?crypto.randomUUID():`concept-${Date.now()}-${Math.random().toString(36).slice(2)}`;}

export function evaluateHook(hook:string, analysis:SourceAnalysis, start=0):HookAssessment{
  const text=hook.trim();const words=text.split(/\s+/).filter(Boolean);const cue=analysis.cues.find(item=>item.end>start&&item.start<start+3);
  const normalizedHook=normalized(text);
  const exact=Boolean(normalizedHook&&cue&&normalized(cue.text).includes(normalizedHook));
  const first=analysis.frames.find(frame=>frame.timestamp>=start&&frame.timestamp<=start+3);
  const factors=[
    {name:"Clarity",score:text?clamp(100-Math.max(0,words.length-9)*5,20,95):35,explanation:text?"Short, concrete wording is easier to read; meaning still requires your review.":"No text hook is supplied. Review the visual opening."},
    {name:"Curiosity",score:text?clamp(45+(text.includes("?")?10:0)+(words.length>=3&&words.length<=10?10:0),20,70):35,explanation:"A simple wording heuristic, not a prediction of audience retention."},
    {name:"Visual impact",score:first?Math.round(clamp(35+first.change*35+first.sharpness*20,0,90)):30,explanation:first?"Based on measured frame change and sharpness in the first three seconds; no event was recognized.":"No sampled opening frame supports a visual assessment."},
    {name:"Relevance",score:exact?85:text?45:30,explanation:exact?"The wording is present in a supplied caption cue.":"Confirm this editor-written text accurately describes the footage."},
    {name:"Readability",score:text?clamp(100-Math.max(0,text.length-35)*1.5,10,95):65,explanation:"Assesses text length for a brief vertical opening, not font contrast in the final render."},
    {name:"Accuracy",score:exact?85:text?40:50,explanation:exact?"Exact supplied caption text supports the words. Caption authenticity and full context still need review.":"Accuracy cannot be established by local frame metrics; manually verify every claim."},
  ];
  return {score:Math.round(factors.reduce((sum,item)=>sum+item.score,0)/factors.length),is_heuristic:true,accuracy:exact?"source_quote":text?"user_supplied":"unverified",factors,warning:"Explainable editing heuristic only. No statistical retention prediction, event recognition, or view-count guarantee."};
}

function nearbyFrame(analysis:SourceAnalysis,time:number){return analysis.frames.reduce<SourceAnalysis["frames"][number]|undefined>((best,frame)=>!best||Math.abs(frame.timestamp-time)<Math.abs(best.timestamp-time)?frame:best,undefined);}
function windowScore(analysis:SourceAnalysis,start:number,length:number){
  const frames=analysis.frames.filter(frame=>frame.timestamp>=start&&frame.timestamp<=start+length);
  const visual=frames.length?frames.reduce((sum,frame)=>sum+frame.change*.45+frame.sharpness*.2+(1-Math.abs(frame.brightness-.5)*2)*.15,0)/frames.length:0;
  const captions=analysis.cues.filter(cue=>cue.end>start&&cue.start<start+length).reduce((sum,cue)=>sum+Math.max(0,Math.min(start+length,cue.end)-Math.max(start,cue.start)),0)/Math.max(1,length);
  return visual+Math.min(1,captions)*.2;
}
function rangeOverlap(a:{start:number;end:number},b:{start:number;end:number}){return Math.max(0,Math.min(a.end,b.end)-Math.max(a.start,b.start));}

export function diversityAssessment(concept:CreativeConcept,history:CreativeConcept[]):CreativeConcept["diversity"]{
  let similarity=0;const repeated=new Set<string>();
  for(const old of history){
    const common=concept.shots.reduce((sum,shot)=>sum+old.shots.filter(other=>other.source_id===shot.source_id).reduce((value,other)=>value+rangeOverlap(shot,other),0),0);
    const footage=Math.min(1,common/Math.max(1,Math.min(concept.duration,old.duration)));
    const opening=concept.shots[0]&&old.shots[0]&&concept.shots[0].source_id===old.shots[0].source_id&&Math.abs(concept.shots[0].start-old.shots[0].start)<1;
    const story=concept.kind===old.kind;
    const composition=concept.shots.map(shot=>shot.composition).join(",")===old.shots.map(shot=>shot.composition).join(",");
    const hooks=normalized(concept.hook)&&normalized(concept.hook)===normalized(old.hook);
    const candidate=footage*.65+Number(opening)*.15+Number(story)*.1+Number(composition)*.05+Number(Boolean(hooks))*.05;
    similarity=Math.max(similarity,candidate);
    if(opening)repeated.add("Opening source range");
    if(hooks)repeated.add("Text hook");
    if(story&&footage>.65)repeated.add("Narrative and selected footage");
    if(composition&&footage>.65)repeated.add("Visual composition");
  }
  return {similarity:Math.round(similarity*100),repeated_patterns:[...repeated],warning:similarity>.82?"This concept substantially repeats a prior selection. Choose different source material or make meaningful story/timeline changes; changing colors does not establish originality.":null};
}

function makeShot(analysis:SourceAnalysis,source:SourceDescriptor,start:number,end:number,index:number,total:number,styleId:StyleId,secondary?:SourceDescriptor):Shot{
  const frame=nearbyFrame(analysis,(start+end)/2);const style=styleById(styleId);
  const cues=analysis.cues.filter(cue=>cue.end>start&&cue.start<end);
  const role=index===0?"hook":index===total-1?"payoff":index===1?"context":"development";
  const duration=end-start;
  return {id:uid(),source_id:source.id,role,start:round(start),end:round(end),crop_x:clamp(frame?.focus_x??.5,0,1),crop_y:clamp(frame?.focus_y??.5,0,1),zoom:1,
    composition:style.composition,transition:style.transition,effect:style.effect,overlay_text:"",overlay_position:"top",
    rationale:role==="hook"?"Open on a real source beat. Verify its standalone context before export.":role==="payoff"?"Conclude with later source footage; confirm that it resolves the actual sequence.":"Preserve chronological source context around the selected moment.",
    source_evidence:[`Source interval: ${start.toFixed(2)}–${end.toFixed(2)} seconds`,...(frame?[`Measured nearby frame at ${frame.timestamp.toFixed(2)}s; visual change ${frame.change.toFixed(3)}. Focal position is a low-confidence visual proxy.`]:[]),...cues.slice(0,2).map(cue=>`Caption cue: ${cue.text}`)],thumbnail:frame?.thumbnail||"",
    ...(secondary?{secondary_source_id:secondary.id,secondary_start:round(clamp(start,0,Math.max(0,secondary.media_info.duration-duration)))}:{}),
  };
}

function chosenSize(source:SourceDescriptor,options:CreativeOptions):{width:1080|720|540;height:1920|1280|960}{
  const height=options.output_height||(source.media_info.height>=1600?1920:source.media_info.height>=1000?1280:960);
  return {width:height===1920?1080:height===1280?720:540,height};
}

function fullConcept(input:GenerateInput,kind:CreativeConcept["kind"],ranges:{start:number;end:number}[],styleId:StyleId):CreativeConcept{
  const {source,analysis,rules,options={}}=input;
  const style=styleById(styleId);const secondary=(input.originalSources||[]).find(value=>value.id!==source.id);
  const shots=ranges.filter(range=>range.end-range.start>=.35).map((range,index,all)=>makeShot(analysis,source,range.start,range.end,index,all.length,styleId,style.requires_secondary?secondary:undefined));
  const duration=round(shots.reduce((sum,shot)=>sum+shot.end-shot.start,0));
  const first=shots[0]; const cue=analysis.cues.find(item=>item.end>(first?.start||0)&&item.start<(first?.start||0)+3);
  const hook=cue?cue.text.slice(0,140):"";
  const title=String(options.title||source.filename.replace(/\.[^.]+$/,""));
  const size=chosenSize(source,options);
  const name=kind==="high-engagement"?"High Engagement":kind==="cinematic"?"Cinematic":"Creative Storytelling";
  const distinct=kind==="high-engagement"?"A compact contiguous source window with concise cuts around measured visual changes; source order is preserved.":kind==="cinematic"?"A different source window with sustained takes and restrained transitions; the full source frame can be preserved where useful.":"Chronological excerpts from earlier, middle, and later source material form a proposed context/development/conclusion; you verify whether the story is truthful.";
  const concept:CreativeConcept={id:uid(),title:`${name} · ${title}`.slice(0,160),kind,audience:options.audience||"Audience chosen by the editor; verify campaign audience restrictions",duration,hook,hook_alternatives:[hook,options.title||"",cue?"":title].filter((value,index,all)=>Boolean(value)&&all.indexOf(value)===index),hook_assessment:evaluateHook(hook,analysis,first?.start||0),shots,style_id:styleId,
    caption_settings:captionSettings({animation:style.caption_animation,...options.captions}),audio_treatment:options.audio||"source",ending_strategy:kind==="creative-storytelling"?"End on a later source excerpt; confirm a genuine payoff without inventing a result.":"Finish the selected source beat without a repeated outro or promotional footer.",distinct_reason:distinct,compliance_notes:["All footage timestamps reference the actual supplied source.","Source framing follows low-confidence visual metrics, not face or object recognition.",...(rules.automated_clipping_allowed===false||rules.ai_generated_allowed===false?["Assisted manual editing is mandatory. Record your actual creative decisions; the campaign restriction is not bypassed."]:[]),...(size.height>source.media_info.height?["The selected export is larger than the source height. Lower the output size where possible; upscaling does not restore detail."]:[])],recommendation_reason:"",mode:"assisted_manual",manual_decisions:options.manual_decisions||"",generation_method:"local_assisted",provider_status:"not_configured",diversity:{similarity:0,repeated_patterns:[],warning:null},output_width:size.width,output_height:size.height,selected_title:title.slice(0,100),description:options.description||"",hashtags:options.hashtags||[],created_at:new Date().toISOString()};
  concept.diversity=diversityAssessment(concept,input.history||[]);
  return concept;
}

export function generateConcepts(input:GenerateInput){
  const {source,analysis,rules,options={}}=input;
  if(source.id!==analysis.source_id||![source.media_info.duration,analysis.duration].every(Number.isFinite)||analysis.duration<=0||Math.abs(source.media_info.duration-analysis.duration)>.25)throw new Error("Analyze the selected real source before creating concepts.");
  if(!analysis.frames.length)throw new Error("Representative source frames are required. Analyze the video or choose a readable source.");
  if(analysis.frames.some(frame=>![frame.timestamp,frame.change,frame.motion,frame.focus_x,frame.focus_y,frame.brightness,frame.sharpness].every(Number.isFinite)||frame.timestamp<0||frame.timestamp>analysis.duration||[frame.change,frame.motion,frame.focus_x,frame.focus_y,frame.brightness,frame.sharpness].some(value=>value<0||value>1)))throw new Error("Source analysis contains invalid measured frame values.");
  if(analysis.scene_changes.some(time=>!Number.isFinite(time)||time<0||time>analysis.duration)||analysis.cues.some(cue=>![cue.start,cue.end].every(Number.isFinite)||cue.start<0||cue.end<=cue.start||cue.end>analysis.duration+.05||typeof cue.text!=="string"))throw new Error("Source analysis contains invalid source timestamps or caption cues.");
  if(options.title&&options.title.length>100||options.description&&options.description.length>2000||options.hashtags&&(options.hashtags.length>30||options.hashtags.some(tag=>typeof tag!=="string"||!/^#[\p{L}\p{N}_]+$/u.test(tag))))throw new Error("Supply a title of at most 100 characters, a description of at most 2,000 characters, and up to 30 valid hashtags.");
  const maximum=Math.min(180,analysis.duration,rules.max_duration??180);const minimum=Math.max(1,rules.min_duration??1);
  const limitations=[...analysis.limitations,"Concepts use measured visual changes and supplied caption cues. They are assisted editing proposals, not semantic AI analysis or viral predictions."];
  if(maximum<minimum)return {concepts:[],recommended_id:null,recommendation:"The source cannot satisfy the supplied campaign duration bounds.",limitations,generation_method:"local_assisted" as const,analysis_method:"local_measured" as const,provider_status:"not_configured" as const,unavailable_reasons:["Source material is shorter than the campaign minimum or the duration bounds contradict."]};
  const requested=Number(options.duration??30);if(!Number.isFinite(requested)||requested<=0)throw new Error("Choose a valid preferred duration.");
  const length=clamp(requested,minimum,maximum);const candidates=[0,...analysis.scene_changes,...analysis.frames.map(frame=>frame.timestamp)].map(time=>clamp(time-length*.35,0,Math.max(0,analysis.duration-length)));
  const variation=Math.max(0,Math.floor(options.variation||0));
  const ranked=[...new Set(candidates.map(round))].sort((left,right)=>windowScore(analysis,right,length)-windowScore(analysis,left,length)||left-right);
  const primary=ranked[variation%ranked.length]||0;
  const cuts=[...new Set(analysis.scene_changes.filter(time=>Number.isFinite(time)&&time>primary+1&&time<primary+length-1))].sort((a,b)=>a-b).filter((time,index,all)=>index===0||time-all[index-1]>=.75);
  const step=options.pace==="relaxed"?7:options.pace==="energetic"?3:4.5;
  const count=Math.min(5,Math.max(1,Math.floor(length/step)));
  const boundaries=[primary,...(cuts.length?cuts.slice(0,count-1):Array.from({length:count-1},(_,index)=>primary+(index+1)*length/count)),primary+length].sort((a,b)=>a-b);
  const aRanges=boundaries.slice(0,-1).map((start,index)=>({start,end:boundaries[index+1]}));
  const auto=recommendStyle(analysis,rules);
  const explicit=options.style&&options.style!=="auto"?options.style:undefined;
  const concepts:CreativeConcept[]=[fullConcept(input,"high-engagement",aRanges,explicit||auto.id)];
  const unavailable:string[]=[];
  if(analysis.duration>=Math.max(8,length*1.25)){
    const stable=[...ranked].sort((left,right)=>{
      const penalty=(start:number)=>rangeOverlap({start,end:start+length},{start:primary,end:primary+length})/length;
      const activity=(start:number)=>analysis.frames.filter(frame=>frame.timestamp>=start&&frame.timestamp<=start+length).reduce((sum,frame)=>sum+frame.change,0);
      return penalty(left)*3+activity(left)-penalty(right)*3-activity(right);
    });
    const start=stable[0]??Math.max(0,analysis.duration-length);const split=length>=12?2:1;
    concepts.push(fullConcept(input,"cinematic",Array.from({length:split},(_,index)=>({start:start+index*length/split,end:start+(index+1)*length/split})),explicit||"cinematic-gaming"));
  }else unavailable.push("The source is too short to propose a substantially different cinematic source window. One honest proposal is preferable to cosmetic duplicates.");
  if(analysis.duration>=Math.max(15,length*1.5)){
    const beat=length/3;const middle=clamp(analysis.duration*.5-beat*.5,beat,Math.max(beat,analysis.duration-2*beat));
    concepts.push(fullConcept(input,"creative-storytelling",[{start:0,end:beat},{start:middle,end:middle+beat},{start:analysis.duration-beat,end:analysis.duration}],explicit||(analysis.cues.length>=3?"interactive-tutorial":"minimal-premium")));
  }else unavailable.push("There is not enough source span for a distinct context/development/conclusion proposal. Add longer or original footage rather than inventing a narrative.");
  for(const concept of concepts){
    concept.diversity=diversityAssessment(concept,[...(input.history||[]),...concepts.filter(other=>other.id!==concept.id)]);
    concept.compliance_notes.push(...validateConcept(concept,[source,...(input.originalSources||[])],rules).checks.filter(check=>check.status!=="PASS").map(check=>check.detail));
  }
  const available=concepts.filter(concept=>!concept.diversity.warning);
  const recommended=(available.length?available:concepts).reduce((best,concept)=>!best||concept.hook_assessment.score-concept.diversity.similarity*.2>best.hook_assessment.score-best.diversity.similarity*.2?concept:best,undefined as CreativeConcept|undefined);
  if(recommended)recommended.recommendation_reason="Recommended as an editable starting point because its opening has stronger measured/readability signals and less overlap with prior concepts. This does not predict views or establish narrative accuracy.";
  return {concepts,recommended_id:recommended?.id||null,recommendation:recommended?.recommendation_reason||"Review the source before choosing a concept.",limitations,unavailable_reasons:unavailable,generation_method:"local_assisted" as const,analysis_method:"local_measured" as const,provider_status:"not_configured" as const};
}

export function toEditPlan(concept:CreativeConcept,source:SourceDescriptor,rules:Row):Row{
  const primary=concept.shots.filter(shot=>shot.source_id===source.id);
  if(!primary.length)throw new Error("Keep at least one real primary-source shot in this storyboard.");
  if(concept.shots.some(shot=>![shot.start,shot.end,shot.crop_x,shot.crop_y,shot.zoom].every(Number.isFinite)||shot.start<0||shot.end<=shot.start||shot.crop_x<0||shot.crop_x>1||shot.crop_y<0||shot.crop_y>1||shot.zoom<1||shot.zoom>1.5)||primary.some(shot=>shot.end>source.media_info.duration+.001))throw new Error("The storyboard contains invalid source times or framing boundaries.");
  const start=Math.min(...primary.map(shot=>shot.start)),end=Math.max(...primary.map(shot=>shot.end));
  const caption=captionSettings(concept.caption_settings);
  return {title:concept.selected_title||concept.title.slice(0,100),start,end,hook:concept.hook,show_hook:Boolean(concept.hook),rationale:concept.distinct_reason,content_type:"general",scenes:concept.shots.map(shot=>({...shot})),subtitle_style:concept.style_id==="high-energy-action"?"bold":"clean",subtitles_enabled:caption.enabled,edit_dna:{hook_structure:concept.hook||"Source opening; no invented text hook",scene_order:concept.shots.map(shot=>shot.role).join(" → "),cut_timing:concept.shots.map(shot=>`${shot.source_id}:${shot.start.toFixed(2)}–${shot.end.toFixed(2)}`).join("; "),framing:concept.shots.map(shot=>shot.composition).join(", "),typography:styleById(concept.style_id).typography,subtitle_treatment:"Supplied cue timing with safe-zone animation; no fabricated word alignment",visual_effects:concept.shots.map(shot=>shot.effect).join(", "),audio_treatment:concept.audio_treatment,ending_structure:concept.ending_strategy},scores:{hook_strength:0,engagement_potential:0,clarity:0,standalone_context:0,campaign_relevance:0},transcript_excerpt:"",semantic_notes:concept.compliance_notes,generation_method:"local_assisted",score_origin:"not_scored",manual_metadata:{title:concept.selected_title||source.filename,description:concept.description,hashtags:concept.hashtags},style_id:concept.style_id,caption_settings:caption,audio_treatment:concept.audio_treatment,output_width:concept.output_width,output_height:concept.output_height,creative_concept:structuredClone(concept),assisted_manual_required:rules.automated_clipping_allowed===false||rules.ai_generated_allowed===false,manual_decisions:concept.manual_decisions};
}

/** Regenerate one unrelated section without silently overwriting manual shots. */
export function mergeConceptSection(existing:CreativeConcept,replacement:CreativeConcept,section:"hook"|"metadata"|"style"|"storyboard",confirmManualOverwrite=false):CreativeConcept{
  if(section==="storyboard"&&(existing.user_modified||existing.shots.some(shot=>shot.manual_modified||shot.locked))&&!confirmManualOverwrite)throw new Error("This storyboard contains manual changes. Confirm replacement or regenerate another section.");
  if(section==="hook")return {...existing,hook:replacement.hook,hook_alternatives:replacement.hook_alternatives,hook_assessment:replacement.hook_assessment};
  if(section==="metadata")return {...existing,selected_title:replacement.selected_title,description:replacement.description,hashtags:replacement.hashtags};
  if(section==="style")return {...existing,style_id:replacement.style_id,caption_settings:replacement.caption_settings,shots:existing.shots.map(shot=>shot.locked?shot:{...shot,composition:styleById(replacement.style_id).composition,transition:styleById(replacement.style_id).transition,effect:styleById(replacement.style_id).effect})};
  return {...replacement,id:existing.id,manual_decisions:existing.manual_decisions,user_modified:false};
}
