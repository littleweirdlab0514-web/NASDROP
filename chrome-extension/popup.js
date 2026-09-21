const $ = selector => document.querySelector(selector);
const messages = {
  en: { connectTitle:'Connect to your NAS', connectHint:'Use the same address and account as the NASDrop web portal.', serverAddress:'NASDrop address', username:'ID', password:'Password', autoExtract:'Automatically extract archives', connect:'Connect', logout:'Sign out', downloadLink:'Download link', useCurrentTab:'Use current tab', send:'Send to NASDrop', recentJobs:'Recent jobs', refresh:'Refresh', destination:'Destination', noDestination:'Not selected in NASDrop', noJobs:'No download jobs yet.', connecting:'Connecting…', inspecting:'Checking the link and adding it…', detected:'{provider} link detected. Ready to send.', added:'Added: {name}', addedMany:'Added {count} files.', currentTabUnavailable:'This tab does not contain a supported download link.', permissionDenied:'Permission to connect to this NASDrop address is required.' },
  ko: { connectTitle:'NAS에 연결', connectHint:'NASDrop 웹 포털과 같은 주소 및 계정을 사용하세요.', serverAddress:'NASDrop 주소', username:'아이디', password:'비밀번호', autoExtract:'압축 파일 자동 해제', connect:'연결', logout:'로그아웃', downloadLink:'다운로드 링크', useCurrentTab:'현재 탭 주소 사용', send:'NASDrop으로 보내기', recentJobs:'최근 작업', refresh:'새로고침', destination:'저장 위치', noDestination:'NASDrop에서 선택되지 않음', noJobs:'아직 다운로드 작업이 없습니다.', connecting:'연결 중…', inspecting:'링크를 확인하고 추가하는 중…', detected:'{provider} 링크를 인식했습니다. 바로 보낼 수 있습니다.', added:'추가됨: {name}', addedMany:'파일 {count}개를 추가했습니다.', currentTabUnavailable:'현재 탭에서 지원되는 다운로드 링크를 찾지 못했습니다.', permissionDenied:'이 NASDrop 주소에 연결할 권한이 필요합니다.' },
  ja: { connectTitle:'NASに接続', connectHint:'NASDropウェブポータルと同じアドレスとアカウントを使用します。', serverAddress:'NASDropアドレス', username:'ID', password:'パスワード', autoExtract:'アーカイブを自動展開', connect:'接続', logout:'ログアウト', downloadLink:'ダウンロードリンク', useCurrentTab:'現在のタブを使用', send:'NASDropへ送信', recentJobs:'最近のジョブ', refresh:'更新', destination:'保存先', noDestination:'NASDropで未選択', noJobs:'ダウンロードジョブはまだありません。', connecting:'接続中…', inspecting:'リンクを確認して追加中…', detected:'{provider}リンクを検出しました。送信できます。', added:'追加済み: {name}', addedMany:'{count}件のファイルを追加しました。', currentTabUnavailable:'現在のタブに対応するダウンロードリンクがありません。', permissionDenied:'このNASDropアドレスへの接続権限が必要です。' },
  zh: { connectTitle:'连接到 NAS', connectHint:'使用与 NASDrop 网页门户相同的地址和账户。', serverAddress:'NASDrop 地址', username:'ID', password:'密码', autoExtract:'自动解压缩文件', connect:'连接', logout:'退出', downloadLink:'下载链接', useCurrentTab:'使用当前标签页', send:'发送到 NASDrop', recentJobs:'最近任务', refresh:'刷新', destination:'保存位置', noDestination:'尚未在 NASDrop 中选择', noJobs:'还没有下载任务。', connecting:'正在连接…', inspecting:'正在检查链接并添加…', detected:'已识别 {provider} 链接，可以发送。', added:'已添加：{name}', addedMany:'已添加 {count} 个文件。', currentTabUnavailable:'当前标签页没有受支持的下载链接。', permissionDenied:'需要连接此 NASDrop 地址的权限。' },
};
messages.ko.autoExtract = '자동 압축 풀기';
let language = NASDropI18n.normalize(navigator.language);
Object.assign(messages.en, {clearCompleted:'Clear completed',archivePassword:'Archive password (optional)',close:'Close',saveOptions:'Save options',clearConfirm:'Remove completed jobs from the list? Files on the NAS will be kept.',cleared:'Completed jobs removed. NAS files were kept.',saved:'Options saved.',passwordAlert:'{count} job(s) need an archive password. Select a job below.',live:'Auto refresh · {time}',retry:'Connection interrupted · retrying with a longer interval',locked:'Options cannot be changed during processing or after completion.',upgrade:'Changing extraction options requires a newer NASDrop server. Password-waiting jobs can still accept a password.',optionHint:'Leave password empty to keep the existing password. Paused jobs remain paused.',passwordNeeded:'Enter the archive password to continue.'});
Object.assign(messages.ko, {clearCompleted:'완료된 작업 삭제',archivePassword:'압축 비밀번호 (선택)',close:'닫기',saveOptions:'설정 저장',clearConfirm:'완료된 작업을 목록에서 삭제할까요? NAS에 저장된 파일은 유지됩니다.',cleared:'완료된 작업 기록을 삭제했습니다. NAS 파일은 유지됩니다.',saved:'설정을 저장했습니다.',passwordAlert:'작업 {count}개에 압축 비밀번호가 필요합니다. 아래 작업을 눌러 입력하세요.',live:'자동 갱신 · {time}',retry:'연결 지연 · 간격을 늘려 다시 확인합니다',locked:'후처리 중이거나 종료된 작업은 설정을 변경할 수 없습니다.',upgrade:'압축 해제 설정 변경은 새 NASDrop 서버가 필요합니다. 비밀번호 대기 작업의 암호 입력은 가능합니다.',optionHint:'비밀번호를 비우면 기존 암호를 유지합니다. 일시정지한 작업은 자동 재개하지 않습니다.',passwordNeeded:'계속하려면 압축 비밀번호를 입력하세요.'});
Object.assign(messages.ja, {clearCompleted:'完了履歴を削除',archivePassword:'アーカイブのパスワード（任意）',close:'閉じる',saveOptions:'設定を保存',clearConfirm:'完了した履歴を削除しますか？NASのファイルは保持されます。',cleared:'完了履歴を削除しました。ファイルは保持されます。',saved:'設定を保存しました。',passwordAlert:'{count}件にパスワードが必要です。ジョブを選択してください。',live:'自動更新 · {time}',retry:'接続できません。間隔を延ばして再試行します。',locked:'処理中または完了後は変更できません。',upgrade:'展開設定の変更には新しいNASDropサーバーが必要です。',optionHint:'空欄なら既存のパスワードを保持します。一時停止は自動再開しません。',passwordNeeded:'アーカイブのパスワードを入力してください。'});
Object.assign(messages.zh, {clearCompleted:'清除已完成任务',archivePassword:'压缩密码（可选）',close:'关闭',saveOptions:'保存设置',clearConfirm:'清除已完成任务记录？NAS 文件将保留。',cleared:'已清除完成记录，NAS 文件已保留。',saved:'设置已保存。',passwordAlert:'{count} 个任务需要密码，请点击任务输入。',live:'自动刷新 · {time}',retry:'连接中断，正在延长间隔重试',locked:'处理期间或结束后不能更改设置。',upgrade:'更改解压设置需要新版 NASDrop 服务。',optionHint:'留空以保留现有密码。暂停任务不会自动恢复。',passwordNeeded:'请输入压缩密码以继续。'});
Object.assign(messages.en,{pauseJob:'Pause',resumeJob:'Resume',deleteJob:'Delete',deleteRecord:'Delete record',deleteHint:'Pause first to delete unfinished files. Completed files are kept.',stoppingHint:'Stopping… Delete becomes available after the worker exits.',deletePartialConfirm:'Delete this unfinished job and all its temporary download files? This cannot be undone. Completed output files are kept.',deleteRecordConfirm:'Remove this completed job record? The downloaded files will be kept.',jobActionDone:'Request accepted.',jobDeleted:'Job deleted.'});
Object.assign(messages.ko,{pauseJob:'멈추기',resumeJob:'다시 시작',deleteJob:'삭제',deleteRecord:'기록 삭제',deleteHint:'미완료 작업은 멈춘 뒤 삭제하면 받던 임시 파일도 삭제됩니다. 완료 파일은 유지됩니다.',stoppingHint:'중지 중… 작업이 완전히 멈추면 삭제할 수 있습니다.',deletePartialConfirm:'이 미완료 작업과 받던 임시 파일을 삭제할까요? 되돌릴 수 없습니다. 이미 완료된 출력 파일은 유지됩니다.',deleteRecordConfirm:'완료된 작업의 기록을 삭제할까요? NAS에 저장된 파일은 유지됩니다.',jobActionDone:'요청을 접수했습니다.',jobDeleted:'작업을 삭제했습니다.'});
Object.assign(messages.ja,{pauseJob:'停止',resumeJob:'再開',deleteJob:'削除',deleteRecord:'履歴削除',deleteHint:'停止後に削除すると一時ファイルも削除されます。完了ファイルは保持されます。',stoppingHint:'停止処理中です。終了後に削除できます。',deletePartialConfirm:'未完了のジョブと一時ファイルを削除しますか？元に戻せません。完了ファイルは保持されます。',deleteRecordConfirm:'履歴を削除しますか？NASのファイルは保持されます。',jobActionDone:'リクエストを受け付けました。',jobDeleted:'ジョブを削除しました。'});
Object.assign(messages.zh,{pauseJob:'暂停',resumeJob:'继续',deleteJob:'删除',deleteRecord:'删除记录',deleteHint:'暂停后删除会清除临时文件。已完成的文件将保留。',stoppingHint:'正在停止，结束后可以删除。',deletePartialConfirm:'删除此未完成任务及临时文件？无法撤销，已完成文件将保留。',deleteRecordConfirm:'删除记录？NAS 文件将保留。',jobActionDone:'请求已接受。',jobDeleted:'任务已删除。'});
let uiState = {connected:false,jobs:[]}, selectedJob = '', optionsDirty = false, mutationBusy = false, loginBusy = false;
const pausableStates=new Set(['inspecting','queued','ready','downloading','waiting_processing','verifying']);
const resumableStates=new Set(['paused','failed','cancelled']);
const deletableStates=new Set(['paused','failed','cancelled','password_required','completed']);
const editableStates = new Set(['queued','ready','inspecting','paused','downloading','password_required']);
const popupPort = chrome.runtime.connect({name:'nasdrop-popup'});
const polling = NASDropPolling.create({
  load:() => send({type:'getJobs'}), visible:() => !document.hidden,
  onData:result => { uiState.jobs = result.jobs; renderJobs(result.jobs); syncJobDetail(); $('#poll-status').textContent = t('live',{time:new Date().toLocaleTimeString(language)}); },
  onError:error => {
    $('#poll-status').textContent = t('retry');
    if (error.status === 401) { render({...uiState,connected:false,token:''}); notice(error.message); }
  },
});
const t = (key, vars = {}) => Object.entries(vars).reduce((text, [name, value]) => text.replace(`{${name}}`, value), messages[language][key] || messages.en[key] || key);

