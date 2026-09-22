/* Shared by the isolated content script and service worker. No page code is evaluated. */
globalThis.NASDropProviders = (() => {
  const id = '[A-Za-z0-9_-]+';
  function parse(value, base) {
    try {
      if (typeof value !== 'string' || /[\x00-\x20\x7f\\]/.test(value) || value.length > 8192) return null;
      const url = new URL(value, base);
      return url.protocol === 'https:' && !url.username && !url.password && !url.port ? url : null;
    } catch { return null; }
  }
  function provider(value) {
    const u = parse(value);
    if (!u) return '';
    if (/^[a-z0-9-]+\.gigafile\.nu$/.test(u.hostname)) return 'gigafile';
    if (['gofile.io', 'www.gofile.io'].includes(u.hostname)) return 'gofile';
    if (['pixeldrain.com', 'www.pixeldrain.com', 'pixeldrain.net', 'pixeldra.in'].includes(u.hostname)) return 'pixeldrain';
    if (['buzzheavier.com', 'www.buzzheavier.com'].includes(u.hostname)) return 'buzzheavier';
    if (['akirabox.to', 'akirabox.com'].includes(u.hostname)) return 'akirabox';
    if (['vik1ngfile.site', 'vikingfile.com'].includes(u.hostname)) return 'vikingfile';
    if (['send.now', 'www.send.now'].includes(u.hostname)) return 'sendnow';
    return '';
  }
  function share(value) {
    const u = parse(value);
    const type = provider(value);
    if (!u || !type) return '';
    if (type === 'akirabox') return new RegExp(`^/${id}/file/?$`).test(u.pathname) ? u.origin + u.pathname.replace(/\/$/, '') : '';
    if (type === 'vikingfile') return new RegExp(`^/f/${id}/?$`).test(u.pathname) ? u.origin + u.pathname.replace(/\/$/, '') : '';
    if (type === 'sendnow') return new RegExp(`^/(?:d/)?${id}/?$`).test(u.pathname) && !u.search && !u.hash ? u.origin + u.pathname.replace(/\/$/, '') : '';
    const prefix = type === 'gofile' ? '/d/' : type === 'pixeldrain' ? '/u/' : '/';
    return new RegExp(`^${prefix}${id}/?$`).test(u.pathname) ? u.origin + u.pathname.replace(/\/$/, '') : '';
  }
  function signedBuzz(value, page) {
    const u = parse(value), p = parse(page);
    return Boolean(u && p && /^[a-z0-9-]+\.buzzheavier\.com$/.test(u.hostname)
      && u.pathname === `/d${p.pathname.replace(/\/$/, '')}`
      && [...u.searchParams.keys()].length === 1 && u.searchParams.has('v')
      && /^[A-Za-z0-9._~+-]+$/.test(u.searchParams.get('v')));
  }
  function buzzEndpoint(raw, page) {
    const u = parse(raw, page), p = parse(page);
    if (!u || !p || u.origin !== p.origin || u.pathname !== `${p.pathname.replace(/\/$/, '')}/download`) return '';
    return u.href;
  }
  function resolve(element, page, sourcePage = '') {
    const source = share(page) || share(sourcePage);
    const type = provider(source || page);
    if (!type || !source || !element) return null;
    const a = name => element.getAttribute(name) || '';
    const href = parse(a('href'), page);
    if (type === 'sendnow') {
      const current = parse(page);
      if (element.matches('button#downloadbtn') && current?.origin === new URL(source).origin
        && current.pathname === '/' && !current.search && !current.hash) {
        return {handoff:'sendnow', captureDownload:true, source};
      }
    }
    if (type === 'akirabox' || type === 'vikingfile' || type === 'sendnow') {
      const result = classifyHandoff(element, page, source);
      if (result.kind === 'file') return {url:result.url, handoff:result.provider};
      if (result.kind === 'expired') return {error:'expiredLink'};
      return null;
    }
    if (type === 'buzzheavier') {
      if (a('href') && signedBuzz(href?.href, page)) return {url: href.href};
      const endpoint = buzzEndpoint(a('hx-get') || a('data-hx-get'), page);
      if (element.matches('a.download-btn') && endpoint) return {endpoint};
      // Read the literal argument only; never execute the inline handler.
      const copy = a('onclick').match(/^\s*copyDownloadLink\(\s*(['"])(.*?)\1\s*\)\s*;?\s*$/);
      if (element.matches('a.copy') && copy) {
        const copiedEndpoint = buzzEndpoint(copy[2].replace(/\\\//g, '/'), page);
        if (copiedEndpoint) return {endpoint: copiedEndpoint};
      }
      return null;
    }
    if (type === 'gigafile') {
      // GigaFile's official controls use download(file, keyRequired, ...).
      // Parse literal arguments only; never execute page JavaScript.
      const call = (a('onclick') || a('href')).match(/^(?:javascript:)?\s*(?:return\s+)?download\(\s*(['"])([A-Za-z0-9_-]+)\1\s*,\s*(true|false)\s*,\s*(true|false)\s*\)\s*;?\s*$/);
      const official = element.matches('button.download_panel_btn_dl.gfbtn, span#dl.download_file_caption');
      if (call && official) return {url: `${new URL(page).origin}/${call[2]}`, gigafileKeyRequired:call[3] === 'true'};
      if (a('href') && href?.origin === new URL(page).origin && ['/download.php', '/bypass_dl.php'].includes(href.pathname)) {
        const file = href.searchParams.get('file');
        if (file && new RegExp(`^${id}$`).test(file)) return {url: `${href.origin}/${file}`};
      }
    }
    if (type === 'gofile' && a('data-action') === 'download') {
      const row = element.closest('.fm-row[data-id]');
      const file = row?.getAttribute('data-id');
      if (file && new RegExp(`^${id}$`).test(file)) return {url: `https://gofile.io/d/${file}`};
      return {url: source};
    }
    if (type === 'pixeldrain') {
      if (a('href') && href && provider(href.href) === type && new RegExp(`^/api/file/${id}$`).test(href.pathname) && href.searchParams.has('download')) {
        return {url: `${href.origin}/u/${href.pathname.split('/').pop()}`};
      }
      // Only the first-party file viewer's explicit download control; never text-only matches.
      if (element.matches('button#download, button#download_button, button.download_button, a#download')) return {url: source};
      // Current Svelte viewer: hashed classes vary between builds. Match the stable
      // viewer region, button class and direct icon, including clicks on nested spans.
      const viewerButton = (element.matches('button.toolbar_button') && element.closest('.toolbar'))
        || (element.matches('button.button_highlight') && element.closest('.description'));
      if (viewerButton && element.querySelector(':scope > i.icon')?.textContent.trim() === 'download') return {url: source};
    }
    return null;
  }
  function allowedSubmission(page, value) {
    const type = provider(page);
    if (!share(page)) return false;
    if (type === 'akirabox' || type === 'vikingfile' || type === 'sendnow') return validHandoffURL(value, type, page);
    if (type === 'buzzheavier') return signedBuzz(value, page);
    return Boolean(share(value) && provider(value) === type && (type !== 'gigafile' || new URL(value).origin === new URL(page).origin));
  }
  function handoffURL(value, type, page = '') {
    const u = parse(value);
    if (!u || u.hash) return null;
    if (type === 'sendnow') {
      const source = share(page);
      if (!source || u.href === source || u.href === `${source}/`) return null;
      // Send.now may rotate its first-party/CDN download hosts, so do not pin a
      // single observed hostname. Keep the browser-side check structural and
      // leave DNS/redirect/content validation to the NAS server.
      if (!u.hostname || u.hostname === 'localhost' || u.hostname.endsWith('.localhost')
        || u.hostname.endsWith('.local') || /^\d{1,3}(?:\.\d{1,3}){3}$/.test(u.hostname)
        || u.hostname.includes(':')) return null;
      if (['send.now','www.send.now'].includes(u.hostname) && !u.search && new RegExp(`^/(?:d/)?${id}/?$`).test(u.pathname)) return null;
      return u;
    }
    const parts = u.pathname.split('/');
    if (parts.length !== 4 || !parts[2] || !parts[3]) return null;
    let filename;
    try { filename = decodeURIComponent(parts[3]); } catch { return null; }
    if (!filename || filename === '.' || filename === '..' || /[\/\\\x00-\x1f\x7f]/.test(filename)) return null;
    if (type === 'akirabox') {
      if (u.hostname !== 'akirabox.com' || parts[1] !== 'download' || !/^[A-Za-z0-9_+=-]+$/.test(parts[2])) return null;
      if ([...u.searchParams.keys()].length !== 2 || u.searchParams.getAll('expiration').length !== 1 || u.searchParams.getAll('signature').length !== 1) return null;
      if (!/^\d{10,11}$/.test(u.searchParams.get('expiration')) || !/^[a-f0-9]{64}$/i.test(u.searchParams.get('signature'))) return null;
    } else if (type === 'vikingfile') {
      if (u.hostname !== 'vikingfile.com' || parts[1] !== 'd' || !/^[A-Za-z0-9_-]+$/.test(parts[2]) || u.search) return null;
    } else return null;
    return u;
  }
  function validHandoffURL(value, type, page = '') {
    const u = handoffURL(value,type,page);
    return Boolean(u && (type !== 'akirabox' || Number(u.searchParams.get('expiration')) > Date.now()/1000));
  }
  // Structural classification only. The server must validate redirects and the
  // real response: an opaque token alone cannot prove file identity or access.
  function classifyHandoff(element, page, sourcePage = '') {
    const source = share(page) || share(sourcePage);
    const type = provider(source || page);
    if (!source || !['akirabox','vikingfile','sendnow'].includes(type)) return {kind:'unrelated'};
    const official = type === 'akirabox' ? element.matches('a#download.download-button')
      : type === 'vikingfile' ? element.matches('a#download-link.button')
      : element.matches('#direct_link a[href]') || element.matches('a#downloadbtn[href]');
    if (!official) return {kind:'unrelated'};
    if (type === 'akirabox' && element.getAttribute('aria-disabled') !== 'false') return {kind:'preparing'};
    if (element.getAttribute('aria-disabled') === 'true' || element.hasAttribute?.('disabled')) return {kind:'preparing'};
    const raw = element.getAttribute('href') || '';
    if (!raw || raw === '#') return {kind:'preparing'};
    const u = handoffURL(raw,type,source);
    if (!u) return {kind:'unrecognized'};
    if (!validHandoffURL(raw,type,source)) return {kind:'expired'};
    return {kind:'file', provider:type, url:u.href};
  }
  async function resolveBuzzLink(endpoint, page, request = fetch) {
    if (!buzzEndpoint(endpoint, page)) throw new Error('Invalid download request.');
    const response = await request(endpoint, {
      headers: {'HX-Request': 'true'}, credentials: 'same-origin',
      redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(20000),
    });
    const link = response.headers.get('HX-Redirect');
    if (!response.ok || !signedBuzz(link, page)) throw new Error('Buzzheavier did not provide a download link. Refresh the page and try again.');
    // Never follow this URL here: only NASDrop may transfer the file body.
    return link;
  }
  return {provider, share, signedBuzz, resolve, allowedSubmission, resolveBuzzLink, classifyHandoff, validHandoffURL};
})();
