importScripts('i18n.js', 'provider-adapters.js');
const currentLanguage=async()=>NASDropI18n.resolve((await settings()).language,chrome.i18n.getUILanguage());
const translatedError=async error=>NASDropI18n.error(await currentLanguage(),error.message);
const storageReady = chrome.storage.local.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
const pageTransfers = new Map();
const SENDNOW_ARM_MS = 60000;
const XSHARE_REFRESH_ARM_MS = 10 * 60 * 1000;
const MENU_LINK = "nasdrop-send-link";
const MENU_PAGE = "nasdrop-send-page";
const ACTIVE_STATUSES = new Set([
  "inspecting", "queued", "ready", "downloading", "waiting_processing", "verifying",
  "extracting", "publishing", "stopping",
]);
const JOB_ALARM = 'nasdrop-job-monitor';
let jobsFlight = null, jobsCache = null, jobsCachedAt = 0, monitorFailures = 0;
const popupPorts = new Set();

async function getJobs(force = false) {
  if (jobsFlight) return jobsFlight;
  if (!force && jobsCache && Date.now() - jobsCachedAt < 2000) return jobsCache;
  jobsFlight = (async () => {
    try {
      const result = await api('/api/jobs', {signal:AbortSignal.timeout(15000)});
      if (!Array.isArray(result.jobs)) throw new Error('Invalid job list received.');
      jobsCache = result; jobsCachedAt = Date.now(); monitorFailures = 0;
      await updateBadge(result.jobs);
      const previous = (await chrome.storage.session.get({passwordJobs:[]})).passwordJobs;
      const waiting = result.jobs.filter(job => job.status === 'password_required');
      const announced = [];
      for (const job of waiting) {
        if (!previous.includes(job.id)) {
          try {
            const language=await currentLanguage();
            await chrome.notifications.create(`nasdrop-password-${job.id}`, {
              type:'basic', iconUrl:'icons/nasdrop-256.png', title:NASDropI18n.t(language,'passwordTitle'),
              message:`${job.name}\n${NASDropI18n.t(language,'passwordMessage')}`,
            });
          } catch { continue; }
        }
        announced.push(job.id);
      }
      await chrome.storage.session.set({passwordJobs:announced});
      const previousReauth = (await chrome.storage.session.get({reauthJobs:[]})).reauthJobs;
      const reauthWaiting = result.jobs.filter(job => job.status === 'reauthentication_required');
      const announcedReauth = [];
      for (const job of reauthWaiting) {
        if (!previousReauth.includes(job.id)) {
          try {
            const language=await currentLanguage();
            await chrome.notifications.create(`nasdrop-reauth-${job.id}`, {
              type:'basic', iconUrl:'icons/nasdrop-256.png', title:NASDropI18n.t(language,'reauthTitle'),
              message:`${job.name}\n${NASDropI18n.t(language,'reauthMessage')}`,
            });
          } catch { continue; }
        }
        announcedReauth.push(job.id);
      }
      await chrome.storage.session.set({reauthJobs:announcedReauth});
      if (result.jobs.some(job => ACTIVE_STATUSES.has(job.status))) await chrome.alarms.create(JOB_ALARM,{delayInMinutes:1});
      else await chrome.alarms.clear(JOB_ALARM);
      return result;
    } catch (error) {
      if (error.status === 401) { jobsCache = null; await chrome.alarms.clear(JOB_ALARM); }
      else await chrome.alarms.create(JOB_ALARM,{delayInMinutes:Math.min(5,2 ** monitorFailures++)});
      throw error;
    } finally { jobsFlight = null; }
  })();
  return jobsFlight;
}

chrome.runtime.onConnect.addListener(port => {
  if (port.name !== 'nasdrop-popup' || port.sender?.url !== chrome.runtime.getURL('popup.html')) return;
  popupPorts.add(port);
  port.onDisconnect.addListener(() => popupPorts.delete(port));
});
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name !== JOB_ALARM) return;
  if (popupPorts.size) { chrome.alarms.create(JOB_ALARM,{delayInMinutes:1}); return; }
  getJobs().catch(() => {});
});