function localize() {
  document.documentElement.lang = language;
  $('#language-label').textContent=NASDropI18n.t(language,'language');
  $('#language-auto').textContent=NASDropI18n.t(language,'autoLanguage');
  $('#destination-label').textContent=`${t('destination')}: ${uiState.status?.target || t('noDestination')}`;
  document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
  const automatic = {
    en:['Site buttons connected', 'Click Download on a supported site. Buzzheavier also supports Copy download link. Reload open pages after installing.', 'Send a link manually'],
    ko:['사이트 버튼 연결됨', '지원 사이트의 다운로드 버튼을 누르면 NASDrop으로 보냅니다. Buzzheavier는 Copy download link도 지원합니다. 설치 후 열린 페이지를 새로고침하세요.', '링크 직접 입력'],
    ja:['サイトのボタンを接続', '対応サイトのダウンロードボタンでNASDropへ送信します。BuzzheavierはCopy download linkにも対応。インストール後はページを再読み込みしてください。', 'リンクを手動入力'],
    zh:['网站按钮已连接', '点击支持网站的下载按钮即可发送到 NASDrop。Buzzheavier 也支持 Copy download link。安装后请刷新已打开的页面。', '手动输入链接'],
  }[language];
  ['automatic-title','automatic-hint','manual-title'].forEach((id,index) => { document.getElementById(id).textContent = automatic[index]; });
}
function notice(text = '', success = false) { $('#notice').textContent = text ? NASDropI18n.error(language,text) : ''; $('#notice').classList.toggle('success', success); }
function send(message) { return chrome.runtime.sendMessage(message).then(response => { if (!response?.ok) { const error = new Error(NASDropI18n.error(language,response?.error)); error.status=response?.status; throw error; } return response.result; }); }
function permissionPattern(rawUrl) { let url; try {url=new URL(rawUrl);} catch {throw new Error(NASDropI18n.t(language,'invalidAddress'));} if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error(NASDropI18n.t(language,'invalidAddress')); return `${url.protocol}//${url.hostname}/*`; }
function percent(job) { return job.size > 0 ? Math.min(100, Math.round((job.downloaded || 0) * 100 / job.size)) : 0; }
function supportedProvider(rawUrl) {
  try {
    const url = new URL(rawUrl);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== 'https:') return '';
    if (/^[a-z0-9-]+\.gigafile\.nu$/.test(host) && /^\/[A-Za-z0-9_-]+\/?$/.test(url.pathname)) return 'GigaFile';
    if (['gofile.io', 'www.gofile.io'].includes(host) && url.pathname.startsWith('/d/')) return 'GoFile';
    if (['pixeldrain.com', 'www.pixeldrain.com', 'pixeldrain.net', 'pixeldra.in'].includes(host) && url.pathname.startsWith('/u/')) return 'Pixeldrain';
    if (/^[a-z0-9-]+\.buzzheavier\.com$/.test(host) && url.pathname.startsWith('/d/') && url.searchParams.has('v')) return 'Buzzheavier';
  } catch (_) {}
  return '';
}

