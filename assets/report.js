'use strict';
const S=JSON.parse(document.getElementById('summary-data').textContent);
const L=document.getElementById('local-data')?JSON.parse(document.getElementById('local-data').textContent):null;
const socialSource=document.getElementById('social-source').textContent.trim();
const originalPublic=document.getElementById('public-source')?.textContent.trim()||'';
const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
const decode=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
let toastTimer;
function toast(s){const el=$('#toast');el.textContent=s;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),3000);}
function dialog(id){const d=document.getElementById(id);if(d){d.showModal();document.body.style.overflow='hidden';}}
$$('dialog').forEach(d=>{d.addEventListener('close',()=>document.body.style.overflow='');d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}});});
$$('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
function blobDownload(content,type,name){const u=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=u;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),30000);}
function socialSvg(){return decode(socialSource);}
function updatePreview(){const src='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(socialSvg())));$$('[data-social]').forEach(i=>i.src=src);}
function publicSummary(){return {...S};}
function publicHtml(){if(!originalPublic)return document.documentElement.outerHTML;const doc=new DOMParser().parseFromString(decode(originalPublic),'text/html');doc.getElementById('summary-data').textContent=JSON.stringify(publicSummary()).replaceAll('<','\\u003c');return '<!doctype html>\n'+doc.documentElement.outerHTML;}
function openPublic(){const u=URL.createObjectURL(new Blob([publicHtml()],{type:'text/html'}));window.open(u,'_blank','noopener');setTimeout(()=>URL.revokeObjectURL(u),120000);}
async function saveImage(){try{const image=new Image();const source=URL.createObjectURL(new Blob([socialSvg()],{type:'image/svg+xml'}));await new Promise((ok,fail)=>{image.onload=ok;image.onerror=fail;image.src=source});const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=630;canvas.getContext('2d').drawImage(image,0,0,1200,630);URL.revokeObjectURL(source);const blob=await new Promise(ok=>canvas.toBlob(ok,'image/png'));if(!blob)throw new Error('Image unavailable');blobDownload(blob,'image/png','brain-surgery-scan.png');}catch(e){blobDownload(socialSvg(),'image/svg+xml','brain-surgery-scan.svg');toast('Saved the vector card instead.');}}
function caption(){const prefix=S.example?'[Design example — illustrative results, not a real user audit]\n\n':'';if(S.state==='insufficient')return prefix+'I ran Brain Surgery on my AI setup. The scan found what can be measured and what still needs a cleaner test.';if(S.state==='unchanged')return prefix+`I ran Brain Surgery on my AI setup. The current setup matched the tested candidate on ${S.tasks} tasks.`;if(S.state==='degraded')return prefix+`I ran Brain Surgery on my AI setup. The current setup beat the tested candidate on ${S.tasks} tasks.`;return prefix+`I ran Brain Surgery on my AI setup.\n\nSame model. ${S.before_percent}% → ${S.after_percent}% test pass rate across ${S.tasks} of my tasks.\nTested changes, not applied yet.\n\nBrain Surgery by AGI Labs.`;}
async function copyText(text){try{await navigator.clipboard.writeText(text);toast('Copied.');}catch(e){const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.append(area);area.select();const ok=document.execCommand('copy');area.remove();if(ok)toast('Copied.');else{blobDownload(text,'text/plain','brain-surgery-caption.txt');toast('Saved the text instead.');}}}
const actions={
 share:()=>{updatePreview();dialog('share-dialog');},
 evidence:()=>dialog('evidence-dialog'),
 surgery:()=>dialog('surgery-dialog'),
 start:()=>dialog('start-dialog'),
 'public-preview':openPublic,
 'save-image':saveImage,
 'publish-preview':()=>{$('#share-dialog').close();$('#share-caption').textContent=caption();dialog('published-dialog');},
 'copy-caption':()=>copyText(caption()),
 'export-public':()=>blobDownload(publicHtml(),'text/html','brain-surgery-public.html'),
 'export-summary':()=>blobDownload(JSON.stringify(publicSummary(),null,2),'application/json','brain-surgery-summary.json'),
 'export-plan':()=>{if(L){blobDownload(JSON.stringify(L.plan,null,2),'application/json','brain-surgery-plan.json');toast('Plan exported. Your setup is unchanged.');}},
 'copy-start':()=>copyText('Run Brain Surgery. Scan my approved recent tasks and installed skills. Test changes in isolation. Do not apply changes or upload anything.')
};
$$('[data-action]').forEach(b=>b.addEventListener('click',()=>{const action=actions[b.dataset.action];if(action)action();}));
if(L&&$('#test-body')){L.pairs.forEach(p=>{const tr=document.createElement('tr');const td=document.createElement('td');td.textContent=p.title||p.workflow;const small=document.createElement('small');small.textContent=p.local_reference||'';td.append(small);tr.append(td);['before','after'].forEach(k=>{const c=document.createElement('td');c.textContent=p.valid?(p[k]?'Pass':'Fail'):'Not scored';c.className=p.valid?(p[k]?'pass':'fail'):'';tr.append(c);});$('#test-body').append(tr);});}
updatePreview();

/* Header retreats on the way down and comes back on the way up, so the share
   control is one gesture away without the bar sitting on top of the report. */
(function(){const nav=document.querySelector('.nav');if(!nav)return;
 let last=window.scrollY,ticking=false;
 function apply(){const y=window.scrollY;
  nav.classList.toggle('nav-lifted',y>8);
  if(y>last&&y>140)nav.classList.add('nav-away');
  else if(y<last)nav.classList.remove('nav-away');
  last=y;ticking=false;}
 addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(apply);}},{passive:true});
 apply();})();
