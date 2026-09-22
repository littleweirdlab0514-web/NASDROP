importScripts('i18n.js', 'provider-adapters.js');
const currentLanguage=async()=>NASDropI18n.resolve((await settings()).language,chrome.i18n.getUILanguage());
const translatedError=async error=>NASDropI18n.error(await currentLanguage(),error.message);
const storageReady = chrome.storage.local.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
const pageTransfers = new Map();
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
  await chrome.storage.session.remove('passwordJobs');
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
  await chrome.storage.session.remove('passwordJobs');
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
  const handoffProvider = handoffPage ? NASDropProviders.provider(handoffPage) : '';
  const inspectBody = ['akirabox','vikingfile'].includes(handoffProvider)
    ? {url:NASDropProviders.share(handoffPage), resolved_url:source.href, provider:handoffProvider}
    : {url:source.href};
  const inspected = await api('/api/inspect', {
    method: 'POST',
    body: JSON.stringify(inspectBody),
  });
  const started = await api('/api/start', {
    method: 'POST',
    body: JSON.stringify({ ...inspected.file, target: '', extract: saved.autoExtract !== false, password: saved.autoExtract === false ? '' : String(options.password || '') }),
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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  // Provider content scripts never receive settings, credentials or job metadata.
  if (sender.tab) {
    const page = sender.url || '';
    if (sender.frameId !== 0 || !NASDropProviders.share(page)) return false;
    let operation;
    if (message?.type === 'pageReady') {
      operation = pageReadiness(page);
    } else if (message?.type === 'pageSubmit' && NASDropProviders.allowedSubmission(page, message.url)) {
      const key = `${sender.tab.id}:${message.url}`;
      if (pageTransfers.has(key)) operation = pageTransfers.get(key);
      else {
        operation = submitFromPage(page, message.url).then(result => ({count: result.count}));
        pageTransfers.set(key, operation);
        operation.finally(() => pageTransfers.delete(key)).catch(() => {});
      }
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
    jobPause: () => controlJob(message, 'pause'),
    jobResume: () => controlJob(message, 'resume'),
    jobDelete: () => controlJob(message, 'delete'),
    jobProcessing: () => updateJob(message, 'processing'),
    login: () => login(message),
    logout,
    submit: () => submitUrl(message.url, false, '', message),
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

async function updateJob(message, action) {
  if (!/^[a-f0-9]{12}$/.test(message.id || '')) throw new Error('Invalid job ID.');
  const body = action === 'password' ? {password:String(message.password || '')} : {extract:message.extract};
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
  if (!ready || !['akirabox','vikingfile'].includes(provider)) return {ready,language};
  const status = await api('/api/status');
  return {ready:true, language,handoffSupported:Array.isArray(status.browser_handoff_providers) && status.browser_handoff_providers.includes(provider)};
}

async function submitFromPage(page, url) {
  const readiness = await pageReadiness(page);
  if (readiness.handoffSupported === false) {
    const error = new Error('This NASDrop server does not support browser handoff for this site yet.');
    error.code = 'serverUnsupported'; throw error;
  }
  return submitUrl(url, false, page);
}
