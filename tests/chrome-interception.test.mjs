import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const root = new URL('../chrome-extension/', import.meta.url);
const i18nSource = await readFile(new URL('i18n.js', root), 'utf8');
const adapterSource = await readFile(new URL('provider-adapters.js', root), 'utf8');
const contentSource = await readFile(new URL('content.js', root), 'utf8');
const workerSource = await readFile(new URL('background.js', root), 'utf8');
const page = 'https://buzzheavier.com/testfile1234';
const signed = 'https://ts.buzzheavier.com/d/testfile1234?v=synthetic-token';
const context = vm.createContext({URL, AbortSignal});
vm.runInContext(adapterSource, context);
const adapter = context.NASDropProviders;
function control(attrs = {}, selectors = [], row = null) {
  return {getAttribute: key => attrs[key] ?? null, matches: selector => selectors.includes(selector),
    closest: selector => selector === '.fm-row[data-id]' ? row : control(attrs, selectors, row)};
}
const download = control({'hx-get':'/testfile1234/download?t=synthetic'}, ['a.download-btn']);
const copy = control({onclick:"copyDownloadLink('\\/testfile1234\\/download?t=synthetic')"}, ['a.copy']);

test('real Buzzheavier button shapes resolve to the same endpoint, never the file body', () => {
  assert.equal(adapter.resolve(download, page).endpoint, `${page}/download?t=synthetic`);
  assert.equal(adapter.resolve(copy, page).endpoint, `${page}/download?t=synthetic`);
  assert.equal(adapter.resolve(control({href:'https://ads.example/download'}, ['a.download-btn']), page), null);
  assert.equal(adapter.resolve(control({'hx-get':'/otherfile/download'}, ['a.download-btn']), page), null);
});

test('Buzzheavier resolves only a valid same-file signed HX-Redirect without following it', async () => {
  const calls = [];
  const result = await adapter.resolveBuzzLink(`${page}/download?t=synthetic`, page, async (url, options) => {
    calls.push({url, options});
    return {ok:true, headers:new Headers({'HX-Redirect':signed})};
  });
  assert.equal(result, signed);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.headers['HX-Request'], 'true');
  assert.equal(calls[0].options.redirect, 'error');
  for (const invalid of ['https://ads.example/d/testfile1234?v=x', 'https://ts.buzzheavier.com/d/other?v=x', signed.replace('https:', 'http:'), signed.replace('?v=', '?x='), '']) {
    await assert.rejects(adapter.resolveBuzzLink(`${page}/download`, page, async () => ({ok:true, headers:new Headers({'HX-Redirect':invalid})})));
  }
  await assert.rejects(adapter.resolveBuzzLink(`${page}/download`, page, async () => ({ok:false, headers:new Headers()})));
});

test('file-specific controls do not silently submit their parent folder', () => {
  const giga = control({onclick:"download('child-file', false, false)"});
  assert.equal(adapter.resolve(giga, 'https://123.gigafile.nu/parent-file').url, 'https://123.gigafile.nu/child-file');
  const go = control({'data-action':'download'}, [], control({'data-id':'child-uuid'}));
  assert.equal(adapter.resolve(go, 'https://gofile.io/d/parent').url, 'https://gofile.io/d/child-uuid');
  const pixel = control({href:'/api/file/child?download'});
  assert.equal(adapter.resolve(pixel, 'https://pixeldrain.com/u/parent').url, 'https://pixeldrain.com/u/child');
  assert.equal(adapter.resolve(control({'data-action':'delete'}), 'https://gofile.io/d/parent'), null);
});