function normalizeBaseUrl(value) {
  const url = new URL(String(value || "").trim());
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('NASDrop address must use HTTP or HTTPS.');
  if (url.username || url.password) throw new Error('Enter a server address without embedded credentials.');
  url.hash = '';
  url.search = '';
  return url.href.replace(/\/$/, '');
}

async function settings() {
  await storageReady;
  return chrome.storage.local.get({ baseUrl: '', token: '', autoExtract: true, username: '', language:'auto' });
}

async function api(path, init = {}, requireAuth = true) {
  const saved = await settings();
  if (!saved.baseUrl) throw new Error('Open the NASDrop extension and enter your server address.');
  if (requireAuth && !saved.token) throw Object.assign(new Error('Sign in to NASDrop first.'), { status: 401 });
  const headers = { 'content-type': 'application/json', ...(init.headers || {}) };
  if (requireAuth) headers.authorization = `Bearer ${saved.token}`;
  let response;
  try {
    response = await fetch(`${normalizeBaseUrl(saved.baseUrl)}${path}`, { ...init, headers, redirect:'error', credentials:'omit' });
  } catch (_) {
    throw new Error('Could not reach the NASDrop server. Check its address and network connection.');
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && requireAuth) await chrome.storage.local.remove('token');
    const error = new Error(payload.error || `NASDrop request failed (${response.status}).`);
    error.status = response.status;
    error.code = payload.code || '';
    throw error;
  }
  return payload;
}

async function updateBadge(jobs) {
  const count = (jobs || []).filter(job => ACTIVE_STATUSES.has(job.status)).length;
  await chrome.action.setBadgeBackgroundColor({ color: '#2563eb' });
  await chrome.action.setBadgeText({ text: count ? String(Math.min(count, 99)) : '' });
}

async function getState() {
  const saved = await settings();
  if (!saved.baseUrl || !saved.token) return { ...saved, connected: false, jobs: [] };
  try {
    const [status, jobResult] = await Promise.all([api('/api/status'), getJobs()]);
    await updateBadge(jobResult.jobs);
    return { ...saved, connected: true, status, jobs: jobResult.jobs };
  } catch (error) {
    return { ...saved, token: error.status === 401 ? '' : saved.token, connected: false, jobs: [], passwordChangeRequired:error.code === 'password_change_required', error: error.message };
  }
}

async function login({ baseUrl, username, password }) {
  const normalized = normalizeBaseUrl(baseUrl);
  const previous = await settings();
  if (previous.baseUrl !== normalized) await chrome.storage.local.remove(['token', 'username']);
  jobsCache = null;
  await chrome.storage.session.remove(['passwordJobs','reauthJobs','xshareRefresh']);
  await chrome.storage.session.remove('sendNowArm');
  await chrome.storage.local.set({ baseUrl: normalized });
  const result = await api('/api/login', {
    method: 'POST',
    body: JSON.stringify({ username: String(username || '').trim(), password: String(password || '') }),
  }, false);
  await chrome.storage.local.set({ token: result.token, username: result.username || String(username || '').trim() });
  if (result.password_change_required) {
    return { ...(await settings()), connected:false, jobs:[], passwordChangeRequired:true };
  }
  return getState();
}

async function logout() {
  try { await api('/api/logout', { method: 'POST', body: '{}' }); } catch (_) {}
  await chrome.storage.local.remove(['token', 'username']);
  jobsCache = null;
  await chrome.alarms.clear(JOB_ALARM);
  await chrome.storage.session.remove(['passwordJobs','reauthJobs','xshareRefresh']);
  await chrome.storage.session.remove('sendNowArm');
  await updateBadge([]);
  return { ok: true };
}

