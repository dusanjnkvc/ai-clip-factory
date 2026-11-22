import assert from "node:assert/strict";
import { readFile, writeFile, mkdtemp, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test, { after, beforeEach } from "node:test";
import ts from "typescript";

// Exercise the production API, rule engine, and director together. Persistence
// and the media binary are isolated here; test-wasm.mjs encodes/decodes real media.
const temporary = await mkdtemp(path.join(tmpdir(), "acf-browser-api-tests-"));
await mkdir(path.join(temporary, "creative"));
after(() => rm(temporary, { recursive: true, force: true }));
const names = ["browser-api", "browser-rules", "browser-pdf", "browser-metadata", "remotion-plan", "editor-project", "browser-editor-api", "editor-assets", ...["types", "styles", "compliance", "director", "publishing", "index"].map(name => `creative/${name}`)];
for (const name of names) {
  const source = await readFile(new URL(`../lib/${name}.ts`, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
    .replace(/(from\s+|import\()(["'])(\.\.?\/[^"']+)\2/g, '$1$2$3.mjs$2')
    .replace(/from ["']fflate["']/, `from ${JSON.stringify(import.meta.resolve("fflate"))}`);
  await writeFile(path.join(temporary, name + ".mjs"), compiled);
}
await writeFile(path.join(temporary, "browser-db.mjs"), `
import { randomUUID } from "node:crypto";
const records = new Map(), blobs = new Map();
const clone = value => value === undefined ? undefined : structuredClone(value);
let claimHook;
export function reset() { records.clear(); blobs.clear(); claimHook = undefined; }
export function onClaim(action) { claimHook = action; }
export async function getRecord(table, id) { return clone(records.get(table + ":" + id)); }
export async function setRecord(table, value) { records.set(table + ":" + value.id, clone(value)); return clone(value); }
export async function listRecords(table) { return [...records.entries()].filter(([key]) => key.startsWith(table + ":")).map(([, value]) => clone(value)).reverse(); }
export async function modifyRecord(table, id, change) { const next = change(await getRecord(table, id)); return setRecord(table, next); }
export async function claimQueuedJob(id, runner) {
  const job = await getRecord("jobs", id);
  if (job?.status !== "queued") return undefined;
  if (claimHook) { const action = claimHook; claimHook = undefined; await action(); }
  return setRecord("jobs", { ...job, status:"processing", runner_id:runner, lease_until:Date.now() + 300000 });
}
export async function putBlob(key, blob) { blobs.set(key, blob); }
export async function getBlob(key) { const blob = blobs.get(key); if (!blob) throw new Error("Missing fixture media"); return blob; }
export async function mediaUrl(key) { await getBlob(key); return "blob:local-test/" + key; }
export const recordId = randomUUID;
export const timestamp = () => new Date().toISOString();
export async function audit(action, entity_id, detail) { return setRecord("audit", {id:recordId(),action,entity_id,detail}); }
`);
await writeFile(path.join(temporary, "browser-media.mjs"), `
export const renders = [];
export function resetMedia() { renders.length = 0; }
export async function inspectVideo() { throw new Error("Uploads are outside these API integration tests"); }
export async function renderBrowserClip(blob, plan, cues, mode, progress, sourceFiles) {
  renders.push({plan:structuredClone(plan),cues:structuredClone(cues),mode,sourceIds:Object.keys(sourceFiles)});
  await progress("Test media adapter", 50);
  return {blob:new Blob(["encoded-test-boundary"],{type:"video/mp4"}),media_info:{duration:plan.scenes.reduce((sum,scene)=>sum+scene.end-scene.start,0),width:plan.output_width||1080,height:plan.output_height||1920,codec:"h264",has_audio:true,decode_verified:true,subtitle_synchronized:true}};
}
`);
await writeFile(path.join(temporary, "browser-rendering.mjs"), `export {renderBrowserClip as renderClipForBrowser} from './browser-media.mjs';`);
const { browserApi, browserDownload } = await import(pathToFileURL(path.join(temporary, "browser-api.mjs")));
const db = await import(pathToFileURL(path.join(temporary, "browser-db.mjs")));
const media = await import(pathToFileURL(path.join(temporary, "browser-media.mjs")));
const { emptyRules, validateRules } = await import(pathToFileURL(path.join(temporary, "browser-rules.mjs")));
const {emptyEditor,newLayer,applyTemplate} = await import(pathToFileURL(path.join(temporary,'editor-project.mjs')));
const { generateConcepts, toEditPlan } = await import(pathToFileURL(path.join(temporary, "creative/index.mjs")));
const source = {id:"authorized-source",filename:"Owned source.mp4",storage_key:"sources/authorized.mp4",rights_confirmed:true,media_info:{duration:60,width:1920,height:1080,has_audio:true}};
const analysis = {source_id:source.id,fingerprint:"measured-fixture",duration:60,width:1920,height:1080,frames:Array.from({length:12},(_,index)=>({timestamp:index*5,thumbnail:"",change:.1,motion:.1,focus_x:.5,focus_y:.5,brightness:.5,sharpness:.5,focus_confidence:"low"})),scene_changes:[15,30,45],cues:[{start:2,end:5,text:"An exact supplied cue"}],limitations:["No semantic model"],warnings:[],method:"local_measured",analyzed_at:"2026-11-17T12:00:00Z",audio:{status:"unavailable",samples:[]}};
const rules = validateRules({...emptyRules(),allowed_platforms:["youtube"],min_duration:1,max_duration:40,draft_approval_required:false,evidence:[{source:"manual",quote:"Reviewed rules"}]});
const request = (value, method="POST") => ({method,body:JSON.stringify(value)});
function plan(overrides = {}, campaignRules = rules) {
  const concept = generateConcepts({source,analysis,rules:campaignRules,options:{duration:12,title:"Verified source edit",output_height:1920}}).concepts[0];
  return {...toEditPlan(concept,source,campaignRules),...overrides};
}
async function postJob(edit = plan(), extra = {}) {
  return browserApi("/jobs", request({source_id:source.id,campaign_id:"campaign",mode:"fast",clip_count:1,plan:edit,...extra}));
}
async function settled(id) {
  for (let attempt=0; attempt<100; attempt++) {
    const job = await db.getRecord("jobs", id);
    if (["completed","failed"].includes(job?.status)) { await new Promise(resolve=>setImmediate(resolve)); return job; }
    await new Promise(resolve=>setImmediate(resolve));
  }
  assert.fail("Local job did not reach a terminal state");
}
beforeEach(async () => {
  db.reset(); media.resetMedia();
  await db.setRecord("sources", source);
  await db.putBlob(source.storage_key, new Blob(["authorized fixture source"]));
  await db.setRecord("campaigns", {id:"campaign",name:"Reviewed campaign",rules});
});

test("the browser workspace is free and opens without a login", async () => {
  const health = await browserApi("/health"), user = await browserApi("/auth/me");
  assert.equal(health.free_mode,true); assert.equal(health.local_no_auth,true);
  assert.equal(health.external_calls_enabled,false); assert.equal(health.monthly_spend_limit_usd,0);
  assert.equal(user.local_workspace,true);
  assert.equal(health.max_upload_mb,1500);
});

test('browser upload accepts the 1500 MB boundary and rejects the next byte before media inspection',async()=>{
  const maximum=1500*1024*1024;
  function upload(size){
    const file=new File(['size-gate-fixture'],'owned.mp4',{type:'video/mp4'});
    Object.defineProperty(file,'size',{value:size});
    const form=new class extends FormData {get(key){return key==='file'?file:super.get(key);}};
    form.set('rights_confirmed','true');form.set('rights_note','Generated boundary test fixture');return form;
  }
  await assert.rejects(browserApi('/sources',{method:'POST',body:upload(maximum)}),/Uploads are outside these API integration tests/);
  await assert.rejects(browserApi('/sources',{method:'POST',body:upload(maximum+1)}),/1,500 MB/);
});

test('automatic publishing text needs no user title, caption or tags, and preserves campaign priority',async()=>{
  const campaignRules=validateRules({...rules,required_hashtags:['#CampaignFirst'],required_mentions:['@brand']});
  await db.setRecord('campaigns',{id:'campaign',name:'Rules',rules:campaignRules});
  await db.setRecord('sources',{...source,filename:'Minecraft gameplay.mp4'});
  await db.setRecord('subtitles',{id:source.id,cues:[{start:1,end:3,text:'How did that happen?'},{start:35,end:38,text:'Outside the selected clip'}]});
  const job=await browserApi('/jobs',request({source_id:source.id,campaign_id:'campaign',manual_selection:{start:0,end:8,metadata_mode:'automatic'}}));
  const done=await settled(job.id);assert.equal(done.status,'completed',done.error);
  const clip=(await db.listRecords('clips'))[0],options=clip.metadata_json.youtube.variants;
  assert.equal(new Set(options.map(v=>v.title)).size,3);
  for(const option of options){assert.equal(option.provenance,'app_proposed');assert.ok(option.description.startsWith('#CampaignFirst @brand\n\n'));assert.ok(option.hashtags.includes('#Gaming'));assert.ok(!JSON.stringify(option).includes('Outside the selected clip'));assert.equal(option.score,0);}
  assert.equal(clip.plan.metadata_origin,'app_proposed');
  const refreshed=await browserApi(`/clips/${clip.id}/regenerate-metadata`,request({}));
  assert.equal(refreshed.storage_key,clip.storage_key);assert.deepEqual(refreshed.plan,clip.plan);assert.equal(refreshed.current_version,clip.current_version+1);
});

test("director projects retain manual draft changes through save and reload", async () => {
  const draft = plan().creative_concept;
  const project = await browserApi("/director/projects", request({source_id:source.id,campaign_id:"campaign",analysis,concepts:[draft],draft}));
  const edited = {...draft,hook:"Editor verified opening",user_modified:true};
  const saved = await browserApi(`/director/projects/${project.id}`,request({draft:edited,concepts:[edited],manual_decision_note:"I reviewed the opening source context."},"PATCH"));
  const loaded = await browserApi(`/director/projects/${project.id}`);
  assert.equal(saved.id,project.id); assert.equal(saved.created_at,project.created_at);
  assert.deepEqual(loaded.draft,edited); assert.equal(loaded.manual_decision_note,"I reviewed the opening source context.");
  assert.equal((await browserApi("/director/projects")).length,1);
  await assert.rejects(browserApi("/director/projects",request({source_id:"missing",campaign_id:"campaign"})),/not available/);
});

test("preflight validates actual caption settings rather than a stale embedded concept", async () => {
  const edit = plan(); edit.caption_settings = {...edit.caption_settings,font_size:100};
  assert.equal(edit.creative_concept.caption_settings.font_size,64);
  await assert.rejects(postJob(edit),/Caption size/);
  assert.equal(media.renders.length,0); assert.equal((await db.listRecords("jobs")).length,0);
});

test("encoded settings and local assisted provenance survive the API render lifecycle", async () => {
  const edit = plan({output_width:540,output_height:960,audio_treatment:"mute"});
  edit.caption_settings = {...edit.caption_settings,font_size:72,animation:"pop"};
  const queued = await postJob(edit), job = await settled(queued.id);
  assert.equal(job.status,"completed",job.error);
  const [clip] = await browserApi("/clips");
  assert.equal(media.renders.length,1);
  assert.deepEqual(media.renders[0].sourceIds,[source.id]);
  assert.equal(clip.plan.creative_concept.output_height,960);
  assert.equal(clip.plan.creative_concept.audio_treatment,"mute");
  assert.equal(clip.plan.creative_concept.caption_settings.font_size,72);
  assert.equal(clip.generation_method,"local_assisted");
  assert.equal(clip.compliance.status,"REVIEW_REQUIRED");
  assert.equal(clip.compliance.publish_ready,false);
  assert.equal(clip.compliance.checks.find(check=>check.rule==="creative_context").status,"REVIEW_REQUIRED");
});

test("a campaign automation ban blocks rendering until human decisions are recorded", async () => {
  const restricted = {...rules,automated_clipping_allowed:false};
  await db.setRecord("campaigns", {id:"campaign",name:"Manual campaign",rules:restricted});
  await assert.rejects(postJob(plan({},restricted)),/Record the real manual decisions/);
  const queued = await postJob(plan({},restricted),{director:{manual_decision_note:"I reviewed context, chose the cuts, and adjusted each crop."}});
  assert.equal((await settled(queued.id)).status,"completed");
  const [clip] = await browserApi("/clips");
  assert.match(clip.plan.creative_concept.manual_decisions,/reviewed context/);
  assert.equal(clip.compliance.checks.find(check=>check.rule==="manual_editing").status,"REVIEW_REQUIRED");
});

test("required original footage and out-of-source cuts cannot reach the renderer", async () => {
  await db.setRecord("campaigns",{id:"campaign",name:"Original footage campaign",rules:{...rules,original_footage_required:true}});
  await assert.rejects(postJob(),/requires original creator footage/);
  await db.setRecord("campaigns",{id:"campaign",name:"Reviewed campaign",rules});
  const edit = plan(); edit.scenes[0].end=61;
  await assert.rejects(postJob(edit),/outside its authorized source range/);
  assert.equal(media.renders.length,0);
});

test("the worker repeats rights preflight after a job has been queued", async () => {
  db.onClaim(async()=>db.setRecord("sources",{...source,rights_confirmed:false}));
  const queued = await postJob(), finished = await settled(queued.id);
  assert.equal(finished.status,"failed"); assert.match(finished.error,/rights have not been confirmed/);
  assert.equal(media.renders.length,0); assert.equal((await db.listRecords("clips")).length,0);
});

test("export rechecks actual edited plan fields before starting a file download", async () => {
  const queued = await postJob(); assert.equal((await settled(queued.id)).status,"completed");
  const [clip] = await db.listRecords("clips");
  clip.plan.caption_settings.font_size=100;
  // Deliberately preserve the earlier valid embedded copy, as an editor might.
  clip.plan.creative_concept.caption_settings={...clip.plan.creative_concept.caption_settings,font_size:64};
  await db.setRecord("clips",clip);
  await assert.rejects(browserDownload(`/clips/${clip.id}/download`),/Caption size/);
});


test('uploaded text rules are extracted with filename evidence and render requirements',async()=>{
  const campaign=await browserApi('/campaigns',{method:'POST',body:JSON.stringify({name:'Document rules',brief:''})});
  const form=new FormData();form.append('file',new File(['Platforms: YouTube\nRequired hashtags: #First #Second\nRequired mentions: @creator\nRequired on-screen text: EXACT WORDING'],'rules.txt',{type:'text/plain'}));
  const updated=await browserApi('/campaigns/'+campaign.id+'/attachments',{method:'POST',body:form});
  assert.deepEqual(updated.rules.required_mentions,['@creator']);
  assert.deepEqual(updated.rules.required_on_video_text,['EXACT WORDING']);
  assert.equal(updated.rules.evidence.find(e=>e.field==='required_mentions').source,'rules.txt');
});

test('editor autosave, templates and asset references preserve clips without analysis or rendering',async()=>{
  const job=await postJob();assert.equal((await settled(job.id)).status,'completed');
  const [clip]=await browserApi('/clips');const edit=structuredClone(clip.plan);edit.editor=emptyEditor();
  const video=await browserApi('/editor/assets/from-source',request({source_id:source.id}));
  edit.editor.layers=[{...newLayer('video',5,video.id),opacity:.6,rotation:12}];
  const draft=await browserApi(`/editor/drafts/${clip.id}`,request({revision:0,plan:edit,metadata:clip.metadata},'PUT'));
  assert.equal(draft.revision,1);assert.equal(media.renders.length,1);assert.equal((await browserApi(`/clips/${clip.id}`)).current_version,1);
  assert.deepEqual((await browserApi(`/editor/drafts/${clip.id}`)).plan.editor.layers,edit.editor.layers);
  await assert.rejects(browserApi(`/editor/drafts/${clip.id}`,request({revision:0,plan:edit,metadata:clip.metadata},'PUT')),/another window/);
  await assert.rejects(browserApi(`/editor/assets/${video.id}`,{method:'DELETE'}),/used by a clip/);
  const template=await browserApi('/editor/templates',request({name:'Reusable design',duration:12,editor:edit.editor,campaign_id:'campaign'}));
  assert.equal(applyTemplate(template.editor,3,12).layers[0].end,3);
  edit.editor.layers[0].asset_id='not-owned';
  await assert.rejects(browserApi(`/editor/drafts/${clip.id}`,request({revision:1,plan:edit,metadata:clip.metadata},'PUT')),/owned editor record/);
  assert.equal(media.renders.length,1);
});

test('gallery Remotion previews resolve current owned media rather than expired render URLs',async()=>{
  const job=await postJob();await settled(job.id);const [clip]=await db.listRecords('clips');
  const video=await browserApi('/editor/assets/from-source',request({source_id:source.id}));clip.plan.editor=emptyEditor();clip.plan.editor.layers=[newLayer('video',5,video.id)];
  clip.media_info.remotion_base_key='owned-clean-base';clip.media_info.remotion_props={assets:{},hook:'Existing hook'};
  await db.putBlob('owned-clean-base',new Blob(['base']));await db.setRecord('clips',clip);
  const props=await browserApi(`/clips/${clip.id}/remotion`);assert.equal(props.assets[video.id],'blob:local-test/'+source.storage_key);assert.equal(props.videoUrl,'blob:local-test/owned-clean-base');
});

test('duplicated editable projects preserve independent media and clear approval',async()=>{
  const job=await postJob();await settled(job.id);const [clip]=await db.listRecords('clips');
  const result=await browserApi(`/editor/drafts/${clip.id}/duplicate`,{method:'POST'}),copy=await browserApi(`/clips/${result.id}`);
  assert.notEqual(copy.id,clip.id);assert.equal(copy.current_version,1);assert.equal(copy.draft_approved,false);
  assert.notEqual(copy.storage_key,clip.storage_key);assert.equal(media.renders.length,1);assert.deepEqual(copy.plan,clip.plan);
});

test('publication edits stay attached to a newly rendered version and stale reviews fail',async()=>{
  const job=await postJob();await settled(job.id);const [clip]=await browserApi('/clips');const metadata=structuredClone(clip.metadata);
  metadata.youtube.variants[0].title='My corrected publication title';
  const edited=await browserApi(`/clips/${clip.id}/regenerate`,request({plan:clip.plan,metadata}));assert.equal((await settled(edited.id)).status,'completed');
  assert.equal((await browserApi(`/clips/${clip.id}`)).metadata.youtube.variants[0].title,'My corrected publication title');
  await assert.rejects(browserApi(`/clips/${clip.id}/review`,request({version:1,note:'Stale review cannot affect the new version.'})),/changed/);
});