function contentHarness({ready = true, fail = false, pageUrl = page, handoffSupported,language,browserLanguage='ko',throwAt='',syncThrow=false,errorText='Extension context invalidated.'} = {}) {
  let handler;
  const messages = [], requests = [], nodes = [];
  function node() {
    const n = {style:{}, textContent:'', isConnected:true, append(){}, setAttribute(){}, addEventListener(){}, remove(){this.isConnected=false;}, attachShadow:node};
    nodes.push(n); return n;
  }
  const c = vm.createContext({URL, AbortSignal, navigator:{language:browserLanguage}, location:{href:pageUrl},
    window:{addEventListener(name, fn, capture){assert.equal(name,'click'); assert.equal(capture,true); handler=fn;}},
    document:{createElement:node, body:node()},
    fetch:async (url, options) => { requests.push({url, options}); return {ok:true, headers:new Headers({'HX-Redirect':signed})}; },
    chrome:{runtime:{sendMessage:message => {messages.push(message); if(message.type===throwAt){if(syncThrow)throw new Error(errorText);return Promise.reject(new Error(errorText));} return Promise.resolve(message.type === 'pageReady' ? {ok:true, result:{ready,handoffSupported,language}} : fail ? {ok:false,error:'Server unavailable'} : {ok:true,result:{count:1}});}}},
  });
  vm.runInContext(i18nSource,c); vm.runInContext(adapterSource, c); vm.runInContext(contentSource, c);
  function click(target = download, overrides = {}) {
    const e = {isTrusted:true, button:0, target, preventDefault(){this.prevented=true;}, stopImmediatePropagation(){this.stopped=true;}, ...overrides};
    handler(e); return e;
  }
  return {click, messages, requests, nodes};
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('invalidated context shows localized refresh guidance and stops repeated submissions',async()=>{
  const c=vm.createContext({});vm.runInContext(i18nSource,c);
  for(const browserLanguage of ['en','ko','ja','zh','fr'])for(const throwAt of ['pageReady','pageSubmit'])for(const syncThrow of [false,true]) {
    const h=contentHarness({browserLanguage,throwAt,syncThrow});
    assert.equal(h.click().prevented,true);await flush();
    assert.ok(h.nodes.some(n=>n.textContent===c.NASDropI18n.t(browserLanguage,'reloadExtension')));
    assert.ok(!h.nodes.some(n=>n.textContent==='Extension context invalidated.'));
    const count=h.messages.length;h.click();await flush();assert.equal(h.messages.length,count);
    if(throwAt==='pageReady')assert.equal(h.requests.length,0);
  }
});

test('other submission failures retain uncertain-result guidance',async()=>{
  const h=contentHarness({throwAt:'pageSubmit',errorText:'Connection closed'});h.click();await flush();
  assert.ok(h.nodes.some(n=>n.textContent.includes('전송 결과를 확인하지 못했습니다')));
});

function pixelControl(buttonClass, region, icon = 'download') {
  // Structural fixture from the two controls observed on the reported live page.
  const button = {
    getAttribute: () => null,
    matches: selector => selector === `button.${buttonClass}`,
    closest: selector => selector === '.toolbar' || selector === '.description' ? (selector === region ? {} : null) : button,
    querySelector: selector => selector === ':scope > i.icon' ? {textContent:icon} : null,
  };
  return button;
}

test('Pixeldrain current toolbar and no-preview buttons redirect nested clicks to the current share', async () => {
  const pageUrl = 'https://pixeldrain.com/u/uLZ8vMm3';
  for (const button of [pixelControl('toolbar_button','.toolbar'), pixelControl('button_highlight','.description')]) {
    assert.equal(adapter.resolve(button,pageUrl).url,pageUrl);
    const h = contentHarness({pageUrl});
    // The user may click the icon or text span rather than the button itself.
    const event = h.click({closest:() => button});
    assert.equal(event.prevented,true); assert.equal(event.stopped,true);
    await flush();
    assert.equal(h.messages.filter(m => m.type === 'pageSubmit').length,1);
    assert.equal(h.messages.find(m => m.type === 'pageSubmit').url,pageUrl);
    assert.equal(h.requests.length,0);
  }
});

test('Pixeldrain ignores share/menu controls, lookalikes outside the viewer, and non-file pages', () => {
  const url = 'https://pixeldrain.com/u/uLZ8vMm3';
  for (const icon of ['share','help','content_copy','fullscreen']) assert.equal(adapter.resolve(pixelControl('toolbar_button','.toolbar',icon),url),null);
  assert.equal(adapter.resolve(pixelControl('button_highlight','.advertisement'),url),null);
  assert.equal(adapter.resolve(pixelControl('toolbar_button','.toolbar'),'https://pixeldrain.com/'),null);
});

test('trusted Download File click stops browser navigation and submits exactly once', async () => {
  const h = contentHarness();
  const first = h.click(); const second = h.click();
  assert.equal(first.prevented, true); assert.equal(first.stopped, true); assert.equal(second.prevented, true);
  await flush();
  assert.equal(h.requests.length, 1);
  assert.equal(h.messages.filter(m => m.type === 'pageSubmit').length, 1);
  assert.equal(h.messages.find(m => m.type === 'pageSubmit').url, signed);
});

test('Copy download link is also intercepted; unsigned page is never submitted', async () => {
  const h = contentHarness(); h.click(copy); await flush();
  assert.equal(h.messages.find(m => m.type === 'pageSubmit').url, signed);
});

test('synthetic clicks, modifier clicks and ads retain original behavior', async () => {
  const h = contentHarness();
  assert.equal(h.click(download, {isTrusted:false}).prevented, undefined);
  assert.equal(h.click(download, {ctrlKey:true}).prevented, undefined);
  assert.equal(h.click(control({href:'https://ads.example/'})).prevented, undefined);
  await flush(); assert.equal(h.messages.length, 0); assert.equal(h.requests.length, 0);
});

test('no-login click is stopped with instructions, without contacting the provider', async () => {
  const h = contentHarness({ready:false}); assert.equal(h.click().prevented,true); await flush();
  assert.equal(h.requests.length, 0);
  assert.ok(h.nodes.some(n => n.textContent.includes('로그인')));
});

test('server rejection stays visible and does not fall through to a browser download', async () => {
  const h = contentHarness({fail:true}); h.click(); await flush();
  assert.ok(h.nodes.some(n => n.textContent === 'Server unavailable'));
  assert.equal(h.requests.length, 1);
});

function workerHarness({refreshFails = false, capabilities = [], jobs = [], autoExtract = true, count = 1, inspectFailures = 0} = {}) {
  let listener;
  const calls = [];
  const session = {}, notices = [], alarms = [];
  const saved = {baseUrl:'https://nas.example', token:'private-session', autoExtract};
  const c = vm.createContext({URL, AbortSignal, importScripts(){},
    chrome:{runtime:{id:'extension-id', getURL:p => `chrome-extension://extension-id/${p}`, onConnect:{addListener(){}}, onInstalled:{addListener(){}}, onMessage:{addListener(fn){listener=fn;}}},
      alarms:{create:async(...args)=>alarms.push(args),clear:async()=>{},onAlarm:{addListener(){}}},
      notifications:{create:async(...args)=>notices.push(args)},i18n:{getUILanguage:()=> 'en'},
      storage:{session:{get:async defaults=>({...defaults,...session}),set:async values=>Object.assign(session,values),remove:async key=>delete session[key]},local:{setAccessLevel:async()=>{}, get:async defaults=>({...defaults,...saved}), set:async values=>Object.assign(saved,values), remove:async keys=>{for (const key of Array.isArray(keys)?keys:[keys])delete saved[key];}}},
      action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}}, contextMenus:{removeAll:fn=>fn(),create(){},onClicked:{addListener(){}}}},
    fetch:async (url, options) => {
      calls.push({url, options});
      if (url.endsWith('/api/inspect') && inspectFailures-- > 0) return {ok:false,status:400,json:async()=>({error:'Synthetic inspection rejected'})};
      if (url.endsWith('/api/jobs') && refreshFails) throw new Error('offline');
      const payload = url.endsWith('/api/login') ? {token:'private-session'} : url.endsWith('/api/status') ? {browser_handoff_providers:capabilities} : url.endsWith('/api/inspect') ? {file:{url:signed, name:'synthetic.txt', size:100, inspection_id:'id'}} : url.endsWith('/api/start') ? {count, job:{id:'job'}} : {jobs};
      return {ok:true,json:async()=>payload};
    },
  });
  vm.runInContext(i18nSource,c); vm.runInContext(adapterSource,c); vm.runInContext(workerSource,c);
  const sender = {id:'extension-id', url:page, tab:{id:1}, frameId:0};
  const dispatch = (message, from = sender) => new Promise(resolve => {
    if (!listener(message, from, resolve)) resolve(null);
  });
  return {dispatch,calls,sender,notices,alarms,saved};
}

