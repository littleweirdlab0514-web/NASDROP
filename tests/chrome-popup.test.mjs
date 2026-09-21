import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';
const root=new URL('../chrome-extension/',import.meta.url);
const i18nSource=await readFile(new URL('i18n.js',root),'utf8');
const pollSource=await readFile(new URL('popup-poller.js',root),'utf8');
const popupSource=await readFile(new URL('popup.js',root),'utf8');
const html=await readFile(new URL('popup.html',root),'utf8');
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('click expands controls and password together inside that card; repeat click collapses',async()=>{
  const second={id:'second123456',name:'second.zip',status:'paused',size:200,downloaded:80,extract:true};
  const h=popupHarness({extraJobs:[second]});await h.ready();
  const cards=h.nodes.get('jobs').children;
  assert.ok(cards.every(card=>card.children[1].classList.contains('hidden')));
  cards[1].children[0].events.click();
  assert.equal(cards[1].children[1].classList.contains('hidden'),false);
  assert.equal(h.nodes.get('job-detail').parentNode,cards[1]);
  assert.equal(h.nodes.get('job-detail').classList.contains('hidden'),false);
  const password=h.nodes.get('job-password');password.value='keep-private';password.events.input();
  await h.poll();
  assert.equal(h.nodes.get('jobs').children[1],cards[1]);
  assert.equal(h.nodes.get('job-password'),password);assert.equal(password.value,'keep-private');
  await inline(h,1,1).events.click();
  assert.equal(h.messages.find(m=>m.type==='jobResume').id,second.id);
  cards[1].children[0].events.click();
  assert.equal(cards[1].children[1].classList.contains('hidden'),true);
  assert.equal(h.nodes.get('job-detail').classList.contains('hidden'),true);
  assert.equal(password.value,'');
  cards[0].children[0].events.click();
  assert.equal(h.nodes.get('job-detail').parentNode,cards[0]);
  assert.equal(cards[1].children[1].classList.contains('hidden'),true);
});

test('inline action rechecks refreshed status before sending and unlocks after rejection',async()=>{
  const h=popupHarness({beforeJobs:job=>{job.status='extracting';}});await h.ready();
  await inline(h,0).events.click();
  assert.equal(h.messages.some(m=>m.type==='jobPause'),false);
  for(const index of [0,1,2])assert.equal(inline(h,index).disabled,true);
  const failed=popupHarness({actionError:true});await failed.ready();await inline(failed,0).events.click();
  assert.equal(inline(failed,0).disabled,false);
  assert.equal(failed.nodes.get('notice').textContent,'synthetic failure');
});

test('job cards have sibling summary and controls, not nested buttons',()=>{
  assert.match(popupSource,/const item=document.createElement\('div'\)/);
  assert.match(popupSource,/item.append\(summary,controls\)/);
  assert.ok(!html.includes('id="job-extract"'));
  assert.ok(!html.includes('id="job-detail-name"'));
  assert.ok(!html.includes('id="pause-job"'));
});

test('polling serializes slow reads, adapts idle/error intervals and stops on hidden/logout',async()=>{
  const c=vm.createContext({setTimeout,clearTimeout}); vm.runInContext(pollSource,c);
  let finish, calls=0, shown=0, visible=true;
  const timers=new Map(); let seq=0;
  const p=c.NASDropPolling.create({load:()=>{calls++;return new Promise(resolve=>finish=resolve);},onData:()=>shown++,onError(){},visible:()=>visible,schedule:(fn,ms)=>{timers.set(++seq,{fn,ms});return seq;},cancel:id=>timers.delete(id)});
  const first=p.start(); p.refresh(); p.refresh(); assert.equal(calls,1);
  finish({jobs:[{status:'downloading'}]}); await first;
  assert.equal([...timers.values()][0].ms,5000);
  const second=p.refresh(); finish({jobs:[]}); await second;
  assert.equal([...timers.values()][0].ms,15000);
  visible=false; p.visibilityChanged(); assert.equal(timers.size,0);
  visible=true; const pending=p.visibilityChanged(); p.stop(); finish({jobs:[]}); await pending;
  assert.equal(shown,2); assert.equal(timers.size,0);
});

test('errors back off to 60 seconds and auth expiration stops retries',async()=>{
  const c=vm.createContext({setTimeout,clearTimeout});vm.runInContext(pollSource,c);
  let status=0,delay; const errors=[];
  const p=c.NASDropPolling.create({load:async()=>{throw Object.assign(new Error('offline'),{status});},onData(){},onError:e=>errors.push(e),schedule:(_,ms)=>{delay=ms;return 1;},cancel:()=>{delay=null;}});
  await p.start();assert.equal(delay,10000);
  await p.refresh();assert.equal(delay,20000);
  await p.refresh();assert.equal(delay,40000);
  await p.refresh();assert.equal(delay,60000);
  status=401;await p.refresh();assert.equal(delay,null);assert.equal(errors.length,5);
});

const inline=(h,index,row=0)=>h.nodes.get('jobs').children[row].children[1].children[index];

