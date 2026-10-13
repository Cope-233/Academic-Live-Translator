(() => {
  'use strict';

  const selected = new Set();
  const TEXT = {
    'zh-CN': {
      selectAll:'全选', selected:n=>`已选择 ${n} 项`, batchExport:'批量导出 MD', batchDelete:'批量删除',
      export:'导出', exportMenu:'导出格式', markdown:'Markdown (.md)', txt:'文本 (.txt)', srt:'字幕 (.srt)',
      srtTranslation:'翻译字幕 (.srt)', json:'JSON (.json)', noSelection:'请先选择至少一个会话',
      deleteConfirm:n=>`确定删除选中的 ${n} 个会话？此操作会同时删除对应的录音和截图，且无法撤销。`,
      exportFailed:'导出失败', deleteFailed:'部分会话删除失败', exported:n=>`已导出 ${n} 个 Markdown 会话`,
      deleted:n=>`已删除 ${n} 个会话`, pickerFallback:'当前浏览器不支持选择保存路径，已使用浏览器默认下载方式。'
    },
    en: {
      selectAll:'Select all', selected:n=>`${n} selected`, batchExport:'Export MD ZIP', batchDelete:'Delete selected',
      export:'Export', exportMenu:'Export format', markdown:'Markdown (.md)', txt:'Text (.txt)', srt:'Subtitles (.srt)',
      srtTranslation:'Translated subtitles (.srt)', json:'JSON (.json)', noSelection:'Select at least one session first',
      deleteConfirm:n=>`Delete the selected ${n} sessions? Their recordings and screenshots will also be removed. This cannot be undone.`,
      exportFailed:'Export failed', deleteFailed:'Some sessions could not be deleted', exported:n=>`Exported ${n} Markdown sessions`,
      deleted:n=>`Deleted ${n} sessions`, pickerFallback:'This browser cannot choose a save path, so the normal browser download was used.'
    }
  };
  const FORMAT = {
    md:{ext:'.md',mime:'text/markdown'}, txt:{ext:'.txt',mime:'text/plain'}, srt:{ext:'.srt',mime:'application/x-subrip'},
    'srt-translation':{ext:'.translation.srt',mime:'application/x-subrip',pickerExt:'.srt'}, json:{ext:'.json',mime:'application/json'}
  };

  const lang = () => document.documentElement.lang === 'en' ? 'en' : 'zh-CN';
  const t = (key,...args) => { const v=TEXT[lang()][key] ?? TEXT['zh-CN'][key] ?? key; return typeof v==='function'?v(...args):v; };
  function notify(message){ const el=document.getElementById('toast'); if(!el)return; el.textContent=message; el.classList.add('show'); clearTimeout(el._libraryTimer); el._libraryTimer=setTimeout(()=>el.classList.remove('show'),2600); }
  function safeFilename(name){ return (String(name||'session').replace(/[\\/:*?"<>|\u0000-\u001f]/g,'_').replace(/[. ]+$/g,'').trim()||'session').slice(0,120); }
  function downloadBlob(blob,filename){ const url=URL.createObjectURL(blob),a=document.createElement('a'); a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000); }
  async function saveBlob(blob,filename,mime,pickerExt){
    if('showSaveFilePicker' in window && window.isSecureContext){
      try{
        const handle=await window.showSaveFilePicker({suggestedName:filename,types:[{description:'Academic Live Translator export',accept:{[mime||blob.type||'application/octet-stream']:[pickerExt||filename.slice(filename.lastIndexOf('.'))||'.dat']}}]});
        const writable=await handle.createWritable(); await writable.write(blob); await writable.close(); return true;
      }catch(error){ if(error?.name==='AbortError')return false; console.warn('File picker failed:',error); }
    }
    downloadBlob(blob,filename); notify(t('pickerFallback')); return true;
  }
  async function fetchExport(id,format){ const r=await fetch(`/api/sessions/${encodeURIComponent(id)}/export/${format}`); if(!r.ok)throw new Error(`${r.status} ${r.statusText}`); return r.blob(); }
  async function exportOne(row){
    const format=row.querySelector('.session-export-format')?.value||'md', meta=FORMAT[format]||FORMAT.md;
    const title=row.querySelector('strong')?.textContent||row.dataset.id, filename=`${safeFilename(title)}${meta.ext}`;
    try{ const blob=await fetchExport(row.dataset.id,format); await saveBlob(blob,filename,meta.mime,meta.pickerExt||meta.ext); }
    catch(error){ console.error(error); notify(`${t('exportFailed')}: ${error.message}`); }
  }

  const crcTable=(()=>{ const x=new Uint32Array(256); for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=(c&1)?(0xedb88320^(c>>>1)):(c>>>1);x[n]=c>>>0;}return x;})();
  function crc32(bytes){let c=0xffffffff;for(const b of bytes)c=crcTable[(c^b)&255]^(c>>>8);return(c^0xffffffff)>>>0;}
  const u16=(v,o,n)=>v.setUint16(o,n,true), u32=(v,o,n)=>v.setUint32(o,n>>>0,true);
  function dosStamp(){const d=new Date(),y=Math.max(1980,d.getFullYear());return{time:(d.getHours()<<11)|(d.getMinutes()<<5)|(d.getSeconds()>>1),date:((y-1980)<<9)|((d.getMonth()+1)<<5)|d.getDate()};}
  function makeZip(files){
    const enc=new TextEncoder(),locals=[],centrals=[],stamp=dosStamp(); let offset=0;
    for(const file of files){
      const name=enc.encode(file.name),data=file.data,crc=crc32(data),local=new Uint8Array(30+name.length+data.length),lv=new DataView(local.buffer);
      u32(lv,0,0x04034b50);u16(lv,4,20);u16(lv,6,0x0800);u16(lv,8,0);u16(lv,10,stamp.time);u16(lv,12,stamp.date);u32(lv,14,crc);u32(lv,18,data.length);u32(lv,22,data.length);u16(lv,26,name.length);u16(lv,28,0);local.set(name,30);local.set(data,30+name.length);locals.push(local);
      const central=new Uint8Array(46+name.length),cv=new DataView(central.buffer);u32(cv,0,0x02014b50);u16(cv,4,20);u16(cv,6,20);u16(cv,8,0x0800);u16(cv,10,0);u16(cv,12,stamp.time);u16(cv,14,stamp.date);u32(cv,16,crc);u32(cv,20,data.length);u32(cv,24,data.length);u16(cv,28,name.length);u16(cv,30,0);u16(cv,32,0);u16(cv,34,0);u16(cv,36,0);u32(cv,38,0);u32(cv,42,offset);central.set(name,46);centrals.push(central);offset+=local.length;
    }
    const centralSize=centrals.reduce((s,p)=>s+p.length,0),end=new Uint8Array(22),ev=new DataView(end.buffer);u32(ev,0,0x06054b50);u16(ev,4,0);u16(ev,6,0);u16(ev,8,files.length);u16(ev,10,files.length);u32(ev,12,centralSize);u32(ev,16,offset);u16(ev,20,0);
    return new Blob([...locals,...centrals,end],{type:'application/zip'});
  }
  function uniqueNames(items){const used=new Map();return items.map(item=>{const base=safeFilename(item.title),n=(used.get(base)||0)+1;used.set(base,n);return{...item,filename:`${base}${n>1?` (${n})`:''}.md`};});}
  function zipFilename(){const d=new Date(),p=n=>String(n).padStart(2,'0');return`ALT-markdown-export-${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.zip`;}
  async function batchExport(){
    if(!selected.size)return notify(t('noSelection'));
    const rows=[...document.querySelectorAll('#sessionList .session')].filter(r=>selected.has(r.dataset.id));
    const items=uniqueNames(rows.map(r=>({id:r.dataset.id,title:r.querySelector('strong')?.textContent||r.dataset.id})));
    if(!items.length)return notify(t('noSelection'));
    const btn=document.getElementById('libraryBatchExport'); if(btn)btn.disabled=true;
    try{const files=await Promise.all(items.map(async item=>{const blob=await fetchExport(item.id,'md');return{name:item.filename,data:new Uint8Array(await blob.arrayBuffer())};}));const saved=await saveBlob(makeZip(files),zipFilename(),'application/zip','.zip');if(saved)notify(t('exported',files.length));}
    catch(error){console.error(error);notify(`${t('exportFailed')}: ${error.message}`);}finally{updateToolbar();}
  }
  async function batchDelete(){
    if(!selected.size)return notify(t('noSelection')); const ids=[...selected]; if(!confirm(t('deleteConfirm',ids.length)))return;
    const results=await Promise.allSettled(ids.map(async id=>{const r=await fetch(`/api/sessions/${encodeURIComponent(id)}`,{method:'DELETE'});if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);}));
    const failed=results.filter(r=>r.status==='rejected').length,deleted=ids.length-failed; selected.clear(); notify(failed?`${t('deleteFailed')} (${failed})`:t('deleted',deleted)); document.getElementById('refreshSessionsBtn')?.click(); updateToolbar();
  }

  function ensureToolbar(){
    const toolbar=document.querySelector('#library .toolbar'); if(!toolbar||document.getElementById('libraryBatchActions'))return;
    const group=document.createElement('div'); group.id='libraryBatchActions';group.className='library-batch-actions';group.innerHTML='<label class="library-select-all"><input id="librarySelectAll" type="checkbox"><span class="label"></span></label><span id="librarySelectionCount" class="library-selection-count"></span><button id="libraryBatchExport" type="button"></button><button id="libraryBatchDelete" type="button" class="danger"></button>';toolbar.appendChild(group);
    group.querySelector('#librarySelectAll').addEventListener('change',e=>{for(const row of document.querySelectorAll('#sessionList .session')){const cb=row.querySelector('.session-select');if(!cb)continue;cb.checked=e.target.checked;e.target.checked?selected.add(row.dataset.id):selected.delete(row.dataset.id);}updateToolbar();});
    group.querySelector('#libraryBatchExport').addEventListener('click',batchExport);group.querySelector('#libraryBatchDelete').addEventListener('click',batchDelete);
  }
  function updateToolbar(){
    ensureToolbar(); const rows=[...document.querySelectorAll('#sessionList .session')],visible=new Set(rows.map(r=>r.dataset.id)); for(const id of [...selected])if(!visible.has(id))selected.delete(id);
    const all=document.getElementById('librarySelectAll'),count=document.getElementById('librarySelectionCount'),exp=document.getElementById('libraryBatchExport'),del=document.getElementById('libraryBatchDelete'),label=document.querySelector('.library-select-all .label');
    if(label)label.textContent=t('selectAll');if(count)count.textContent=t('selected',selected.size);if(exp){exp.textContent=t('batchExport');exp.disabled=!selected.size;}if(del){del.textContent=t('batchDelete');del.disabled=!selected.size;}
    if(all){const n=rows.filter(r=>selected.has(r.dataset.id)).length;all.checked=rows.length>0&&n===rows.length;all.indeterminate=n>0&&n<rows.length;}
  }
  function optionMarkup(){return`<option value="md">${t('markdown')}</option><option value="txt">${t('txt')}</option><option value="srt">${t('srt')}</option><option value="srt-translation">${t('srtTranslation')}</option><option value="json">${t('json')}</option>`;}
  function decorateRow(row){
    const id=row.dataset.id;if(!id)return;
    if(!row.querySelector('.session-select')){const cb=document.createElement('input');cb.type='checkbox';cb.className='session-select';cb.checked=selected.has(id);cb.setAttribute('aria-label',t('selectAll'));cb.addEventListener('change',()=>{cb.checked?selected.add(id):selected.delete(id);updateToolbar();});row.prepend(cb);}
    if(!row.querySelector('.library-extra-actions')){const actions=row.lastElementChild;if(!actions)return;const extra=document.createElement('span');extra.className='library-extra-actions';extra.innerHTML=`<select class="session-export-format" aria-label="${t('exportMenu')}">${optionMarkup()}</select><button class="session-export" type="button">${t('export')}</button>`;actions.insertBefore(extra,actions.firstChild);extra.querySelector('.session-export').addEventListener('click',()=>exportOne(row));}
  }
  function decorateList(){
    ensureToolbar();const rows=[...document.querySelectorAll('#sessionList .session')],visible=new Set(rows.map(r=>r.dataset.id));for(const id of [...selected])if(!visible.has(id))selected.delete(id);rows.forEach(decorateRow);updateToolbar();
  }
  function relabel(){
    for(const row of document.querySelectorAll('#sessionList .session')){const cb=row.querySelector('.session-select'),select=row.querySelector('.session-export-format'),button=row.querySelector('.session-export');if(cb)cb.setAttribute('aria-label',t('selectAll'));if(select){const value=select.value;select.innerHTML=optionMarkup();select.value=value;select.setAttribute('aria-label',t('exportMenu'));}if(button)button.textContent=t('export');}updateToolbar();
  }
  function installStyles(){
    if(document.getElementById('libraryActionsStyles'))return;const style=document.createElement('style');style.id='libraryActionsStyles';style.textContent='#library .toolbar{flex-wrap:wrap;gap:10px}.library-batch-actions{display:flex;align-items:center;gap:8px;margin-left:auto;flex-wrap:wrap}.library-select-all{display:flex;align-items:center;gap:6px;white-space:nowrap}.library-selection-count{font-size:13px;opacity:.7;min-width:74px}.session-select{flex:0 0 auto;width:17px;height:17px;margin:0 2px 0 0}#sessionList .session{gap:12px}#sessionList .session>div:last-child{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap}.library-extra-actions{display:inline-flex;align-items:center;gap:6px}.session-export-format{max-width:165px}.library-batch-actions button:disabled{opacity:.45;cursor:not-allowed}@media(max-width:800px){.library-batch-actions{width:100%;margin-left:0}#sessionList .session{align-items:flex-start}#sessionList .session>div:last-child{justify-content:flex-start}}';document.head.appendChild(style);
  }
  function init(){installStyles();ensureToolbar();const list=document.getElementById('sessionList');if(list)new MutationObserver(decorateList).observe(list,{childList:true});new MutationObserver(relabel).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});decorateList();}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
