(() => {
  const $ = (selector) => document.querySelector(selector);
  const t = (key, vars) => window.NASDropI18n.t(key, vars);
  const launchedToken = new URLSearchParams(location.hash.slice(1)).get("token") || "";
  if (launchedToken) history.replaceState(null, "", location.pathname + location.search);
  const state = { token: launchedToken || localStorage.getItem("nasdrop-session-token") || "", jobs: [], status: null, timer: null, selectedTarget: "", folder: null, folderPurpose: "job", account: null, accountResetMode: false, selected: new Set(), extractionInitialized: false };
  const statusKeys = { queued:"statusQueued", ready:"statusReady", downloading:"statusDownloading", waiting_processing:"statusWaitingProcessing", verifying:"statusVerifying", extracting:"statusExtracting", publishing:"statusPublishing", password_required:"statusPasswordRequired", paused:"statusPaused", completed:"statusCompleted", failed:"statusFailed", cancelled:"statusCancelled" };

  function bytes(value) {
    if (!Number.isFinite(value) || value <= 0) return "0 B";
    const units = ["B","KB","MB","GB","TB"];
    const i = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / 1024 ** i).toFixed(i > 2 ? 2 : 1)} ${units[i]}`;
  }
  function esc(value) { const node = document.createElement("span"); node.textContent = String(value ?? ""); return node.innerHTML; }
  async function api(path, init = {}) {
    const response = await fetch(path, { ...init, headers:{ "content-type":"application/json", authorization:`Bearer ${state.token}`, ...(init.headers || {}) } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || t("requestFailed"));
    return payload;
  }
  async function publicApi(path, init = {}) {
    const response = await fetch(path, { ...init, headers:{ "content-type":"application/json", ...(init.headers || {}) } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || t("requestFailed"));
    return payload;
  }
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); refresh(); state.timer = setInterval(refreshJobs, 2500); }
  function showLogin(message = "") { clearInterval(state.timer); $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); $("#login-error").textContent = message; }
  async function refresh() {
    try { const [status, jobs, account] = await Promise.all([api("/api/status"), api("/api/jobs"), api("/api/account")]); state.status = status; state.jobs = jobs.jobs; state.account = account; renderStatus(); renderJobs(); renderAccount(); }
    catch (error) { localStorage.removeItem("nasdrop-session-token"); state.token = ""; showLogin(error.message); }
  }
  async function refreshJobs() { try { state.jobs = (await api("/api/jobs")).jobs; renderJobs(); } catch (_) {} }
  function renderStatus() {
    const s = state.status;
    if (!state.selectedTarget) state.selectedTarget = s.target;
    const effectiveTarget = state.selectedTarget || s.target;
    const effectiveWritable = Boolean(effectiveTarget) && (effectiveTarget !== s.target || s.target_writable);
    $("#destination").textContent = effectiveTarget || t("notSelected");
    $("#write-state").textContent = effectiveTarget ? (effectiveWritable ? t("writable") : t("permissionRequired")) : t("notSelected");
    $("#write-state").className = effectiveTarget && effectiveWritable ? "ok" : "bad";
    $("#setting-target").textContent = s.target || t("notSelected");
    $("#setting-write").textContent = s.target ? (s.target_writable ? t("packageWritable") : t("permissionRequired")) : t("notSelected");
    $("#setting-write").className = `badge ${s.target && s.target_writable ? "ok" : "bad"}`;
    $("#service-user").textContent = s.service_user || t("dedicatedAccount");
    $("#service-url").textContent = location.origin;
    $("#launcher-port").value = String(s.launcher_port || 8791);
    $("#version").textContent = s.version;
    const gofileCooldown = s.gofile_cooldown || {};
    const gofileNotice = $("#gofile-cooldown");
    gofileNotice.classList.toggle("hidden", !gofileCooldown.active);
    if (gofileCooldown.active) {
      const until = new Date(Number(gofileCooldown.until) * 1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
      gofileNotice.textContent = t("gofileCooldown", {time:until});
    }
    const sameProviderEnabled = Boolean(s.same_provider_parallel);
    $("#same-provider-parallel").checked = sameProviderEnabled;
    $("#same-provider-limit").value = String(s.same_provider_limit || 2);
    $("#same-provider-limit").disabled = !sameProviderEnabled;
    $("#concurrency-summary").textContent = sameProviderEnabled ? t("sameServiceSummary", {count:s.same_provider_limit}) : t("off");
    $("#concurrency-summary").className = `badge ${sameProviderEnabled ? "ok" : ""}`;
    const downloadMode = s.download_mode === "single" ? "single" : "segmented";
    $("#download-mode").value = downloadMode;
    $("#download-mode-summary").textContent = t(downloadMode === "single" ? "singleModeShort" : "segmentedModeShort");
    $("#download-mode-summary").className = `badge ${downloadMode === "single" ? "ok" : ""}`;
    $("#auto-extract-archives").checked = Boolean(s.auto_extract_archives);
    $("#disk-protection").checked = Boolean(s.disk_protection);
    $("#processing-summary").textContent = s.auto_extract_archives ? t("autoExtractOn") : t("autoExtractOff");
    $("#processing-summary").className = `badge ${s.auto_extract_archives ? "ok" : ""}`;
    $("#temp-folder-name").textContent = s.temporary_folder || ".nasdrop-tmp";
    $("#archive-engine").textContent = s.seven_zip_available ? t("engineReady") : t("engineMissing");
    $("#archive-engine").className = `badge ${s.seven_zip_available ? "ok" : "bad"}`;
    if (!state.extractionInitialized) {
      $("#extract-download").checked = Boolean(s.auto_extract_archives);
      $("#archive-password-wrap").classList.toggle("hidden", !s.auto_extract_archives);
      state.extractionInitialized = true;
    }
  }
  function renderAccount() {
    if (!state.account) return;
    const launcherResetAvailable = Boolean(state.account.configured && state.account.launcher_session);
    const locked = launcherResetAvailable && !state.accountResetMode;
    const username = $("#account-username");
    const password = $("#new-password");
    const confirmation = $("#confirm-password");
    username.value = state.account.username || "";
    $("#account-current-id").textContent = state.account.username || "—";
    $("#account-locked-summary").classList.toggle("hidden", !locked);
    $("#account-username-row").classList.toggle("hidden", locked);
    $("#new-password-row").classList.toggle("hidden", locked);
    $("#confirm-password-row").classList.toggle("hidden", locked);
    password.required = !locked;
    confirmation.required = !locked;
    password.placeholder = "";
    confirmation.placeholder = "";
    $("#save-account").disabled = locked;
    $("#reset-account").classList.toggle("hidden", !launcherResetAvailable);
    $("#current-password-row").classList.toggle("hidden", !state.account.configured || state.account.launcher_session);
  }
  async function loadAccount() {
    try { state.account = await api("/api/account"); renderAccount(); }
    catch (error) { $("#account-message").textContent = error.message; }
  }
  function renderJobs() {
    const active = state.jobs.filter(j => ["queued","ready","downloading","waiting_processing","verifying","extracting","publishing"].includes(j.status));
    const existing = new Set(state.jobs.map(job => job.id));
    state.selected.forEach(id => { if (!existing.has(id)) state.selected.delete(id); });
    $("#queue-summary").textContent = active.length ? t("processing", {count:active.length}) : t("noQueuedJobs");
    $("#clear-completed").disabled = !state.jobs.some(job => job.status === "completed");
    if (!state.jobs.length) { $("#jobs").innerHTML = `<div class="empty"><b>${esc(t("noJobsTitle"))}</b><span>${esc(t("noJobsHint"))}</span></div>`; renderSelectionToolbar(); return; }
    $("#jobs").innerHTML = state.jobs.map(job => {
      const pct = job.size ? Math.min(100, Math.round(job.downloaded / job.size * 100)) : 0;
      const statusLabel = job.status === "queued" && job.not_before > Date.now() / 1000 ? t("scheduled") : (statusKeys[job.status] ? t(statusKeys[job.status]) : esc(job.status));
      const passwordForm = job.status === "password_required" ? `<form class="job-password" data-id="${job.id}"><input type="password" name="password" autocomplete="new-password" maxlength="256" required placeholder="${esc(t("archivePassword"))}"><button type="submit" class="ghost">${esc(t("retryExtraction"))}</button></form>` : "";
      return `<article class="job ${state.selected.has(job.id) ? "selected" : ""}"><label class="job-check"><input type="checkbox" data-id="${job.id}" ${state.selected.has(job.id) ? "checked" : ""}><span></span></label><div class="status-dot ${job.status}"></div><div class="job-main"><div class="job-title"><strong>${esc(job.name)}</strong><span class="job-status">${statusLabel}</span></div><div class="progress"><i style="width:${pct}%"></i></div><div class="job-meta"><span>${bytes(job.downloaded)} / ${bytes(job.size)}</span><span>${pct}%</span><span class="job-target">${esc(job.output || job.target || state.status?.target || "")}</span></div>${job.extracted ? `<p class="job-result">${esc(t("archiveExtracted"))}</p>` : ""}${job.error ? `<p class="error">${esc(job.error)}</p>` : ""}${passwordForm}${job.sha256 ? `<details><summary>${esc(t("integrity"))}</summary><code>SHA-256 ${esc(job.sha256)}</code></details>` : ""}</div></article>`;
    }).join("");
    renderSelectionToolbar();
  }
  function selectedJobs() { return state.jobs.filter(job => state.selected.has(job.id)); }
  function renderSelectionToolbar() {
    const selected = selectedJobs();
    $("#selection-toolbar").classList.toggle("hidden", !selected.length);
    $("#selection-count").textContent = t("selected", {count:selected.length});
    $("#select-all").textContent = selected.length === state.jobs.length && state.jobs.length ? t("clearSelection") : t("selectAll");
    $("#pause-selected").disabled = !selected.some(job => ["queued","ready","downloading","waiting_processing","verifying"].includes(job.status));
    $("#resume-selected").disabled = !selected.some(job => ["paused","failed","cancelled"].includes(job.status));
    $("#delete-selected").disabled = !selected.some(job => !["queued","ready","downloading","waiting_processing","verifying","extracting","publishing"].includes(job.status));
  }
  async function runSelected(action) {
    const selected = selectedJobs();
    let jobs = selected;
    if (action === "pause") jobs = selected.filter(job => ["queued","ready","downloading","waiting_processing","verifying"].includes(job.status));
    if (action === "resume") jobs = selected.filter(job => ["paused","failed","cancelled"].includes(job.status));
    if (action === "delete") jobs = selected.filter(job => !["queued","ready","downloading","waiting_processing","verifying","extracting","publishing"].includes(job.status));
    if (!jobs.length) return;
    if (action === "delete" && !confirm(t("confirmDelete", {count:jobs.length}))) return;
    try {
      if (action === "delete") await api("/api/jobs/delete", {method:"POST",body:JSON.stringify({ids:jobs.map(job => job.id)})});
      else await Promise.all(jobs.map(job => api(`/api/jobs/${job.id}/${action}`, {method:"POST",body:"{}"})));
      jobs.forEach(job => state.selected.delete(job.id));
      await refreshJobs();
    } catch (error) { $("#notice").textContent = error.message; }
  }
  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("#login-error").textContent = "";
    try {
      const result = await publicApi("/api/login", {method:"POST",body:JSON.stringify({username:$("#login-username").value.trim(),password:$("#login-password").value})});
      state.token = result.token; localStorage.setItem("nasdrop-session-token", state.token); $("#login-password").value = ""; showApp();
    } catch (error) { $("#login-error").textContent = error.message; }
  });
  $("#download-form").addEventListener("submit", async (event) => { event.preventDefault(); const button = $("#start-button"); const url = $("#download-url").value.trim(); const extract = $("#extract-download").checked; const password = extract ? $("#archive-password").value : ""; button.disabled = true; $("#notice").textContent = t("inspectLink"); try { const checked = await api("/api/inspect", {method:"POST",body:JSON.stringify({url})}); const started = await api("/api/start", {method:"POST",body:JSON.stringify({...checked.file,target:state.selectedTarget,extract,password})}); $("#download-url").value = ""; $("#archive-password").value = ""; $("#notice").textContent = started.count > 1 ? t("addedMany", {count:started.count,target:state.selectedTarget}) : t("addedOne", {name:checked.file.name,target:state.selectedTarget}); await refreshJobs(); } catch (error) { $("#notice").textContent = error.message; } finally { button.disabled = false; } });
  $("#extract-download").addEventListener("change", event => { $("#archive-password-wrap").classList.toggle("hidden", !event.target.checked); if (!event.target.checked) $("#archive-password").value = ""; });
  $("#jobs").addEventListener("change", event => { const checkbox = event.target.closest("input[data-id]"); if (!checkbox) return; checkbox.checked ? state.selected.add(checkbox.dataset.id) : state.selected.delete(checkbox.dataset.id); renderJobs(); });
  $("#jobs").addEventListener("submit", async event => { const form = event.target.closest(".job-password"); if (!form) return; event.preventDefault(); const button = form.querySelector("button"); const password = form.elements.password.value; button.disabled = true; try { await api(`/api/jobs/${form.dataset.id}/password`, {method:"POST",body:JSON.stringify({password})}); await refreshJobs(); } catch (error) { $("#notice").textContent = error.message; button.disabled = false; } });
  $("#select-all").addEventListener("click", () => { if (state.selected.size === state.jobs.length) state.selected.clear(); else state.jobs.forEach(job => state.selected.add(job.id)); renderJobs(); });
  $("#pause-selected").addEventListener("click", () => runSelected("pause"));
  $("#resume-selected").addEventListener("click", () => runSelected("resume"));
  $("#delete-selected").addEventListener("click", () => runSelected("delete"));
  $("#clear-completed").addEventListener("click", async () => { const count = state.jobs.filter(job => job.status === "completed").length; if (!count || !confirm(t("confirmClear", {count}))) return; try { await api("/api/jobs/completed/clear", {method:"POST",body:"{}"}); state.selected.clear(); await refreshJobs(); } catch (error) { $("#notice").textContent = error.message; } });
  $("#same-provider-parallel").addEventListener("change", event => { $("#same-provider-limit").disabled = !event.target.checked; });
  $("#save-download-behavior").addEventListener("click", async () => {
    const enabled = $("#same-provider-parallel").checked;
    const limit = Number($("#same-provider-limit").value);
    if (enabled && !confirm(t("confirmParallel", {count:limit}))) return;
    const mode = $("#download-mode").value;
    if (mode === "single" && !confirm(t("confirmSingleMode"))) return;
    const button = $("#save-download-behavior"); button.disabled = true; $("#download-behavior-message").textContent = t("saving");
    try {
      await api("/api/settings", {method:"POST",body:JSON.stringify({same_provider_parallel:enabled,same_provider_limit:limit,download_mode:mode})});
      state.status = await api("/api/status"); renderStatus();
      $("#download-behavior-message").textContent = t("downloadBehaviorSaved");
    } catch (error) { $("#download-behavior-message").textContent = error.message; }
    finally { button.disabled = false; }
  });
  $("#save-launcher-port").addEventListener("click", async () => {
    const rawPort = $("#launcher-port").value.trim();
    const port = rawPort ? Number(rawPort) : 8791;
    const button = $("#save-launcher-port"); button.disabled = true; $("#launcher-port-message").textContent = t("saving");
    try {
      const result = await api("/api/settings", {method:"POST",body:JSON.stringify({launcher_port:port})});
      state.status = await api("/api/status"); renderStatus();
      $("#launcher-port-message").textContent = t("launcherPortSaved", {port:result.launcher_port});
    } catch (error) { $("#launcher-port-message").textContent = error.message; }
    finally { button.disabled = false; }
  });
  $("#save-processing").addEventListener("click", async () => {
    const enabled = $("#auto-extract-archives").checked;
    const diskProtection = $("#disk-protection").checked;
    const button = $("#save-processing"); button.disabled = true; $("#processing-message").textContent = t("saving");
    try {
      await api("/api/settings", {method:"POST",body:JSON.stringify({auto_extract_archives:enabled,disk_protection:diskProtection})});
      state.status = await api("/api/status"); renderStatus();
      $("#processing-message").textContent = enabled ? t("processingSavedOn") : t("processingSavedOff");
    } catch (error) { $("#processing-message").textContent = error.message; }
    finally { button.disabled = false; }
  });
  document.querySelectorAll(".nav").forEach(button => button.addEventListener("click", () => { document.querySelectorAll(".nav").forEach(x => x.classList.toggle("active", x === button)); $("#dashboard-view").classList.toggle("hidden", button.dataset.view !== "dashboard"); $("#settings-view").classList.toggle("hidden", button.dataset.view !== "settings"); if (button.dataset.view === "settings") loadAccount(); }));
  $("#logout-button").addEventListener("click", async () => {
    try { await api("/api/logout", {method:"POST",body:"{}"}); } catch (_) {}
    localStorage.removeItem("nasdrop-session-token"); state.token = ""; showLogin();
  });
  async function loadFolder(path) {
    $("#folder-list").innerHTML = `<div class="folder-loading">${esc(t("loadingFolders"))}</div>`;
    $("#folder-message").textContent = "";
    try {
      state.folder = await api(`/api/folders?path=${encodeURIComponent(path)}`);
      $("#folder-current").textContent = state.folder.path;
      $("#folder-up").disabled = !state.folder.parent;
      $("#folder-select").disabled = !state.folder.writable;
      $("#folder-message").textContent = state.folder.writable ? t("currentWritable") : t("currentNotWritable");
      $("#folder-list").innerHTML = state.folder.folders.length ? state.folder.folders.map(folder => `<button class="folder-item ${folder.readable === false ? "locked" : ""}" data-path="${esc(folder.path)}" ${folder.readable === false ? "disabled" : ""}><span>${folder.readable === false ? "🔒" : "📁"}</span><b>${esc(folder.name)}</b><em class="${folder.writable ? "ok" : folder.readable === false ? "locked" : ""}">${folder.writable ? t("writable") : folder.readable === false ? t("permissionRequired") : t("browse")}</em></button>`).join("") : `<div class="folder-loading">${esc(t("noSubfolders"))}</div>`;
    } catch (error) { $("#folder-list").innerHTML = ""; $("#folder-message").textContent = error.message; }
  }
  function openFolder(purpose, path) { state.folderPurpose = purpose; $("#folder-modal").classList.remove("hidden"); loadFolder(path); }
  $("#choose-folder").addEventListener("click", () => openFolder("job", state.selectedTarget || state.status?.target || "/"));
  $("#change-default-folder").addEventListener("click", () => openFolder("default", state.status?.target || "/"));
  $("#folder-list").addEventListener("click", event => { const item = event.target.closest(".folder-item"); if (item) loadFolder(item.dataset.path); });
  $("#folder-up").addEventListener("click", () => { if (state.folder?.parent) loadFolder(state.folder.parent); });
  function closeFolder() { $("#folder-modal").classList.add("hidden"); }
  $("#folder-close").addEventListener("click", closeFolder);
  $("#folder-cancel").addEventListener("click", closeFolder);
  $("#folder-select").addEventListener("click", async () => {
    if (!state.folder?.writable) return;
    if (state.folderPurpose === "default") {
      try {
        await api("/api/settings", {method:"POST",body:JSON.stringify({target:state.folder.path})});
        state.status = await api("/api/status");
        state.selectedTarget = state.status.target;
        renderStatus();
        $("#notice").textContent = t("defaultChanged", {target:state.status.target});
        closeFolder();
      } catch (error) { $("#folder-message").textContent = error.message; }
      return;
    }
    state.selectedTarget = state.folder.path;
    $("#destination").textContent = state.selectedTarget;
    $("#write-state").textContent = t("writable");
    $("#write-state").className = "ok";
    closeFolder();
  });
  $("#account-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = $("#new-password").value;
    if (password !== $("#confirm-password").value) { $("#account-message").textContent = t("passwordMismatch"); return; }
    const button = $("#account-form button[type=submit]"); button.disabled = true; $("#account-message").textContent = t("saving");
    try {
      const result = await api("/api/account", {method:"POST",body:JSON.stringify({username:$("#account-username").value.trim(),current_password:$("#current-password").value,password})});
      if (result.token) { state.token = result.token; localStorage.setItem("nasdrop-session-token", state.token); }
      $("#current-password").value = ""; $("#new-password").value = ""; $("#confirm-password").value = "";
      state.accountResetMode = false;
      await loadAccount(); $("#account-message").textContent = t("accountSaved");
    } catch (error) { $("#account-message").textContent = error.message; }
    finally { button.disabled = false; }
  });
  $("#reset-account").addEventListener("click", () => {
    state.accountResetMode = true;
    $("#new-password").value = "";
    $("#confirm-password").value = "";
    renderAccount();
    $("#account-message").textContent = t("resetAccountHint");
    $("#account-username").focus();
  });
  window.addEventListener("nasdrop-language-change", () => {
    if (state.status) renderStatus();
    renderJobs();
    renderAccount();
    if (state.folder) loadFolder(state.folder.path);
  });
  async function bootstrap() {
    if (state.token) { showApp(); return; }
    try { const auth = await publicApi("/api/auth/status"); $("#login-setup-hint").classList.toggle("hidden", auth.configured); }
    catch (_) {}
  }
  bootstrap();
})();