async function submitUrl(rawUrl, notify = false, handoffPage = '', options = {}) {
  let source;
  try {
    source = new URL(String(rawUrl || '').trim());
    if (!['http:', 'https:'].includes(source.protocol)) throw new Error();
  } catch (_) {
    throw new Error('Enter a valid HTTP or HTTPS download link.');
  }
  const saved = await settings();
  const sourceProvider = NASDropProviders.provider(source.href);
  const downloadKey = String(options.downloadKey || '');
  if (downloadKey && sourceProvider !== 'gigafile') throw new Error('A GigaFile download key can only be used with a GigaFile link.');
  if (downloadKey.length > 4) throw new Error('GigaFile download key must be 1–4 characters.');
  const common = {target:'',extract:saved.autoExtract !== false,password:saved.autoExtract === false ? '' : String(options.password || '')};
  let asyncEnqueueSupported = sourceProvider === 'gigafile';
  if (sourceProvider === 'gofile') {
    if (typeof options.asyncEnqueueSupported === 'boolean') asyncEnqueueSupported=options.asyncEnqueueSupported;
    else {
      const status=await api('/api/status');
      asyncEnqueueSupported=Array.isArray(status.async_enqueue_providers) && status.async_enqueue_providers.includes('gofile');
    }
  }
  if (asyncEnqueueSupported) {
    const body={url:source.href,...common};
    if (downloadKey) body.download_key=downloadKey;
    const started=await api('/api/enqueue',{method:'POST',body:JSON.stringify(body)}).catch(error=>{
      if (!error.status) throw new Error('Result unknown. Check NASDrop jobs before retrying.');
      throw error;
    });
    let fallbackName=source.pathname.split('/').filter(Boolean).at(-1) || `${sourceProvider === 'gofile' ? 'GoFile' : 'GigaFile'} download`;
    try { fallbackName=decodeURIComponent(fallbackName); } catch (_) { /* Keep the encoded safe fallback. */ }
    const file={name:started.job?.name || fallbackName};
    if (notify) await chrome.notifications.create({type:'basic',iconUrl:'icons/nasdrop-256.png',title:'NASDrop',message:started.count > 1 ? NASDropI18n.t(await currentLanguage(),'addedMany',{count:started.count}) : file.name}).catch(()=>{});
    try { await getJobs(true); } catch (_) { /* The accepted job remains successful. */ }
    return {file,...started};
  }
  const handoffProvider = handoffPage ? NASDropProviders.provider(handoffPage) : '';
  const inspectBody = ['akirabox','vikingfile','sendnow','xshare'].includes(handoffProvider)
    ? {url:NASDropProviders.share(handoffPage), resolved_url:source.href, provider:handoffProvider}
    : {url:source.href};
  const inspected = await api('/api/inspect', {
    method: 'POST',
    body: JSON.stringify(inspectBody),
  });
  const startBody = { ...inspected.file, ...common };
  const started = await api('/api/start', {
    method: 'POST',
    body: JSON.stringify(startBody),
  }).catch(error => {
    if (!error.status) throw new Error('Result unknown. Check NASDrop jobs before retrying.');
    throw error;
  });
  if (notify) {
    const title = NASDropI18n.t(await currentLanguage(),'addedMany',{count:started.count});
    await chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/nasdrop-256.png',
      title: 'NASDrop',
      message: started.count > 1 ? title : inspected.file.name,
    }).catch(() => {});
  }
  try {
    const jobResult = await getJobs(true);
    await updateBadge(jobResult.jobs);
  } catch (_) { /* An accepted job remains successful even if refresh fails. */ }
  return { file: inspected.file, ...started };
}

async function notifyError(error) {
  await chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icons/nasdrop-256.png',
    title: 'NASDrop',
    message: await translatedError(error),
  });
}

async function updateMenus() {
  const language=await currentLanguage();
  await new Promise(resolve=>chrome.contextMenus.removeAll(resolve));
  chrome.contextMenus.create({id:MENU_LINK,title:NASDropI18n.t(language,'menuLink'),contexts:['link']});
  chrome.contextMenus.create({id:MENU_PAGE,title:NASDropI18n.t(language,'menuPage'),contexts:['page']});
}
chrome.runtime.onInstalled.addListener(()=>{updateMenus().catch(()=>{});});
chrome.runtime.onStartup?.addListener(()=>{updateMenus().catch(()=>{});});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const url = info.menuItemId === MENU_LINK ? info.linkUrl : (info.pageUrl || tab?.url);
  submitUrl(url, true).catch(notifyError);
});

