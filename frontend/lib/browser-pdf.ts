/** PDF text is read on this device; scripts/actions and remote URLs are never run. */
export async function readRulesDocument(file:File):Promise<string>{
  if(file.size>15*1024*1024)throw new Error('Rules files are limited to 15 MB.');
  if(/\.txt$/i.test(file.name))return (await file.text()).slice(0,100000);
  if(!/\.pdf$/i.test(file.name))throw new Error('Upload PDF or TXT rules.');
  const pdf=await import('pdfjs-dist/legacy/build/pdf.mjs');
  pdf.GlobalWorkerOptions.workerSrc=new URL(`${process.env.NEXT_PUBLIC_BASE_PATH||''}/pdf/pdf.worker.min.mjs`,location.origin).href;
  const task=pdf.getDocument({data:new Uint8Array(await file.arrayBuffer()),useSystemFonts:true,disableFontFace:true,useWasm:false});
  const doc=await task.promise;
  try{
    if(doc.numPages>80)throw new Error('Rules PDFs are limited to 80 pages.');
    let text='';
    for(let n=1;n<=doc.numPages;n++){
      const content=await (await doc.getPage(n)).getTextContent();
      text+=content.items.map(item=>'str' in item?item.str+('hasEOL' in item&&item.hasEOL?'\n':' '):'').join('')+'\n';
      if(text.length>100000)throw new Error('The PDF contains too much text. Supply the relevant rules pages.');
    }
    if(!text.trim())throw new Error('This PDF has no readable text. Paste its rules or upload a text-based PDF; scanned pages need OCR.');
    return text;
  }finally{await task.destroy();}
}
