(() => {
  const $ = (selector) => document.querySelector(selector);
  const t = (key, vars) => window.NASDropI18n.t(key, vars);
  const launchedToken = new URLSearchParams(location.hash.slice(1)).get("token") || "";
  if (launchedToken) { localStorage.setItem("nas-download-token", launchedToken); history.replaceState(null, "", location.pathname + location.search); }
  const state = { token: launchedToken || localStorage.getItem("nas-download-token") || "", jobs: [], status: null, timer: null, selectedTarget: "", folder: null, folderPurpose: "job", pairing: null, codeVisible: false, selected: new Set() };
  const statusKeys = { queued:"statusQueued", ready:"statusReady", downloading:"statusDownloading", verifying:"statusVerifying", paused:"statusPaused", completed:"statusCompleted", failed:"statusFailed", cancelled:"statusCancelled" };

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
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); refresh(); state.timer = setInterval(refreshJobs, 2500); }
  function showLogin(message = "") { clearInterval(state.timer); $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); $("#login-error").textContent = message; }
  async function refresh() {
    try { const [status, jobs] = await Promise.all([api("/api/status"), api("/api/jobs")]); state.status = status; state.jobs = jobs.jobs; renderStatus(); renderJobs(); }
    catch (error) { showLogin(error.message); }
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
  }
  function renderPairing() {
    if (!state.pairing) return;
    $("#access-code").textContent = state.codeVisible ? state.pairing.token : "••••••••••••••••••••";
    $("#reveal-code").textContent = state.codeVisible ? t("hideCode") : t("showCode");
    try {
      qrcode.stringToBytes = qrcode.stringToBytesFuncs["UTF-8"];
      const qr = qrcode(0, "M");
      qr.addData(state.pairing.uri);
      qr.make();
      $("#pairing-qr").innerHTML = qr.createImgTag(5, 12, t("qrAlt"));
    } catch (error) { $("#pairing-qr").textContent = t("qrFailed", {error:error.message}); }
  }
  async function loadPairing() {
    try { state.pairing = await api("/api/pairing"); renderPairing(); }
    catch (error) { $("#pairing-message").textContent = error.message; }
  }
  function renderJobs() {
    const active = state.jobs.filter(j => ["queued","ready","downloading","verifying"].includes(j.status));
    const existing = new Set(state.jobs.map(job => job.id));
    state.selected.forEach(id => { if (!existing.has(id)) state.selected.delete(id); });
    $("#queue-summary").textContent = active.length ? t("processing", {count:active.length}) : t("noQueuedJobs");
    $("#clear-completed").disabled = !state.jobs.some(job => job.status === "completed");
    if (!state.jobs.length) { $("#jobs").innerHTML = `<div class="empty"><b>${esc(t("noJobsTitle"))}</b><span>${esc(t("noJobsHint"))}</span></div>`; renderSelectionToolbar(); return; }
    $("#jobs").innerHTML = state.jobs.map(job => {
      const pct = job.size ? Math.min(100, Math.round(job.downloaded / job.size * 100)) : 0;
      const statusLabel = job.status === "queued" && job.not_before > Date.now() / 1000 ? t("scheduled") : (statusKeys[job.status] ? t(statusKeys[job.status]) : esc(job.status));
      return `<article class="job ${state.selected.has(job.id) ? "selected" : ""}"><label class="job-check"><input type="checkbox" data-id="${job.id}" ${state.selected.has(job.id) ? "checked" : ""}><span></span></label><div class="status-dot ${job.status}"></div><div class="job-main"><div class="job-title"><strong>${esc(job.name)}</strong><span class="job-status">${statusLabel}</span></div><div class="progress"><i style="width:${pct}%"></i></div><div class="job-meta"><span>${bytes(job.downloaded)} / ${bytes(job.size)}</span><span>${pct}%</span><span class="job-target">${esc(job.target || state.status?.target || "")}</span></div>${job.error ? `<p class="error">${esc(job.error)}</p>` : ""}${job.sha256 ? `<details><summary>${esc(t("integrity"))}</summary><code>SHA-256 ${esc(job.sha256)}</code></details>` : ""}</div></article>`;
    }).join("");
    renderSelectionToolbar();
  }
  function selectedJobs() { return state.jobs.filter(job => state.selected.has(job.id)); }
  function renderSelectionToolbar() {
    const selected = selectedJobs();
    $("#selection-toolbar").classList.toggle("hidden", !selected.length);
    $("#selection-count").textContent = t("selected", {count:selected.length});
    $("#select-all").textContent = selected.length === state.jobs.length && state.jobs.length ? t("clearSelection") : t("selectAll");
    $("#pause-selected").disabled = !selected.some(job => ["queued","ready","downloading","verifying"].includes(job.status));
    $("#resume-selected").disabled = !selected.some(job => ["paused","failed","cancelled"].includes(job.status));
    $("#delete-selected").disabled = !selected.some(job => !["queued","ready","downloading","verifying"].includes(job.status));
  }
  async function runSelected(action) {
    const selected = selectedJobs();
    let jobs = selected;
    if (action === "pause") jobs = selected.filter(job => ["queued","ready","downloading","verifying"].includes(job.status));
    if (action === "resume") jobs = selected.filter(job => ["paused","failed","cancelled"].includes(job.status));
    if (action === "delete") jobs = selected.filter(job => !["queued","ready","downloading","verifying"].includes(job.status));
    if (!jobs.length) return;
    if (action === "delete" && !confirm(t("confirmDelete", {count:jobs.length}))) return;
    try {
      if (action === "delete") await api("/api/jobs/delete", {method:"POST",body:JSON.stringify({ids:jobs.map(job => job.id)})});
      else await Promise.all(jobs.map(job => api(`/api/jobs/${job.id}/${action}`, {method:"POST",body:"{}"})));
      jobs.forEach(job => state.selected.delete(job.id));
      await refreshJobs();
    } catch (error) { $("#notice").textContent = error.message; }
  }
  $("#login-form").addEventListener("submit", async (event) => { event.preventDefault(); state.token = $("#access-token").value.trim(); try { await api("/api/status"); localStorage.setItem("nas-download-token", state.token); showApp(); } catch (error) { $("#login-error").textContent = error.message; } });
  $("#download-form").addEventListener("submit", async (event) => { event.preventDefault(); const button = $("#start-button"); const url = $("#download-url").value.trim(); button.disabled = true; $("#notice").textContent = t("inspectLink"); try { const checked = await api("/api/inspect", {method:"POST",body:JSON.stringify({url})}); const started = await api("/api/start", {method:"POST",body:JSON.stringify({...checked.file,target:state.selectedTarget})}); $("#download-url").value = ""; $("#notice").textContent = started.count > 1 ? t("addedMany", {count:started.count,target:state.selectedTarget}) : t("addedOne", {name:checked.file.name,target:state.selectedTarget}); await refreshJobs(); } catch (error) { $("#notice").textContent = error.message; } finally { button.disabled = false; } });
  $("#jobs").addEventListener("change", event => { const checkbox = event.target.closest("input[data-id]"); if (!checkbox) return; checkbox.checked ? state.selected.add(checkbox.dataset.id) : state.selected.delete(checkbox.dataset.id); renderJobs(); });
  $("#select-all").addEventListener("click", () => { if (state.selected.size === state.jobs.length) state.selected.clear(); else state.jobs.forEach(job => state.selected.add(job.id)); renderJobs(); });
  $("#pause-selected").addEventListener("click", () => runSelected("pause"));
  $("#resume-selected").addEventListener("click", () => runSelected("resume"));
  $("#delete-selected").addEventListener("click", () => runSelected("delete"));
  $("#clear-completed").addEventListener("click", async () => { const count = state.jobs.filter(job => job.status === "completed").length; if (!count || !confirm(t("confirmClear", {count}))) return; try { await api("/api/jobs/completed/clear", {method:"POST",body:"{}"}); state.selected.clear(); await refreshJobs(); } catch (error) { $("#notice").textContent = error.message; } });
  $("#same-provider-parallel").addEventListener("change", event => { $("#same-provider-limit").disabled = !event.target.checked; });
  $("#save-concurrency").addEventListener("click", async () => {
    const enabled = $("#same-provider-parallel").checked;
    const limit = Number($("#same-provider-limit").value);
    if (enabled && !confirm(t("confirmParallel", {count:limit}))) return;
    const button = $("#save-concurrency"); button.disabled = true; $("#concurrency-message").textContent = t("saving");
    try {
      await api("/api/settings", {method:"POST",body:JSON.stringify({same_provider_parallel:enabled,same_provider_limit:limit})});
      state.status = await api("/api/status"); renderStatus();
      $("#concurrency-message").textContent = enabled ? t("parallelSaved", {count:limit}) : t("sequentialSaved");
    } catch (error) { $("#concurrency-message").textContent = error.message; }
    finally { button.disabled = false; }
  });
  $("#save-download-mode").addEventListener("click", async () => {
    const mode = $("#download-mode").value;
    if (mode === "single" && !confirm(t("confirmSingleMode"))) return;
    const button = $("#save-download-mode"); button.disabled = true; $("#download-mode-message").textContent = t("saving");
    try {
      const result = await api("/api/settings", {method:"POST",body:JSON.stringify({download_mode:mode})});
      state.status = await api("/api/status"); renderStatus();
      $("#download-mode-message").textContent = t(result.download_mode === "single" ? "singleModeSaved" : "segmentedModeSaved");
    } catch (error) { $("#download-mode-message").textContent = error.message; }
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
  document.querySelectorAll(".nav").forEach(button => button.addEventListener("click", () => { document.querySelectorAll(".nav").forEach(x => x.classList.toggle("active", x === button)); $("#dashboard-view").classList.toggle("hidden", button.dataset.view !== "dashboard"); $("#settings-view").classList.toggle("hidden", button.dataset.view !== "settings"); if (button.dataset.view === "settings") loadPairing(); }));
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
  $("#reveal-code").addEventListener("click", () => { state.codeVisible = !state.codeVisible; renderPairing(); });
  $("#copy-code").addEventListener("click", async () => {
    if (!state.pairing) return;
    try { await navigator.clipboard.writeText(state.pairing.token); $("#pairing-message").textContent = t("copied"); }
    catch (_) {
      const input = document.createElement("textarea"); input.value = state.pairing.token; document.body.appendChild(input); input.select(); document.execCommand("copy"); input.remove();
      $("#pairing-message").textContent = t("copied");
    }
  });
  $("#rotate-code").addEventListener("click", async () => {
    if (!confirm(t("confirmRotate"))) return;
    try {
      const pairing = await api("/api/token/rotate", {method:"POST",body:"{}"});
      state.pairing = pairing; state.token = pairing.token; state.codeVisible = true;
      localStorage.setItem("nas-download-token", state.token); renderPairing();
      $("#pairing-message").textContent = t("rotated");
    } catch (error) { $("#pairing-message").textContent = error.message; }
  });
  window.addEventListener("nasdrop-language-change", () => {
    if (state.status) renderStatus();
    renderJobs();
    renderPairing();
    if (state.folder) loadFolder(state.folder.path);
  });
  if (state.token) showApp();
})();