async function activeSendNowArm() {
  const arm = (await chrome.storage.session.get({sendNowArm:null})).sendNowArm;
  if (!arm || arm.expiresAt <= Date.now()) {
    if (arm) await chrome.storage.session.remove('sendNowArm');
    return null;
  }
  return arm;
}

async function activeXShareRefresh(source = '') {
  const refresh = (await chrome.storage.session.get({xshareRefresh:null})).xshareRefresh;
  if (!refresh || refresh.expiresAt <= Date.now() || !/^[a-f0-9]{12}$/.test(refresh.jobId || '')
      || !refresh.source || (source && refresh.source !== source)) {
    if (refresh) await chrome.storage.session.remove('xshareRefresh');
    return null;
  }
  return refresh;
}

async function refreshXShareJob(refresh, source, resolvedUrl) {
  if (!refresh || refresh.source !== source || !NASDropProviders.allowedSubmission(source,resolvedUrl)) {
    throw new Error('Invalid download request.');
  }
  await chrome.storage.session.remove('xshareRefresh');
  const result=await api(`/api/jobs/${refresh.jobId}/browser-handoff`,{
    method:'POST',body:JSON.stringify({provider:'xshare',resolved_url:resolvedUrl}),
  });
  jobsCache=null;
  await chrome.alarms.create(JOB_ALARM,{delayInMinutes:1});
  return {count:1,refreshed:true,accepted:result?.accepted !== false};
}

async function sendNowResult(tabId, result) {
  await chrome.tabs.sendMessage(tabId,{type:'sendNowResult',...result}).catch(() => {});
}

