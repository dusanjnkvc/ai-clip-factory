import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const environment={...process.env,NEXT_TELEMETRY_DISABLED:'1',NEXT_PUBLIC_BROWSER_MODE:'true',NEXT_PUBLIC_BASE_PATH:process.env.NEXT_PUBLIC_BASE_PATH??'/ai-clip-factory'};
for(const args of [['scripts/prepare-browser.mjs'],['node_modules/next/dist/bin/next','build']]){
  const result=spawnSync(process.execPath,args,{env:environment,stdio:'inherit'});
  if(result.status!==0)process.exit(result.status||1);
}
writeFileSync('out/.nojekyll','');