async function useCurrentTab(showError = true) {
  const [tab] = await chrome.tabs.query({ active:true, currentWindow:true });
  const provider = supportedProvider(tab?.url || '');
  if (!provider) { if (showError) notice(t('currentTabUnavailable')); return false; }
  $('#download-url').value = tab.url;
  notice(t('detected', { provider }), true);
  return true;
}

function renderJobs(jobs) {
  const list = $('#jobs');
  $('#clear-completed').disabled = mutationBusy || !jobs?.some(job=>job.status === 'completed');
  const waiting = jobs?.filter(job=>job.status === 'password_required').length || 0;
  $('#password-alert').classList.toggle('hidden',!waiting);
  $('#password-alert').textContent = waiting ? t('passwordAlert',{count:waiting}) : '';
  list.replaceChildren();
  if (!jobs?.length) { const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = t('noJobs'); list.append(empty); return; }
  jobs.forEach(job => {
    const item = document.createElement('button'); item.type='button'; item.className = `job${selectedJob === job.id ? ' selected' : ''}${job.status === 'password_required' ? ' password-required' : ''}`;
    item.addEventListener('click',()=>openJob(job.id));
    const line = document.createElement('div'); line.className = 'job-line';
    const name = document.createElement('strong'); name.textContent = job.name;
    const status = document.createElement('span'); status.textContent = `${NASDropI18n.t(language,job.status==='failed'?'failedStatus':job.status)} · ${percent(job)}%`;
    const bar = document.createElement('div'); bar.className = 'bar';
    const fill = document.createElement('i'); fill.style.width = `${percent(job)}%`;
    const meta = document.createElement('div'); meta.className='job-meta'; meta.textContent=`${formatBytes(job.downloaded)} / ${formatBytes(job.size)}`;
    line.append(name, status); bar.append(fill); item.append(line, bar, meta); list.append(item);
  });
}