test('provider messages cannot read tokens or call login/settings APIs', async () => {
  const h = workerHarness();
  for (const type of ['getState','getJobs','clearCompleted','jobPassword','jobProcessing','jobPause','jobResume','jobDelete','login','logout','submit','savePreferences']) assert.equal(await h.dispatch({type,url:signed}),null);
  const ready = await h.dispatch({type:'pageReady'});
  assert.equal(JSON.stringify(ready), '{"ok":true,"result":{"ready":true,"language":"en"}}');
  assert.equal(await h.dispatch({type:'pageSubmit',url:'https://evil.example'}),null);
  assert.equal(await h.dispatch({type:'pageSubmit',url:signed},{...h.sender,frameId:1}),null);
  assert.equal(h.calls.length,0);
});

test('four-language page notices and background password alerts use saved choice',async()=>{
  const c=vm.createContext({});vm.runInContext(i18nSource,c);
  const popup={id:'extension-id',url:'chrome-extension://extension-id/popup.html'};
  for(const language of ['en','ko','zh','ja']) {
    const h=contentHarness({language,browserLanguage:'fr'});h.click();await flush();
    assert.ok(h.nodes.some(n=>n.textContent===c.NASDropI18n.t(language,'success')));
    const worker=workerHarness({jobs:[{id:'abcdef012345',name:'test.zip',status:'password_required'}]});
    assert.equal((await worker.dispatch({type:'savePreferences',language},popup)).ok,true);
    assert.equal(worker.saved.autoExtract,true);
    assert.equal((await worker.dispatch({type:'pageReady'})).result.language,language);
    await worker.dispatch({type:'getJobs'},popup);
    assert.equal(worker.notices[0][1].title,c.NASDropI18n.t(language,'passwordTitle'));
  }
  const h=contentHarness({browserLanguage:'unknown'});h.click();await flush();
  assert.ok(h.nodes.some(n=>n.textContent==='Added to NASDrop.'));
});

