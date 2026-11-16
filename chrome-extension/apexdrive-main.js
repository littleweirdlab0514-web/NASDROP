(() => {
  const originalClick=HTMLAnchorElement.prototype.click;
  let armedUntil=0;

  function issuedUrl(value) {
    try {
      const url=new URL(String(value || ''),location.href);
      const keys=[...url.searchParams.keys()];
      const verify=url.searchParams.get('verify') || '';
      const filename=url.searchParams.get('fn') || '';
      if (url.protocol !== 'https:' || url.hostname !== 'd.linatalksbayou.com' || url.port
        || url.username || url.password || url.hash
        || !/^\/xbox-apex\/\d{1,20}\/[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.[A-Za-z0-9]{1,10}$/i.test(url.pathname)
        || keys.length !== 2 || !keys.includes('verify') || !keys.includes('fn')
        || url.searchParams.getAll('verify').length !== 1 || url.searchParams.getAll('fn').length !== 1
        || !/^\d{10}-[A-Za-z0-9._~+/=-]{16,4096}$/.test(verify)
        || !filename || filename.length > 1024 || filename === '.' || filename === '..'
        || /[\/\\\x00-\x1f\x7f]/.test(filename)) return '';
      return url.href;
    } catch { return ''; }
  }

  document.addEventListener('__nasdrop_apexdrive_arm_v1',event => {
    const expiresAt=Number(event.detail?.expiresAt || 0);
    if (expiresAt <= Date.now() || expiresAt > Date.now()+86400000) return;
    armedUntil=expiresAt;
  },true);

  HTMLAnchorElement.prototype.click=function(...args) {
    const issued=armedUntil > Date.now() ? issuedUrl(this.getAttribute('href')) : '';
    if (!issued) return Reflect.apply(originalClick,this,args);
    document.dispatchEvent(new CustomEvent('__nasdrop_apexdrive_url_v1',{detail:issued}));
  };
})();