function formatBytes(value) {
  if (!Number.isFinite(value) || value <= 0) return '0 B';
  const unit = Math.min(4,Math.floor(Math.log(value)/Math.log(1024)));
  return `${(value/1024**unit).toFixed(unit ? 1 : 0)} ${['B','KB','MB','GB','TB'][unit]}`;
}
function openJob(id) {
  if (selectedJob !== id) { selectedJob=id; optionsDirty=false; $('#job-password').value=''; }
  $('#job-detail').classList.remove('hidden'); syncJobDetail();
}
function closeJob() { selectedJob=''; optionsDirty=false; $('#job-password').value=''; $('#job-detail').classList.add('hidden'); }
function syncJobDetail() {
  const job=uiState.jobs.find(job=>job.id===selectedJob);
  if (!job) { closeJob(); return; }
  $('#job-detail-name').textContent=job.name;
  $('#pause-job').disabled=mutationBusy || !pausableStates.has(job.status);
  $('#resume-job').disabled=mutationBusy || !resumableStates.has(job.status);
  $('#delete-job').disabled=mutationBusy || !deletableStates.has(job.status);
  $('#delete-job').textContent=t(job.status==='completed'?'deleteRecord':'deleteJob');
  $('#job-delete-hint').textContent=t(job.status==='stopping'?'stoppingHint':'deleteHint');
  if (!optionsDirty) $('#job-extract').checked=Boolean(job.extract);
  const modern=Boolean(uiState.status?.job_processing_options), editable=editableStates.has(job.status);
  $('#job-extract').disabled=mutationBusy || !modern || !editable;
  $('#job-password').disabled=mutationBusy || !$('#job-extract').checked || !(modern && editable || job.status==='password_required');
  $('#save-job-options').disabled=mutationBusy || !(modern && editable || job.status==='password_required');
  $('#job-options-hint').textContent=!modern ? t('upgrade') : !editable ? t('locked') : job.status==='password_required' ? t('passwordNeeded') : t('optionHint');
}