test('popup jobs reads coalesce, password alerts deduplicate, and completed cleanup uses history endpoint',async()=>{
  const h=workerHarness({jobs:[{id:'abcdef012345',name:'private.zip',status:'password_required'}]});
  const popup={id:'extension-id',url:'chrome-extension://extension-id/popup.html'};
  await Promise.all([h.dispatch({type:'getJobs'},popup),h.dispatch({type:'getJobs'},popup)]);
  await h.dispatch({type:'getJobs',force:true},popup);
  assert.equal(h.notices.length,1);
  assert.equal(h.calls.filter(c=>c.url.endsWith('/api/jobs')).length,2);
  await h.dispatch({type:'clearCompleted'},popup);
  assert.equal(h.calls.at(-1).url,'https://nas.example/api/jobs/completed/clear');
  assert.equal(h.calls.at(-1).options.body,'{}');
  const invalid=await h.dispatch({type:'jobProcessing',id:'../../settings',extract:false},popup);
  assert.equal(invalid.ok,false);
  await h.dispatch({type:'jobProcessing',id:'abcdef012345',extract:true,password:'synthetic password'},popup);
  assert.deepEqual(JSON.parse(h.calls.at(-1).options.body),{extract:true,password:'synthetic password'});
});

test('concurrent page submissions queue once and a failed status refresh cannot undo success', async () => {
  const h = workerHarness({refreshFails:true});
  const results = await Promise.all([h.dispatch({type:'pageSubmit',url:signed}),h.dispatch({type:'pageSubmit',url:signed})]);
  assert.ok(results.every(r => r.ok && r.result.count === 1));
  assert.equal(h.calls.filter(c => c.url.endsWith('/api/start')).length,1);
  assert.equal(h.calls[0].options.headers.authorization,'Bearer private-session');
  assert.ok(results.every(r => !JSON.stringify(r).includes('private-session')));
});

const akiraPage = 'https://akirabox.to/Share123/file';
const vikingPage = 'https://vik1ngfile.site/f/Share123';
const akiraUrl = `https://akirabox.com/download/syntheticOpaqueToken=/example.mkv?expiration=${Math.floor(Date.now()/1000)+3600}&signature=${'a'.repeat(64)}`;
const vikingUrl = 'https://vikingfile.com/d/OpaqueID123/example.zip';
const akiraButton = href => control({href,'aria-disabled':'false'}, ['a#download.download-button']);
const vikingButton = href => control({href}, ['a#download-link.button']);

test('AkiraBox/Viking recognize only the official button and strict issued-link structure', () => {
  for (const [pageUrl, href, makeButton] of [[akiraPage,akiraUrl,akiraButton],[vikingPage,vikingUrl,vikingButton]]) {
    assert.equal(adapter.classifyHandoff(makeButton(href),pageUrl).kind,'file');
    assert.equal(adapter.resolve(makeButton(href),pageUrl).url,href);
    assert.equal(adapter.classifyHandoff(control({href}),pageUrl).kind,'unrelated');
    assert.equal(adapter.classifyHandoff(makeButton('#'),pageUrl).kind,'preparing');
    for (const invalid of ['https://advertiser.example/download/file.exe', href.replace('https:', 'http:'), href.replace('.com/', '.com.evil.example/'), href.replace('.com/', '.com:8443/'), href.replace('https://','https://user:secret@'), href + '#fragment', href.replace('example.', '%2fexample.'), href.replace('example.', '%00example.')]) {
      assert.equal(adapter.classifyHandoff(makeButton(invalid),pageUrl).kind,'unrecognized');
      assert.equal(adapter.allowedSubmission(pageUrl,invalid),false);
    }
  }
});

