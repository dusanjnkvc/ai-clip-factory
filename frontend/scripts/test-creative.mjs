import assert from "node:assert/strict";
import {readFile,writeFile,mkdtemp,unlink,rmdir} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import {pathToFileURL} from "node:url";
import test,{after} from "node:test";
import ts from "typescript";

const temporary=await mkdtemp(path.join(tmpdir(),"acf-creative-tests-"));
const names=["types","styles","compliance","director","publishing","index","analyzer"];
for(const name of names){
  const source=await readFile(new URL(`../lib/creative/${name}.ts`,import.meta.url),"utf8");
  const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText.replace(/from (["'])\.\/([^"']+)\1/g,'from "./$2.mjs"');
  await writeFile(path.join(temporary,name+".mjs"),compiled);
}
after(async()=>{for(const name of names)await unlink(path.join(temporary,name+".mjs"));await rmdir(temporary);});
const {generateConcepts,validateConcept,toEditPlan,evaluateHook,STYLES,captionSettings,publishingSuggestions,diversityAssessment,mergeConceptSection,classifyRequirements}=await import(pathToFileURL(path.join(temporary,"index.mjs")).href);
const {measureFramePixels,measuredSceneChanges}=await import(pathToFileURL(path.join(temporary,"analyzer.mjs")).href);
const source={id:"owned-source",filename:"Authorized source.mp4",rights_confirmed:true,media_info:{duration:120,width:1920,height:1080}};
const rules={allowed_platforms:["youtube"],min_duration:5,max_duration:40,required_hashtags:["#Campaign"],required_mentions:["@Brand"],required_disclosures:["Paid partnership"],required_branding:[],prohibited_content:[],audio_restrictions:[],permitted_source_material:[],required_links:[],evidence:[{field:"allowed_platforms",quote:"YouTube",source:"brief"}],uncertainties:[],contradictions:[],draft_approval_required:false};
function analysis(duration=120){return {source_id:source.id,fingerprint:"fixture",duration,width:1920,height:1080,frames:Array.from({length:20},(_,index)=>({timestamp:index*duration/20,thumbnail:`data:image/jpeg;base64,fixture-${index}`,change:index===7?.9:.12,motion:.2,focus_x:.5,focus_y:.5,brightness:.5,sharpness:.7,focus_confidence:"low"})),scene_changes:[12,25,42,67,86,106].filter(value=>value<duration),cues:[{start:4,end:9,text:"The supplied opening"},{start:30,end:35,text:"An exact caption phrase"},{start:78,end:82,text:"The source continues"}],limitations:["No semantic model is enabled."],warnings:[],method:"local_measured",analyzed_at:"2026-11-16T10:00:00Z",audio:{status:"unavailable",samples:[]}};}
function batch(options={},extra={}){return generateConcepts({source,analysis:analysis(),rules,options:{duration:20,title:"A verified source moment",...options},...extra});}
function concept(){return batch().concepts[0];}
function check(result,rule){const found=result.checks.find(item=>item.rule===rule);assert.ok(found,`Expected check ${rule}`);return found;}

test("a sufficiently long measured source yields three source-grounded concepts",()=>{
  const result=batch();assert.equal(result.concepts.length,3);assert.equal(result.generation_method,"local_assisted");assert.equal(result.provider_status,"not_configured");
  assert.deepEqual(new Set(result.concepts.map(item=>item.kind)),new Set(["high-engagement","cinematic","creative-storytelling"]));
  for(const item of result.concepts)for(const shot of item.shots){assert.equal(shot.source_id,source.id);assert.ok(shot.start>=0&&shot.end<=120&&shot.end>shot.start);assert.ok(shot.source_evidence.length);}
});
test("creative alternatives differ in actual selected footage and cut structure",()=>{
  const signatures=batch().concepts.map(item=>JSON.stringify(item.shots.map(shot=>[shot.source_id,shot.start,shot.end])));assert.equal(new Set(signatures).size,3);
});
test("very short footage returns fewer concepts instead of cosmetic duplicates",()=>{
  const short={...source,media_info:{...source.media_info,duration:3}};const measured=analysis(3);measured.cues=[];
  const result=generateConcepts({source:short,analysis:measured,rules:{...rules,min_duration:1,max_duration:3},options:{duration:2}});
  assert.equal(result.concepts.length,1);assert.ok(result.unavailable_reasons.length>=1);
});
test("analysis must belong to the selected real source",()=>assert.throws(()=>batch({}, {analysis:{...analysis(),source_id:"another-source"}}),/Analyze the selected/));
test("missing measured frames stop concept creation",()=>assert.throws(()=>batch({}, {analysis:{...analysis(),frames:[]}}),/frames are required/));
test("nonfinite frame measurements cannot become a render plan",()=>{const measured=analysis();measured.frames[0].change=NaN;assert.throws(()=>batch({}, {analysis:measured}),/invalid measured/);});
test("source facts and caption evidence must remain inside real source bounds",()=>{
  assert.throws(()=>batch({}, {source:{...source,media_info:{...source.media_info,duration:NaN}}}),/Analyze the selected/);
  for(const change of [{scene_changes:[NaN]},{scene_changes:[121]},{cues:[{start:0,end:121,text:"Out of source"}]},{cues:[{start:4,end:3,text:"Reversed cue"}]}])assert.throws(()=>batch({}, {analysis:{...analysis(),...change}}),/invalid source timestamps/);
});
test("campaign minimum longer than the source produces an explicit unavailable result",()=>{const result=batch({}, {rules:{...rules,min_duration:130,max_duration:150}});assert.equal(result.concepts.length,0);assert.match(result.recommendation,/cannot satisfy/);});
test("negative, reversed, out-of-source and nonfinite timestamps block render",()=>{
  for(const change of [{start:-1},{start:20,end:19},{end:130},{start:NaN}]){const item=concept();Object.assign(item.shots[0],change);assert.equal(validateConcept(item,[source],rules).render_allowed,false);}
});
test("unavailable source references are identified as missing footage",()=>{const item=concept();item.shots[0].source_id="missing";const result=validateConcept(item,[source],rules);assert.equal(result.render_allowed,false);assert.ok(result.missing_footage.includes("missing"));});
test("crop and animated crop endpoints stay within source bounds",()=>{
  for(const change of [{crop_x:-.1},{crop_y:1.1},{zoom:1.6},{crop_x_end:2},{crop_y_end:NaN}]){const item=concept();Object.assign(item.shots[0],change);assert.equal(validateConcept(item,[source],rules).render_allowed,false);}
});
test("caption safe zones, sizes, animation, and colors are validated",()=>{
  for(const invalid of [{safe_top:0},{safe_bottom:20},{font_size:150},{color:"red;exec"},{animation:"random"}])assert.throws(()=>captionSettings(invalid));
  assert.equal(captionSettings().safe_bottom,280);
});
test("style registry defines eight explicit whitelisted editorial styles",()=>{assert.equal(STYLES.length,8);assert.equal(new Set(STYLES.map(item=>item.id)).size,8);for(const style of STYLES){assert.ok(style.typography&&style.sound&&style.pacing);assert.ok(["cut","fade"].includes(style.transition));}});
test("split-screen cannot render with missing creator footage",()=>{const item=batch({style:"reaction-split-screen"}).concepts[0];const result=validateConcept(item,[source],rules);assert.equal(result.render_allowed,false);assert.equal(check(result,"split_footage").status,"FAIL");});
test("secondary footage timestamps are validated against their own duration",()=>{const second={id:"original",filename:"Creator.mp4",original_creator:true,media_info:{duration:2,width:1080,height:1920}};const item=batch({style:"comparison-vs"},{originalSources:[second]}).concepts[0];assert.equal(validateConcept(item,[source,second],rules).render_allowed,false);});
test("automation prohibition requires recorded human creative decisions",()=>{
  const restricted={...rules,automated_clipping_allowed:false};const item=batch({}, {rules:restricted}).concepts[0];
  assert.equal(validateConcept(item,[source],restricted).render_allowed,false);item.manual_decisions="I inspected context, recut the source and adjusted each shot.";
  const result=validateConcept(item,[source],restricted);assert.equal(result.render_allowed,true);assert.equal(result.publish_ready,false);assert.equal(check(result,"manual_creative_decisions").status,"REVIEW_REQUIRED");
});
test("required original footage blocks a source-only proposal",()=>{const result=validateConcept(concept(),[source],{...rules,original_footage_required:true});assert.equal(result.render_allowed,false);assert.ok(result.missing_footage.includes("verified original creator footage"));});
test("declared original footage still requires human verification",()=>{const original={...source,original_creator:true};const result=validateConcept(concept(),[original],{...rules,original_footage_required:true});assert.equal(check(result,"original_footage").status,"REVIEW_REQUIRED");assert.equal(result.publish_ready,false);});
test("prohibited music and AI voices are not asserted absent from unknown source audio",()=>{const result=validateConcept(concept(),[source],{...rules,music_allowed:false,ai_voice_allowed:false});assert.equal(check(result,"music_restriction").status,"REVIEW_REQUIRED");assert.equal(check(result,"ai_voice_restriction").status,"REVIEW_REQUIRED");});
test("changing colors and fonts cannot erase repeated source/story history",()=>{const old=concept();const changed=structuredClone(old);changed.caption_settings.color="#AABBCC";changed.style_id="retro-arcade";const result=diversityAssessment(changed,[old]);assert.ok(result.similarity>82);assert.ok(result.warning);});
test("unrelated regeneration preserves manual storyboard changes",()=>{const current=concept();current.user_modified=true;current.shots[0].manual_modified=true;current.shots[0].overlay_text="My verified note";const replacement=batch({variation:1}).concepts[0];const merged=mergeConceptSection(current,replacement,"hook");assert.deepEqual(merged.shots,current.shots);assert.throws(()=>mergeConceptSection(current,replacement,"storyboard"),/manual changes/);});
test("render plan carries structured parameters and manual decision evidence",()=>{const item=concept();item.manual_decisions="I reviewed every selected shot.";const plan=toEditPlan(item,source,rules);assert.equal(plan.generation_method,"local_assisted");assert.equal(plan.creative_concept.id,item.id);assert.equal(plan.manual_decisions,item.manual_decisions);assert.equal(plan.scenes[0].source_id,source.id);assert.ok([960,1280,1920].includes(plan.output_height));});
test("hook assessment explains uncertainty without invented retention predictions",()=>{const result=evaluateHook("An exact caption phrase",analysis(),30);assert.equal(result.accuracy,"source_quote");assert.equal(result.is_heuristic,true);assert.equal(result.factors.length,6);assert.match(result.warning,/No statistical retention prediction/);});
test("punctuation alone cannot be claimed as a verified source quote",()=>assert.equal(evaluateHook("!!!",analysis(),30).accuracy,"user_supplied"));
test("unknown paired-source permission remains an explicit human review",()=>{
  const second={id:"creator",filename:"Creator.mp4",original_creator:true,media_info:{duration:120,width:1080,height:1920}};
  const item=batch({style:"reaction-split-screen"},{originalSources:[second]}).concepts[0];
  assert.equal(check(validateConcept(item,[source,second],rules),"secondary_rights").status,"REVIEW_REQUIRED");
});
test("publishing suggestions preserve required text and real cover timestamps",()=>{
  const item=concept();const required={...rules,required_links:["https://example.com/campaign"]};
  for(const platform of ["youtube","tiktok","instagram"]){const result=publishingSuggestions(item,required,platform);assert.equal(result.variants.length,3);for(const variant of result.variants){assert.ok(variant.description.includes("Paid partnership"));assert.ok(variant.description.includes("https://example.com/campaign"));assert.ok(variant.hashtags.includes("#Campaign"));assert.ok(variant.cover_timestamp>=item.shots[0].start&&variant.cover_timestamp<=item.shots[0].end);}}
});
test("unsafe promotional links do not become publishing suggestions",()=>assert.throws(()=>publishingSuggestions(concept(),{...rules,required_links:["javascript:alert(1)"]},"youtube"),/HTTPS/));
test("campaign classifications distinguish prohibited automation and unclear rules",()=>{const fields=classifyRequirements({...rules,automated_clipping_allowed:false,uncertainties:["Check branding"]});assert.equal(fields.find(item=>item.field==="automated_clipping_allowed").classification,"prohibited");assert.equal(fields.find(item=>item.field==="uncertainties").classification,"unclear");});

test("pixel measurements distinguish a stable frame from actual luminance change",()=>{
  const black=new Uint8ClampedArray(5*5*4);const white=new Uint8ClampedArray(5*5*4).fill(255);
  const initial=measureFramePixels(black,5,5);const stable=measureFramePixels(black,5,5,initial.luma);const changed=measureFramePixels(white,5,5,initial.luma);
  assert.equal(initial.focus_confidence,"low");assert.equal(stable.change,0);assert.equal(stable.motion,0);assert.equal(stable.focus_x,.5);assert.equal(stable.focus_y,.5);
  assert.ok(changed.change>.99);assert.ok(changed.brightness>.99);assert.equal(changed.sharpness,0);
  assert.throws(()=>measureFramePixels(black,2,5),/complete sampled frame/);assert.throws(()=>measureFramePixels(black,5,5,new Float32Array(1)),/complete sampled frame/);
});

test("sampled scene changes require measured jumps and exclude the initial frame",()=>{
  assert.deepEqual(measuredSceneChanges([]),[]);assert.deepEqual(measuredSceneChanges([{timestamp:0,change:1}]),[]);
  const frames=[1,.01,.02,.03,.8,.02,.01].map((change,index)=>({timestamp:index*4,change}));
  assert.deepEqual(measuredSceneChanges(frames),[16]);assert.deepEqual(measuredSceneChanges(frames.map(frame=>({...frame,change:.04}))),[]);
});