function render(state) {
  uiState=state;
  language=NASDropI18n.resolve(state.language,navigator.language);
  $('#language-select').value=state.language||'auto';
  localize();
  const connected = Boolean(state.connected);
  $('#login-view').classList.toggle('hidden', connected);
  $('#app-view').classList.toggle('hidden', !connected);
  $('#logout-button').classList.toggle('hidden', !connected);
  $('#base-url').value = state.baseUrl || $('#base-url').value;
  $('#username').value = state.username || $('#username').value;
  $('#auto-extract').checked = state.autoExtract !== false;
  $('#archive-password').disabled = state.autoExtract === false;
  $('#connection-label').textContent = connected ? state.baseUrl : 'Chrome';
  if (connected) {
    $('#destination-label').textContent = `${t('destination')}: ${state.status?.target || t('noDestination')}`;
    renderJobs(state.jobs);
    syncJobDetail();
    polling.start(false);
  } else { polling.stop(); closeJob(); if (state.error) notice(state.error); }
}

async function refresh() { render(await send({ type: 'getState' })); }

$('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); if (loginBusy) return; loginBusy=true;
  const button=$('#login-button'); button.disabled=true; notice(t('connecting'));
  const baseUrl = $('#base-url').value.trim();
  try {
    const origin=permissionPattern(baseUrl);
    const granted=await chrome.permissions.request({origins:[origin]});
    if (!granted) throw new Error(t('permissionDenied'));
    const state = await send({ type:'login', baseUrl, username:$('#username').value, password:$('#password').value });
    $('#password').value = ''; notice(''); render(state);
  } catch (error) { notice(error.message); } finally { button.disabled = false; loginBusy=false; }
});
$('#password').addEventListener('keydown',event=>{
  if (event.key==='Enter' && !event.isComposing) { event.preventDefault(); if (!loginBusy) $('#login-form').requestSubmit($('#login-button')); }
});

$('#send-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('#send-button'); button.disabled = true; notice(t('inspecting'));
  try {
    await preferenceSave;
    const result = await send({ type:'submit', url:$('#download-url').value.trim(), password:$('#auto-extract').checked ? $('#archive-password').value : '' });
    $('#download-url').value = '';
    $('#archive-password').value = '';
    notice(result.count > 1 ? t('addedMany', { count:result.count }) : t('added', { name:result.file.name }), true);
    await refresh();
  } catch (error) { notice(error.message); } finally { button.disabled = false; }
});