function popupHarness({connected=true,modern=true,preferences={autoExtract:true},confirmAction=()=>true,actionError=false,extraJobs=[],beforeJobs=()=>{}}={}) {
  const nodes=new Map(), messages=[], timers=new Map();let timerID=0,deleted=false;
  const job={id:'abcdef012345',name:'archive.zip',status:'downloading',size:100,downloaded:10,extract:true};
  const jobs=[job,...extraJobs];
  function node() {
    const events={};const classes=new Set();
    return {value:'',textContent:'',checked:false,disabled:false,dataset:{},style:{},children:[],events,
      classList:{toggle(name,value){value ? classes.add(name):classes.delete(name);},add:n=>classes.add(n),remove:n=>classes.delete(n),contains:n=>classes.has(n)},
      append(...children){for(const child of children){child.remove();child.parentNode=this;this.children.push(child);}},
      remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(n=>n!==this);this.parentNode=null;}},
      replaceChildren(...children){for(const child of [...this.children])child.remove();this.append(...children);},setAttribute(){},
      addEventListener(name,fn){events[name]=fn;},
      requestSubmit(submitter){return this.events.submit({preventDefault(){},submitter});},
    };
  }
  for(const [,id]of html.matchAll(/id="([^"]+)"/g))nodes.set(id,node());
  const document={hidden:false,documentElement:{},getElementById:id=>nodes.get(id),querySelector:s=>nodes.get(s.slice(1)),querySelectorAll:()=>[],createElement:node,addEventListener(){}};
  const c=vm.createContext({URL,Date,Math,Number,Set,console,document,navigator:{language:'ko'},window:{addEventListener(){}},confirm:confirmAction,
    setTimeout:(fn,ms)=>{timers.set(++timerID,{fn,ms});return timerID;},clearTimeout:id=>timers.delete(id),
    chrome:{runtime:{connect:()=>({disconnect(){}}),sendMessage:async message=>{
      messages.push(message);
      if(['jobPause','jobResume','jobDelete'].includes(message.type)&&actionError)return {ok:false,error:'synthetic failure'};
      const target=jobs.find(j=>j.id===message.id);
      if(message.type==='jobPause')target.status='stopping';
      if(message.type==='jobResume')target.status='queued';
      if(message.type==='jobDelete')deleted=true;
      if(message.type==='savePreferences')for(const key of ['autoExtract','language'])if(message[key]!==undefined)preferences[key]=message[key];
      if(message.type==='getState'||message.type==='login')return {ok:true,result:{connected:message.type==='login'||connected,baseUrl:'https://nas.example',...preferences,jobs,status:{target:'/downloads',job_processing_options:modern}}};
      if(message.type==='getJobs'){beforeJobs(job);return {ok:true,result:{jobs:deleted?[]:jobs.map(j=>({...j}))}};}
      return {ok:true,result:{ok:true}};
    }},tabs:{query:async()=>[]},permissions:{request:async()=>true}},
  });
  vm.runInContext(i18nSource,c);vm.runInContext(pollSource,c);vm.runInContext(popupSource,c);
  return {nodes,messages,job,c,async ready(){await flush();},async poll(){vm.runInContext('polling.refresh()',c);await flush();}};
}

test('Enter after password submits login once with a real submit button',async()=>{
  const h=popupHarness({connected:false});await h.ready();
  h.nodes.get('base-url').value='https://nas.example';h.nodes.get('username').value='owner';h.nodes.get('password').value='test-password';
  let prevented=false;
  h.nodes.get('password').events.keydown({key:'Enter',isComposing:false,preventDefault(){prevented=true;}});
  await flush();assert.equal(prevented,true);
  assert.equal(h.messages.filter(m=>m.type==='login').length,1);
  assert.equal(h.nodes.get('password').value,'');assert.equal(h.nodes.get('login-button').disabled,false);
});

test('pause waits for stopped status before enabling confirmed temporary-file deletion',async()=>{
  const confirmations=[];
  const h=popupHarness({confirmAction:text=>{confirmations.push(text);return true;}});await h.ready();
  h.nodes.get('jobs').children[0].children[0].events.click();
  assert.equal(inline(h,2).disabled,true);
  await inline(h,0).events.click();
  assert.equal(h.messages.filter(m=>m.type==='jobPause').length,1);
  assert.equal(inline(h,2).disabled,true);
  assert.equal(inline(h,1).disabled,true);
  h.job.status='paused';await h.poll();
  assert.equal(inline(h,2).disabled,false);
  assert.equal(inline(h,1).disabled,false);
  await inline(h,2).events.click();
  assert.match(confirmations[0],/임시 파일/);
  assert.equal(h.messages.filter(m=>m.type==='jobDelete').length,1);
  assert.equal(h.nodes.get('job-detail').classList.contains('hidden'),true);
});

