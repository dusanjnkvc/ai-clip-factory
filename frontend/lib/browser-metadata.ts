import type {BrowserRow} from './browser-db';
import {enforceCampaignMetadata,PLATFORMS,type CaptionCue} from './browser-rules';

const stop=new Set('a an the and or but so of to in on at for with from this that these those it its is are was were be been being i you your we they my our me he she his her not no yes just really very can could would should will have has had do does did get got then there here what how when why who which now video clip source recording footage export final edited untitled moment watch mp4 mov webm mkv'.split(' '));
function compact(value:string,max:number){const text=value.replace(/\s+/g,' ').trim();return text.length<=max?text:text.slice(0,max-1).replace(/\s+\S*$/,'')+'…';}
function unique(values:string[]){return [...new Map(values.map(value=>[value.toLocaleLowerCase(),value])).values()];}
function topicFromFilename(filename:string){
  const words=filename.replace(/\.[^.]+$/,'').replace(/[a-f\d]{8}-[a-f\d-]{20,}/gi,' ').replace(/\b[a-f\d]{16,}\b/gi,' ').replace(/[_-]+/g,' ').replace(/\b\d+(?:mb|gb|kb)\b/gi,' ').replace(/\b\d{3,}\b/g,' ').split(/\s+/).filter(word=>word&&!stop.has(word.toLowerCase())&&!/^\d+$/.test(word));
  return compact(words.join(' '),60);
}

/** Free editorial proposals grounded in filenames and supplied speech, never
 * fabricated game events, live trend data, engagement scores or view forecasts. */
export function proposePublishing(source:BrowserRow,selection:BrowserRow={},cues:CaptionCue[]=[],rules:BrowserRow={},variation=0):BrowserRow{
  const start=Number(selection.start||0),end=selection.end==null?Math.min(Number(source.media_info?.duration||3600),start+30):Number(selection.end);
  const selected=cues.filter(cue=>cue.end>start&&cue.start<end&&cue.text.trim().length>=8);
  const ranked=[...selected].sort((a,b)=>((/[?!]/.test(b.text)?30:0)+Math.min(b.text.length,90))-((/[?!]/.test(a.text)?30:0)+Math.min(a.text.length,90)));
  const quote=ranked[0]?compact(ranked[0].text,72):'';
  const topic=topicFromFilename(String(source.filename||''));
  const titleIdeas=quote?[quote,`The moment behind “${compact(quote,62)}”`,`Your take: “${compact(quote,66)}”`]:topic?[`${topic} — watch this moment`,`Did you notice this in ${topic}?`,`${topic}: what caught your eye?`]:['Watch this moment closely','What caught your eye here?','Your take on this moment?'];
  const words=(topic+' '+selected.map(cue=>cue.text).join(' ')).match(/[\p{L}][\p{L}\p{N}]{2,}/gu)||[];
  const frequencies=new Map<string,{word:string;count:number}>();
  for(const word of words){const key=word.toLocaleLowerCase();if(!stop.has(key)){const existing=frequencies.get(key);frequencies.set(key,{word,count:(existing?.count||0)+1});}}
  const topicTags=[...frequencies.values()].sort((a,b)=>b.count-a.count).slice(0,4).map(item=>'#'+item.word[0].toLocaleUpperCase()+item.word.slice(1));
  const gaming=/\b(gameplay|gaming|minecraft|fortnite|valorant|counter strike|cs2|battlefield|call of duty|warzone|roblox|apex legends|gta|league of legends|rocket league)\b/i.test(topic);
  const basis=quote?'Selected subtitle cues and source filename':topic?'Source filename; no dialogue or event recognition':'No descriptive source context yet; broad editorial draft';
  const description=[quote?`“${quote}”`:topic?`A closer look at ${topic}.`:'One moment. Take a closer look.',quote&&topic?`From ${topic}.`:''].filter(Boolean).join('\n\n');
  const platforms=Object.fromEntries(PLATFORMS.map(platform=>{
    const hashtags=unique([...(rules.required_hashtags||[]),...(gaming?['#Gaming']:[]),...topicTags,platform==='youtube'?'#Shorts':platform==='instagram'?'#Reels':'#ShortVideo']).slice(0,30);
    const questions=['What caught your eye?','How would you describe this moment?','What would you replay?'];
    return [platform,{recommended_index:0,variants:[0,1,2].map((index)=>{
      const option=(index+variation)%3;
      return enforceCampaignMetadata({title:compact(titleIdeas[option],100),description:description+'\n\n'+questions[option],caption:description+'\n\n'+questions[(option+(platform==='tiktok'?1:0))%3],hashtags,keywords:[...frequencies.keys()].slice(0,6),opening_hook:quote||'Watch this moment closely',call_to_action:questions[option],score:0,provenance:'app_proposed',reasoning:`App-proposed editorial copy. Basis: ${basis}. Review for accuracy; no trend lookup or viral/view prediction.`},rules);
    })}];
  }));
  return {metadata:platforms,basis,quote,topic,requires_review:true};
}
