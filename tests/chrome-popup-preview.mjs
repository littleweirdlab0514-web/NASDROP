// Local visual fixture only. No NAS requests or real credentials are used.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
const root=new URL('../chrome-extension/',import.meta.url);
const mock=`
let previewJobs=['downloading','paused','completed','stopping'].map((status,i)=>({id:'preview'+i,name:('Example.Long.Multilingual.파일名.1080p.').repeat(3)+'.zip',status,size:356000000,downloaded:1900000,extract:true}));
Object.defineProperty(navigator,'language',{value:new URLSearchParams(location.search).get('lang')||'ko'});
window.chrome={runtime:{connect:()=>({disconnect(){}}),sendMessage:async m=>{
  if(m.type==='savePreferences')for(const key of ['autoExtract','language'])if(m[key]!==undefined)localStorage.setItem('preview-'+key,JSON.stringify(m[key]));
  const job=previewJobs.find(j=>j.id===m.id);
  if(m.type==='jobPause'&&job)job.status='paused';
  if(m.type==='jobResume'&&job)job.status='downloading';
  if(m.type==='jobDelete')previewJobs=previewJobs.filter(j=>j.id!==m.id);
  if(m.type==='getState'||m.type==='login')return {ok:true,result:{connected:!location.search.includes('loggedout'),baseUrl:'https://nas.example',language:JSON.parse(localStorage.getItem('preview-language')||'"auto"'),autoExtract:localStorage.getItem('preview-autoExtract')!=='false',jobs:previewJobs,status:{target:'/downloads',job_processing_options:true}}};
  return {ok:true,result:{jobs:previewJobs}};
}},tabs:{query:async()=>[]},permissions:{request:async()=>true}};
`;
const allowed=new Set(['popup.html','popup.css','popup.js','popup-poller.js','i18n.js','icons/nasdrop-48.png']);
createServer(async(req,res)=>{
  const name=new URL(req.url,'http://localhost').pathname.slice(1);
  if(name==='mock.js'){res.setHeader('Content-Type','text/javascript');res.end(mock);return;}
  if(!allowed.has(name)){res.writeHead(404);res.end();return;}
  let data=await readFile(new URL(name,root));
  if(name==='popup.html')data=data.toString().replace('<script src="popup-poller.js">','<script src="mock.js"></script><script src="popup-poller.js">');
  res.setHeader('Content-Type',name.endsWith('.html')?'text/html; charset=utf-8':name.endsWith('.css')?'text/css':name.endsWith('.png')?'image/png':'text/javascript');
  res.end(data);
}).listen(18791,'127.0.0.1',()=>console.log('Popup fixture: http://127.0.0.1:18791/popup.html'));