test('completed deletion keeps output wording; cancel and errors retain the job',async()=>{
  for(const accept of [false,true]) {
    const confirmations=[];
    const h=popupHarness({confirmAction:text=>{confirmations.push(text);return accept;},actionError:true});await h.ready();
    h.job.status='completed';await h.poll();h.nodes.get('jobs').children[0].children[0].events.click();
    assert.equal(inline(h,2).textContent,'기록 삭제');
    await inline(h,2).events.click();
    assert.match(confirmations[0],/파일은 유지/);
    assert.equal(h.messages.filter(m=>m.type==='jobDelete').length,Number(accept));
    assert.equal(h.nodes.get('job-detail').classList.contains('hidden'),false);
    if(accept)assert.equal(h.nodes.get('notice').textContent,'synthetic failure');
  }
});

test('resume sends only selected paused job and postprocessing controls remain locked',async()=>{
  const h=popupHarness();await h.ready();h.nodes.get('jobs').children[0].children[0].events.click();
  for(const status of ['extracting','publishing','stopping']) {
    h.job.status=status;await h.poll();
    for(const index of [0,1,2])assert.equal(inline(h,index).disabled,true);
  }
  h.job.status='paused';await h.poll();await inline(h,1).events.click();
  assert.equal(h.messages.find(m=>m.type==='jobResume').id,h.job.id);
});

test('clicking a job opens options and polling preserves password and dirty extraction choice',async()=>{
  const h=popupHarness();await h.ready();
  h.nodes.get('jobs').children[0].children[0].events.click();
  assert.equal(h.nodes.get('job-detail').classList.contains('hidden'),false);
  const password=h.nodes.get('job-password');password.value='synthetic';password.events.input();
  h.job.downloaded=50;await h.poll();
  assert.equal(h.nodes.get('job-password'),password);assert.equal(password.value,'synthetic');
  await h.nodes.get('job-options-form').events.submit({preventDefault(){}});
  const sent=h.messages.find(m=>m.type==='jobProcessing');
  assert.equal(sent.id,h.job.id);assert.equal(sent.password,'synthetic');assert.equal(sent.extract,true);
  assert.equal(password.value,'');
});

test('older server keeps extraction readonly but permits password-required retry',async()=>{
  const h=popupHarness({modern:false});await h.ready();h.job.status='password_required';await h.poll();
  h.nodes.get('jobs').children[0].children[0].events.click();
  assert.equal(h.nodes.get('job-password').disabled,false);
  h.nodes.get('job-password').value='retry';
  await h.nodes.get('job-options-form').events.submit({preventDefault(){}});
  assert.ok(h.messages.some(m=>m.type==='jobPassword'&&m.password==='retry'));
});

test('completed cleanup removes history through explicit action and disables when none exist',async()=>{
  const h=popupHarness();await h.ready();assert.equal(h.nodes.get('clear-completed').disabled,true);
  h.job.status='completed';await h.poll();assert.equal(h.nodes.get('clear-completed').disabled,false);
  await h.nodes.get('clear-completed').events.click();assert.equal(h.messages.filter(m=>m.type==='clearCompleted').length,1);
});

test('toolbar preference persists across popup reopen without changing existing job options',async()=>{
  assert.ok(!html.includes('login-extract'));
  assert.match(html,/id="refresh-button"[^]*?<\/button><label class="check"><input id="auto-extract"/);
  const preferences={autoExtract:false};
  const h=popupHarness({preferences});await h.ready();
  const toggle=h.nodes.get('auto-extract');assert.equal(toggle.checked,false);
  h.nodes.get('jobs').children[0].children[0].events.click();
  h.nodes.get('job-password').value='keep-input';h.nodes.get('job-password').events.input();
  for (const value of [true,false]) {
    toggle.checked=value;await toggle.events.change({target:toggle});
    assert.equal(preferences.autoExtract,value);
    assert.equal(h.nodes.get('job-password').value,'keep-input');
    const reopened=popupHarness({preferences});await reopened.ready();
    assert.equal(reopened.nodes.get('auto-extract').checked,value);
  }
  assert.equal(h.messages.filter(m=>m.type==='jobProcessing'||m.type==='jobPassword').length,0);
});

test('all four languages persist, translate statuses and preserve extraction/password state',async()=>{
  const preferences={autoExtract:false,language:'auto'},h=popupHarness({preferences});await h.ready();
  h.nodes.get('jobs').children[0].children[0].events.click();
  h.nodes.get('job-password').value='keep-private';h.nodes.get('job-password').events.input();
  for(const language of ['en','ko','zh','ja']) {
    const select=h.nodes.get('language-select');select.value=language;await select.events.change({target:select});
    assert.equal(preferences.language,language);assert.equal(preferences.autoExtract,false);
    assert.equal(h.nodes.get('destination-label').textContent,vm.runInContext("t('destination')+': /downloads'",h.c));
    assert.equal(h.nodes.get('job-password').value,'keep-private');
    const expected=h.c.NASDropI18n.t(language,'downloading');
    assert.ok(h.nodes.get('jobs').children[0].children[0].children[0].children[1].textContent.startsWith(expected));
    const reopened=popupHarness({preferences});await reopened.ready();
    assert.equal(reopened.nodes.get('language-select').value,language);
    assert.equal(vm.runInContext('language',reopened.c),language);
  }
  assert.equal(vm.runInContext('Object.keys(messages).every(lang=>Object.keys(messages.en).every(key=>Boolean(messages[lang][key])))',h.c),true);
});