test('AkiraBox rejects missing, duplicated or expired signatures and does not count clicks', () => {
  assert.equal(adapter.classifyHandoff(control({href:akiraUrl},['a#download.download-button']),akiraPage).kind,'preparing');
  for (const invalid of [akiraUrl.split('?')[0],akiraUrl+'&signature='+ 'a'.repeat(64),akiraUrl+'&redirect=https://evil.example',akiraUrl.replace('signature=','other=')]) {
    assert.equal(adapter.classifyHandoff(akiraButton(invalid),akiraPage).kind,'unrecognized');
  }
  const expired = akiraUrl.replace(/expiration=\d+/, 'expiration=1000000000');
  assert.equal(adapter.classifyHandoff(akiraButton(expired),akiraPage).kind,'expired');
  assert.equal(adapter.allowedSubmission(akiraPage,expired),false);
  // Two ads followed by a real link: only the real link qualifies. No third-click assumption.
  for (let i=0; i<2; i++) assert.equal(adapter.resolve(akiraButton('https://ads.example/file.exe'),akiraPage),null);
  assert.equal(adapter.resolve(akiraButton(akiraUrl),akiraPage).url,akiraUrl);
  assert.equal(adapter.resolve(akiraButton(akiraUrl),akiraPage).url,akiraUrl);
});

test('job controls validate IDs and use only pause, resume and scoped delete endpoints',async()=>{
  const h=workerHarness(),popup={id:'extension-id',url:'chrome-extension://extension-id/popup.html'};
  for(const type of ['jobPause','jobResume','jobDelete']) {
    assert.equal((await h.dispatch({type,id:'../unsafe'},popup)).ok,false);
    assert.equal((await h.dispatch({type,id:'abcdef012345'},popup)).ok,true);
  }
  assert.deepEqual(h.calls.map(c=>new URL(c.url).pathname),['/api/jobs/abcdef012345/pause','/api/jobs/abcdef012345/resume','/api/jobs/delete']);
  assert.deepEqual(JSON.parse(h.calls[2].options.body),{ids:['abcdef012345']});
});

test('Akira-only NAS capability does not enable Viking',async()=>{
  const h=workerHarness({capabilities:['akirabox']});
  assert.equal((await h.dispatch({type:'pageReady'},{...h.sender,url:akiraPage})).result.handoffSupported,true);
  assert.equal((await h.dispatch({type:'pageReady'},{...h.sender,url:vikingPage})).result.handoffSupported,false);
  assert.equal((await h.dispatch({type:'pageSubmit',url:vikingUrl},{...h.sender,url:vikingPage})).ok,false);
  assert.ok(!h.calls.some(c=>c.url.endsWith('/api/inspect')));
});

test('handoff failure reports server error and permits a fresh official link without final-host permissions',async()=>{
  for(const [pageUrl,first,next,provider] of [[akiraPage,akiraUrl,akiraUrl.replace('signature='+ 'a'.repeat(64),'signature='+ 'b'.repeat(64)),'akirabox'],[vikingPage,vikingUrl,vikingUrl.replace('OpaqueID123','FreshID123'),'vikingfile']]) {
    const h=workerHarness({capabilities:[provider],inspectFailures:1});
    const sender={...h.sender,url:pageUrl};
    const failed=await h.dispatch({type:'pageSubmit',url:first},sender);
    assert.equal(failed.ok,false);assert.equal(failed.error,'Synthetic inspection rejected');
    assert.equal(h.calls.filter(c=>c.url.endsWith('/api/start')).length,0);
    const success=await h.dispatch({type:'pageSubmit',url:next},sender);
    assert.equal(success.ok,true);
    const inspections=h.calls.filter(c=>c.url.endsWith('/api/inspect')).map(c=>JSON.parse(c.options.body));
    assert.deepEqual(inspections,[{url:pageUrl,resolved_url:first,provider},{url:pageUrl,resolved_url:next,provider}]);
    assert.equal(h.calls.filter(c=>c.url.endsWith('/api/start')).length,1);
    assert.ok(h.calls.every(c=>new URL(c.url).origin==='https://nas.example'));
    assert.ok(h.calls.every(c=>c.options.credentials==='omit'));
  }
});

