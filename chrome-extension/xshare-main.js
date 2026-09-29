(() => {
  const originalClick=HTMLAnchorElement.prototype.click;
  let armed=null;

  function safeIssuedUrl(value,shareId) {
    try {
      const url=new URL(String(value || ''),location.href);
      const keys=[...url.searchParams.keys()];
      const key=url.searchParams.get('key') || '';
      if (url.protocol !== 'https:' || url.hostname !== 'x-share.net' || url.port
        || url.username || url.password || url.hash || url.pathname !== `/api/download/${shareId}`
        || keys.length !== 1 || keys[0] !== 'key' || url.searchParams.getAll('key').length !== 1
        || key.length < 1 || key.length > 4096 || !/^[\x21-\x7e]+$/.test(key)) return '';
      return url.href;
    } catch { return ''; }
  }

  document.addEventListener('__nasdrop_xshare_arm_v1',event => {
    const shareId=String(event.detail?.shareId || '');
    const expiresAt=Number(event.detail?.expiresAt || 0);
    if (!/^[A-Za-z0-9_-]{6,64}$/.test(shareId) || expiresAt <= Date.now() || expiresAt > Date.now()+65000) return;
    armed={shareId,expiresAt};
  },true);

  HTMLAnchorElement.prototype.click=function(...args) {
    const current=armed;
    const issued=current && current.expiresAt > Date.now() && this.hasAttribute('download')
      ? safeIssuedUrl(this.getAttribute('href'),current.shareId) : '';
    if (!issued) return Reflect.apply(originalClick,this,args);
    armed=null;
    document.dispatchEvent(new CustomEvent('__nasdrop_xshare_url_v1',{detail:issued}));
  };
})();
