(() => {
  const adapters = globalThis.NASDropProviders;
  let language=NASDropI18n.normalize(navigator.language);
  const text=new Proxy({}, {get:(_,key)=>NASDropI18n.dictionaries[language][key]});
  let pending = false;
  let sendNowTimer = 0;
  let contextLost = false;
  let readinessCache = null;
  function invalidContext(error) { return /extension context invalidated/i.test(String(error?.message || error || '')); }
  let panel;
  function show(message) {
    if (!panel?.isConnected) {
      panel = document.createElement('div');
      panel.style.cssText = 'position:fixed;right:20px;bottom:20px;z-index:2147483647;max-width:380px;';
      const shadow = panel.attachShadow({mode:'closed'});
      const card = document.createElement('div');
      card.style.cssText = 'background:#101827;color:white;padding:16px;border:1px solid #5277bc;border-radius:12px;font:14px/1.5 system-ui;box-shadow:0 6px 30px #0005;';
      const title = document.createElement('strong'); title.textContent = 'NASDrop';
      const close = document.createElement('button'); close.textContent = '×'; close.setAttribute('aria-label', text.close); panel.closeButton=close;
      close.style.cssText = 'float:right;background:transparent;color:white;border:0;font-size:20px;cursor:pointer;';
      close.addEventListener('click', () => panel.remove());
      const status = document.createElement('div'); status.setAttribute('role', 'status');
      card.append(close, title, status); shadow.append(card);
      panel.update = value => { status.textContent = value; };
      (document.body || document.documentElement).append(panel);
    }
    panel.update(NASDropI18n.error(language,message));
  }
  async function send(action) {
    if (contextLost) { show(text.reloadExtension); return; }
    pending = true;
    show(text.sending);
    try {
      const ready = await chrome.runtime.sendMessage({type:'pageReady'});
      language=NASDropI18n.normalize(ready?.result?.language || language);
      if(panel?.closeButton)panel.closeButton.setAttribute('aria-label',text.close);
      if (action.error) { show(text[action.error] || text.failed); return; }
      if (!ready?.ok || !ready.result.ready) { show(text.login); return; }
      if (action.handoff && !ready.result.handoffSupported) { show(text.serverUnsupported); return; }
      let url = action.url;
      if (action.endpoint) {
        show(text.resolving);
        url = await adapters.resolveBuzzLink(action.endpoint, location.href);
      }
      show(text.sending);
      let response;
      try { response = await chrome.runtime.sendMessage({type:'pageSubmit', url, downloadKey:action.downloadKey || ''}); }
      catch (error) { if (invalidContext(error)) { contextLost=true; show(text.reloadExtension); } else show(text.uncertain); return; }
      show(response?.ok ? text.success : text[response?.code] || response?.error || text.failed);
    } catch (error) {
      if (invalidContext(error)) { contextLost=true; show(text.reloadExtension); }
      else show(error.message || text.failed);
    } finally { pending = false; }
  }
  async function armDownload(action, element) {
    if (contextLost) { show(text.reloadExtension); return; }
    pending = true;
    show(text.sending);
    try {
      const response = await chrome.runtime.sendMessage({type:'pageArmDownload',source:action.source});
      language=NASDropI18n.normalize(response?.result?.language || language);
      if(panel?.closeButton)panel.closeButton.setAttribute('aria-label',text.close);
      if (!response?.ok) { pending=false; show(text[response?.code] || response?.error || text.failed); return; }
      element.click();
      sendNowTimer=setTimeout(()=>{pending=false;show(text.uncertain);},65000);
    } catch (error) {
      pending=false;
      if (invalidContext(error)) { contextLost=true; show(text.reloadExtension); }
      else show(error.message || text.failed);
    }
  }
  chrome.runtime.onMessage.addListener(message => {
    if (message?.type !== 'sendNowResult') return;
    clearTimeout(sendNowTimer); sendNowTimer=0; pending=false;
    show(message.ok ? text.success : message.error || text.failed);
  });
  async function preloadReadiness() {
    if (adapters.provider(location.href) !== 'gigafile') return;
    try {
      const response = await chrome.runtime.sendMessage({type:'pageReady'});
      if (response?.ok) readinessCache = response.result;
    } catch (error) {
      if (invalidContext(error)) contextLost=true;
    }
  }
  void preloadReadiness();
  // Delegation also covers controls inserted after load and SPA navigation.
  window.addEventListener('click', event => {
    if (!event.isTrusted || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const element = event.target?.closest?.('a, button, input[type="button"], input[type="submit"], [data-action], [onclick]');
    if (!element || element.disabled || element.getAttribute('aria-disabled') === 'true') return;
    const action = adapters.resolve(element, location.href, document.referrer);
    if (!action) return;
    if (action.gigafileKeyRequired) {
      // Unknown, signed-out and older servers leave the site's own download
      // behavior untouched. Capability is prefetched before the user clicks.
      if (!readinessCache?.ready || !readinessCache.gigafileDownloadKeySupported) return;
      const input = document.querySelector('#dlkey');
      const downloadKey = String(input?.value || '');
      if (downloadKey.length < 1 || downloadKey.length > 4) {
        event.preventDefault(); event.stopImmediatePropagation(); input?.focus(); show(text.gigafileKeyPrompt); return;
      }
      action.downloadKey = downloadKey;
      if (input) input.value = '';
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!pending) void (action.captureDownload ? armDownload(action, element) : send(action));
  }, true);
})();