test('unsupported NAS shows handoff notice without submitting or resolving links', async () => {
  const h = contentHarness({pageUrl:akiraPage, handoffSupported:false});
  const event = h.click(akiraButton(akiraUrl)); await flush();
  assert.equal(event.prevented,true);
  assert.equal(h.messages.filter(m=>m.type === 'pageSubmit').length,0);
  assert.equal(h.requests.length,0);
  assert.ok(h.nodes.some(n=>n.textContent.includes('아직 지원하지')));
});

test('advertising links are never queued by the page click handler', async () => {
  const h = contentHarness({pageUrl:akiraPage,handoffSupported:true});
  assert.equal(h.click(akiraButton('https://ads.example/download.exe')).prevented,undefined);
  assert.equal(h.click(control({href:akiraUrl})).prevented,undefined);
  await flush(); assert.equal(h.messages.length,0);
});

test('worker independently gates new providers and keeps source URL separate from issued URL', async () => {
  for (const [pageUrl, url, provider] of [[akiraPage,akiraUrl,'akirabox'],[vikingPage,vikingUrl,'vikingfile']]) {
    const h = workerHarness();
    const sender = {...h.sender,url:pageUrl};
    const rejected = await h.dispatch({type:'pageSubmit',url},sender);
    assert.equal(rejected.ok,false); assert.equal(rejected.code,'serverUnsupported');
    assert.equal(h.calls.filter(c=>/\/(inspect|start)$/.test(c.url)).length,0);
    const enabled = workerHarness({capabilities:[provider]});
    const accepted = await enabled.dispatch({type:'pageSubmit',url},{...enabled.sender,url:pageUrl});
    assert.equal(accepted.ok,true);
    const body = JSON.parse(enabled.calls.find(c=>c.url.endsWith('/api/inspect')).options.body);
    assert.deepEqual(body,{url:pageUrl,resolved_url:url,provider});
    assert.equal(JSON.stringify(accepted).includes(url),false);
  }
});

test('saved default survives login and governs new manual, shared, multi-file and handoff jobs only',async()=>{
  const popup={id:'extension-id',url:'chrome-extension://extension-id/popup.html'};
  for (const value of [false,true]) {
    const h=workerHarness({autoExtract:value,count:3,capabilities:['akirabox','vikingfile']});
    await h.dispatch({type:'login',baseUrl:'https://nas.example',username:'test',password:'synthetic'},popup);
    assert.equal(h.saved.autoExtract,value);
    for (const url of ['https://pixeldrain.com/u/test1234','https://gofile.io/d/test1234','https://1.gigafile.nu/1234-test1234']) {
      const result=await h.dispatch({type:'submit',url,extract:!value,password:'synthetic'},popup);
      assert.equal(result.ok,true);assert.equal(result.result.count,3);
    }
    for (const [pageUrl,url] of [[page,signed],[akiraPage,akiraUrl],[vikingPage,vikingUrl]]) {
      assert.equal((await h.dispatch({type:'pageSubmit',url},{...h.sender,url:pageUrl})).ok,true);
    }
    const starts=h.calls.filter(c=>c.url.endsWith('/api/start'));
    assert.equal(starts.length,6);
    assert.ok(starts.every(c=>JSON.parse(c.options.body).extract===value));
    if (!value) assert.ok(starts.every(c=>JSON.parse(c.options.body).password===''));
    const before=h.calls.length;
    await h.dispatch({type:'savePreferences',autoExtract:!value},popup);
    assert.equal(h.saved.autoExtract,!value);assert.equal(h.calls.length,before);
    await h.dispatch({type:'submit',url:signed},popup);
    assert.equal(JSON.parse(h.calls.findLast(c=>c.url.endsWith('/api/start')).options.body).extract,!value);
    assert.ok(!h.calls.some(c=>c.url.includes('/processing')||c.url.includes('/settings')));
  }
  const fresh=workerHarness();delete fresh.saved.autoExtract;
  assert.equal((await fresh.dispatch({type:'getState'},popup)).result.autoExtract,true);
});