async function captureSendNowDownload(item) {
  const arm = await activeSendNowArm();
  if (!arm) return;
  let referrer;
  try { referrer = new URL(item.referrer || ''); } catch { return; }
  if (referrer.protocol !== 'https:' || !['send.now','www.send.now'].includes(referrer.hostname)
    || referrer.pathname !== '/' || referrer.search || referrer.hash) return;
  const url = item.finalUrl || item.url || '';
  if (!NASDropProviders.allowedSubmission(arm.source, url)) return;
  await chrome.storage.session.remove('sendNowArm');
  await chrome.downloads.cancel(item.id).catch(() => {});
  await chrome.downloads.erase({id:item.id}).catch(() => {});
  try {
    await submitFromPage(arm.source, url);
    await sendNowResult(arm.tabId,{ok:true});
  } catch (error) {
    await sendNowResult(arm.tabId,{ok:false,error:await translatedError(error)});
  }
}
chrome.downloads.onCreated.addListener(item => { void captureSendNowDownload(item); });

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  // Provider content scripts never receive settings, credentials or job metadata.
  if (sender.tab) {
    const page = sender.url || '';
    if (sender.frameId !== 0) return false;
    let operation;
    if (message?.type === 'pageArmDownload') {
      let current, source;
      try { current=new URL(page); source=NASDropProviders.share(message.source); } catch { return false; }
      if (!source || NASDropProviders.provider(source) !== 'sendnow'
        || current.protocol !== 'https:' || !['send.now','www.send.now'].includes(current.hostname)
        || current.pathname !== '/' || current.search || current.hash || current.origin !== new URL(source).origin) return false;
      operation = pageReadiness(source).then(async readiness => {
        if (!readiness.ready) throw Object.assign(new Error('Sign in to NASDrop first.'), {code:'login'});
        if (readiness.handoffSupported === false) throw Object.assign(new Error('This NASDrop server does not support browser handoff for this site yet.'), {code:'serverUnsupported'});
        const active = await activeSendNowArm();
        if (active && active.tabId !== sender.tab.id) throw new Error('Another Send.now handoff is already waiting for its download.');
        await chrome.storage.session.set({sendNowArm:{tabId:sender.tab.id,source,expiresAt:Date.now()+SENDNOW_ARM_MS}});
        return {armed:true,language:readiness.language};
      });
    } else if (message?.type === 'pageArmXShare') {
      const source=NASDropProviders.share(message.source);
      if (!source || source !== NASDropProviders.share(page) || NASDropProviders.provider(source) !== 'xshare') return false;
      operation = pageReadiness(source).then(readiness => {
        if (!readiness.ready) throw Object.assign(new Error('Sign in to NASDrop first.'), {code:'login'});
        if (readiness.handoffSupported === false) throw Object.assign(new Error('This NASDrop server does not support browser handoff for this site yet.'), {code:'serverUnsupported'});
        return {armed:true,language:readiness.language};
      });
    } else if (!NASDropProviders.share(page)) return false;
    else if (message?.type === 'pageReady') {
      operation = pageReadiness(page);
    } else if (message?.type === 'pageSubmit' && NASDropProviders.allowedSubmission(page, message.url)) {
      operation=(async()=>{
        const source=NASDropProviders.share(page);
        const refresh=NASDropProviders.provider(source)==='xshare' ? await activeXShareRefresh(source) : null;
        const key=refresh ? `${sender.tab.id}:xshare-refresh:${refresh.jobId}` : `${sender.tab.id}:${message.url}`;
        if(pageTransfers.has(key))return pageTransfers.get(key);
        const transfer=(async()=>{
          try {
            if(refresh)return await refreshXShareJob(refresh,source,message.url);
            const result=await submitFromPage(page,message.url,{downloadKey:message.downloadKey});
            return {count:result.count};
          } finally {pageTransfers.delete(key);}
        })();
        pageTransfers.set(key,transfer);
        return transfer;
      })();
    } else return false;
    operation.then(result => sendResponse({ok:true, result})).catch(async error => sendResponse({ok:false, error:await translatedError(error), code:error.code}));
    return true;
  }
  if (sender.url !== chrome.runtime.getURL('popup.html')) return false;
  const actions = {
    getState,
    getJobs: () => getJobs(Boolean(message.force)),
    clearCompleted: async () => {
      const result = await api('/api/jobs/completed/clear',{method:'POST',body:'{}'});
      jobsCache = null;
      return result;
    },
    jobPassword: () => updateJob(message, 'password'),
    jobDownloadKey: () => updateJob(message, 'download-key'),
    jobPause: () => controlJob(message, 'pause'),
    jobResume: () => controlJob(message, 'resume'),
    jobDelete: () => controlJob(message, 'delete'),
    jobHandoffOpen: () => openXShareRefresh(message),
    jobProcessing: () => updateJob(message, 'processing'),
    login: () => login(message),
    logout,
    submit: () => submitFromPopup(message),
    savePreferences: async () => {
      const values={};
      if(typeof message.autoExtract==='boolean')values.autoExtract=message.autoExtract;
      if(message.language!==undefined) {
        if(!['auto',...NASDropI18n.locales].includes(message.language))throw new Error('Invalid language.');
        values.language=message.language;
      }
      await chrome.storage.local.set(values);
      if(values.language!==undefined)await updateMenus();
      return { ok: true };
    },
  };
  const action = actions[message?.type];
  if (!action) return false;
  action().then(result => sendResponse({ ok: true, result })).catch(async error => {
    sendResponse({ ok: false, error: await translatedError(error), status: error.status || 0 });
  });
  return true;
});

async function controlJob(message, action) {
  if (!/^[a-f0-9]{12}$/.test(message.id || '')) throw new Error('Invalid job ID.');
  const path=action==='delete' ? '/api/jobs/delete' : `/api/jobs/${message.id}/${action}`;
  const result=await api(path,{method:'POST',body:JSON.stringify(action==='delete'?{ids:[message.id]}:{})});
  jobsCache=null;
  await chrome.alarms.create(JOB_ALARM,{delayInMinutes:1});
  return result;
}

