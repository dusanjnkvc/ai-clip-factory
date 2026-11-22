/** Local Node rendering bridge. No Lambda, hosted renderer or paid API. */
import {readFile,mkdir,access} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {bundle} from '@remotion/bundler';
import {selectComposition,renderMedia} from '@remotion/renderer';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const request=JSON.parse(await readFile(process.argv[2],'utf8'));
const files=await Promise.all(['index.tsx','ClipComposition.tsx','BasicCaptions.tsx','EditorLayers.tsx'].map(f=>readFile(path.join(root,'remotion',f))));
const identity=createHash('sha256').update(Buffer.concat([...files,await readFile(path.join(root,'package-lock.json'))])).digest('hex').slice(0,20);
const output=path.resolve(process.argv[3]),cache=path.join(root,'..','.runtime','remotion-bundles',identity);
try{await access(path.join(cache,'index.html'));}catch{await mkdir(cache,{recursive:true});await bundle({entryPoint:path.join(root,'remotion','index.tsx'),outDir:cache,publicDir:path.join(root,'public')});}
const composition=await selectComposition({serveUrl:cache,id:'ClipFactory',inputProps:request.props});
await renderMedia({serveUrl:cache,composition,inputProps:request.props,outputLocation:output,codec:'h264',audioCodec:'aac',crf:20,concurrency:1,chromiumOptions:{gl:'swangle'},onProgress:({progress})=>process.stdout.write(JSON.stringify({progress:Math.round(progress*100)})+'\n')});