$('#use-tab-button').addEventListener('click', () => useCurrentTab(true));
$('#refresh-button').addEventListener('click', async () => { const button=$('#refresh-button'); button.disabled=true; try { await polling.refresh(); } finally { button.disabled=false; } });
$('#logout-button').addEventListener('click', async () => { polling.stop(); await polling.refresh(); await send({type:'logout'}); render({...uiState,connected:false,token:'',jobs:[]}); notice(''); });
let preferenceSave = Promise.resolve();
$('#auto-extract').addEventListener('change', event => {
  const toggle=event.target, value=toggle.checked, previous=uiState.autoExtract !== false;
  toggle.disabled=true;
  preferenceSave=send({type:'savePreferences',autoExtract:value}).then(()=>{
    uiState.autoExtract=value;
    $('#archive-password').disabled=!value;
    if (!value) $('#archive-password').value='';
  }).catch(error=>{toggle.checked=previous;notice(error.message);}).finally(()=>{toggle.disabled=false;});
  return preferenceSave;
});
$('#close-detail').addEventListener('click',closeJob);
$('#language-select').addEventListener('change',async event=>{
  const select=event.target,previous=uiState.language||'auto';select.disabled=true;
  try {
    await send({type:'savePreferences',language:select.value});
    uiState.language=select.value;language=NASDropI18n.resolve(select.value,navigator.language);
    localize();renderJobs(uiState.jobs);syncJobDetail();notice('');$('#poll-status').textContent='';
  } catch(error) {select.value=previous;notice(error.message);}
  finally {select.disabled=false;}
});
async function runJobAction(type, buttonId) {
  if (mutationBusy || $(buttonId).disabled) return;
  const job=uiState.jobs.find(job=>job.id===selectedJob);
  if (!job) return;
  if (type==='jobDelete' && !confirm(t(job.status==='completed'?'deleteRecordConfirm':'deletePartialConfirm'))) return;
  mutationBusy=true; polling.stop(); syncJobDetail();
  try {
    await polling.refresh();
    await send({type,id:job.id});
    if (type==='jobDelete') { uiState.jobs=uiState.jobs.filter(item=>item.id!==job.id); if (selectedJob===job.id) closeJob(); }
    else job.status=type==='jobPause'?'stopping':'queued';
    renderJobs(uiState.jobs); notice(t(type==='jobDelete'?'jobDeleted':'jobActionDone'),true);
  } catch(error) { notice(error.message); }
  finally {mutationBusy=false; syncJobDetail(); await polling.start();}
}
$('#pause-job').addEventListener('click',()=>runJobAction('jobPause','#pause-job'));
$('#resume-job').addEventListener('click',()=>runJobAction('jobResume','#resume-job'));
$('#delete-job').addEventListener('click',()=>runJobAction('jobDelete','#delete-job'));
$('#job-extract').addEventListener('change',()=>{ optionsDirty=true; if (!$('#job-extract').checked) $('#job-password').value=''; syncJobDetail(); });
$('#job-password').addEventListener('input',()=>{optionsDirty=true;});
$('#clear-completed').addEventListener('click',async()=>{
  if (mutationBusy || !confirm(t('clearConfirm'))) return;
  mutationBusy=true; polling.stop(); renderJobs(uiState.jobs);
  try { await polling.refresh(); await send({type:'clearCompleted'}); notice(t('cleared'),true); }
  catch (error) { notice(error.message); }
  finally { mutationBusy=false; await polling.start(); }
});
$('#job-options-form').addEventListener('submit',async event=>{
  event.preventDefault(); if (mutationBusy || $('#save-job-options').disabled) return;
  mutationBusy=true; polling.stop(); syncJobDetail();
  try {
    await polling.refresh();
    await send({type:uiState.status?.job_processing_options ? 'jobProcessing' : 'jobPassword',id:selectedJob,extract:$('#job-extract').checked,password:$('#job-password').value});
    $('#job-password').value=''; optionsDirty=false; notice(t('saved'),true);
  } catch(error) { notice(error.message); }
  finally {mutationBusy=false; await polling.start(); syncJobDetail();}
});
document.addEventListener('visibilitychange',()=>polling.visibilityChanged());
window.addEventListener('pagehide',()=>{polling.stop(); popupPort.disconnect(); $('#job-password').value=''; $('#archive-password').value='';});

localize();
refresh().then(() => useCurrentTab(false)).catch(error => notice(error.message));