async function openXShareRefresh(message) {
  if(!/^[a-f0-9]{12}$/.test(message.id||''))throw new Error('Invalid job ID.');
  const [status,result]=await Promise.all([api('/api/status'),getJobs(true)]);
  const supported=Array.isArray(status.browser_handoff_refresh_providers)
    && status.browser_handoff_refresh_providers.includes('xshare');
  if(!supported)throw Object.assign(new Error('This NASDrop server does not support refreshing X-Share jobs yet.'),{code:'serverUnsupported'});
  const job=result.jobs.find(item=>item.id===message.id);
  const source=job ? NASDropProviders.share(job.url) : '';
  if(!job||job.status!=='reauthentication_required'||NASDropProviders.provider(source)!=='xshare')throw new Error('This job no longer needs X-Share verification.');
  await chrome.storage.session.set({xshareRefresh:{jobId:job.id,source,expiresAt:Date.now()+XSHARE_REFRESH_ARM_MS}});
  await chrome.tabs.create({url:source});
  return {opened:true};
}

async function updateJob(message, action) {
  if (!/^[a-f0-9]{12}$/.test(message.id || '')) throw new Error('Invalid job ID.');
  let body;
  if (action === 'password') body = {password:String(message.password || '')};
  else if (action === 'download-key') {
    const downloadKey=String(message.downloadKey || '');
    if (downloadKey.length < 1 || downloadKey.length > 4) throw new Error('GigaFile download key must be 1–4 characters.');
    body={download_key:downloadKey};
  } else body = {extract:message.extract};
  if (action === 'processing') {
    if (typeof body.extract !== 'boolean') throw new Error('Invalid extraction option.');
    if (message.password) body.password = String(message.password);
  }
  const result = await api(`/api/jobs/${message.id}/${action}`,{method:'POST',body:JSON.stringify(body)});
  jobsCache = null;
  await chrome.alarms.create(JOB_ALARM,{delayInMinutes:1});
  return result;
}

async function pageReadiness(page) {
  const saved = await settings();
  const ready = Boolean(saved.baseUrl && saved.token);
  const language=NASDropI18n.resolve(saved.language,chrome.i18n.getUILanguage());
  const provider = NASDropProviders.provider(page);
  if (!ready || !['akirabox','vikingfile','sendnow','xshare','gigafile','gofile'].includes(provider)) return {ready,language};
  const status = await api('/api/status');
  if (provider === 'gigafile') return {ready:true,language,gigafileDownloadKeySupported:status.gigafile_download_key === true};
  if (provider === 'gofile') return {ready:true,language,asyncEnqueueSupported:Array.isArray(status.async_enqueue_providers) && status.async_enqueue_providers.includes('gofile')};
  return {ready:true, language,handoffSupported:Array.isArray(status.browser_handoff_providers) && status.browser_handoff_providers.includes(provider)};
}

async function submitFromPopup(message) {
  if (message.downloadKey) {
    const status=await api('/api/status');
    if (status.gigafile_download_key !== true) {
      const error=new Error('This NASDrop server does not support GigaFile download keys yet.');
      error.code='serverUnsupported'; throw error;
    }
  }
  return submitUrl(message.url,false,'',message);
}

async function submitFromPage(page, url, options = {}) {
  const readiness = await pageReadiness(page);
  if (readiness.handoffSupported === false) {
    const error = new Error('This NASDrop server does not support browser handoff for this site yet.');
    error.code = 'serverUnsupported'; throw error;
  }
  if (NASDropProviders.provider(page) === 'gigafile' && options.downloadKey && !readiness.gigafileDownloadKeySupported) {
    const error = new Error('This NASDrop server does not support GigaFile download keys yet.');
    error.code = 'serverUnsupported'; throw error;
  }
  return submitUrl(url, false, page, {...options,asyncEnqueueSupported:readiness.asyncEnqueueSupported});
}
