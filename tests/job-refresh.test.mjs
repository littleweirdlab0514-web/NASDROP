import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

test('1fichier wait message counts down locally without provider requests', async () => {
  const source = await readFile(new URL('../synology/web/app.js', import.meta.url), 'utf8');
  const functions = source.slice(source.indexOf('  function oneFichierWaitUntil('), source.indexOf('  function esc('));
  let now = 1_000_000;
  const nodes = [
    {dataset:{onefichierWaitUntil:'1065'},textContent:''},
  ];
  const context = vm.createContext({
    URL,
    Date:{now:()=>now},
    document:{querySelectorAll:selector=>selector==='[data-onefichier-wait-until]'?nodes:[]},
    t:(key, vars={}) => key === 'oneFichierWaitCountdown'
      ? `${vars.minutes}:${vars.seconds}`
      : key,
  });
  vm.runInContext(functions, context);
  const job = {status:'queued',not_before:1065,source:'https://1fichier.com/?example'};
  assert.equal(context.oneFichierWaitUntil(job),1065);
  assert.equal(context.oneFichierWaitUntil({...job,source:'https://1fichier.com.evil.example/?example'}),0);
  context.updateWaitCountdowns();
  assert.equal(nodes[0].textContent,'1:05');
  now = 1_064_200;
  context.updateWaitCountdowns();
  assert.equal(nodes[0].textContent,'0:01');
  now = 1_066_000;
  context.updateWaitCountdowns();
  assert.equal(nodes[0].textContent,'oneFichierRetrying');
});

test('GigaFile form queues immediately without synchronous inspection', async () => {
  const source = await readFile(new URL('../synology/web/app.js', import.meta.url), 'utf8');
  const handler = source.slice(source.indexOf('  $("#download-form").addEventListener'),
    source.indexOf('  $("#extract-download").addEventListener'));
  let submit;
  const nodes = {
    '#download-form': {addEventListener(_event, fn){submit=fn;}},
    '#start-button': {}, '#download-url': {value:'https://123.gigafile.nu/1231-abcdef'},
    '#extract-download': {checked:true}, '#archive-password': {value:'synthetic'}, '#notice': {},
    '#gigafile-download-key': {value:''}, '#onefichier-password': {value:''},
    '#onefichier-password-wrap': {classList:{add(){}}}
  };
  const requests=[];
  vm.runInNewContext(handler, {$:key=>nodes[key], URL, t:key=>key,
    state:{selectedTarget:'/downloads'}, refreshJobs:async()=>{},
    api:async(path,options)=>{requests.push([path,JSON.parse(options.body)]);return {count:1};}});
  await submit({preventDefault(){}});
  assert.deepEqual(requests.map(r=>r[0]),['/api/enqueue']);
  assert.equal(requests[0][1].extract,true);
  assert.equal(requests[0][1].password,'synthetic');
  assert.equal(nodes['#archive-password'].value,'');
  assert.equal(nodes['#start-button'].disabled,false);
});

test('polling keeps password form identity, caret and open verification details', async () => {
  const source = await readFile(new URL('../synology/web/app.js', import.meta.url), 'utf8');
  const fn = source.slice(source.indexOf('  function replaceJobList('), source.indexOf('  function renderJobs('));
  let focused = false, selection;
  const input = {value:'not-persisted', selectionStart:2, selectionEnd:5,
    focus(){focused=true;}, setSelectionRange(...args){selection=args;}};
  const form = {dataset:{id:'one'}, contains:node=>node===input};
  const detail = {open:true, closest:()=>({dataset:{jobId:'one'}})};
  let current = form, currentDetail=detail;
  const container = {
    set innerHTML(markup){
      current = markup ? {dataset:{id:'one'}, replaceWith(node){current=node;}} : null;
      currentDetail = {open:false, closest:detail.closest};
    },
    querySelectorAll(selector){
      if(selector==='.job-password')return current?[current]:[];
      if(selector.endsWith('[open]'))return currentDetail.open?[currentDetail]:[];
      return [currentDetail];
    },
    contains:node=>current===form && node===input,
  };
  const context = vm.createContext({document:{activeElement:input}});
  vm.runInContext(fn, context);
  context.replaceJobList(container, 'new markup');
  assert.equal(current,form);
  assert.equal(input.value,'not-persisted');
  assert.equal(currentDetail.open,true);
  assert.equal(focused,true);
  assert.deepEqual(selection,[2,5]);
  focused=false;
  context.replaceJobList(container,'');
  assert.equal(current,null);
  assert.equal(focused,false);
});

test('stopping jobs cannot be resumed or deleted by the selection toolbar', async () => {
  const source = await readFile(new URL('../synology/web/app.js', import.meta.url), 'utf8');
  assert.match(source,/stopping:"statusStopping"/);
  assert.match(source,/#resume-selected"\)\.disabled = !selected\.some\(job => \["paused","failed","cancelled"\]/);
  assert.match(source,/#delete-selected"\)\.disabled = .*"stopping"/);
  assert.match(source,/error\.status === 401/);
});

test('bootstrap login forces the web account form and hides every other operation', async () => {
  const source = await readFile(new URL('../synology/web/app.js', import.meta.url), 'utf8');
  const fn = source.slice(source.indexOf('  function renderPasswordChangeGate('), source.indexOf('  function renderStatus('));
  const classes = (...initial) => {
    const values = new Set(initial);
    return {
      add:value=>values.add(value), remove:value=>values.delete(value),
      toggle(value, force){ force ? values.add(value) : values.delete(value); },
      contains:value=>values.has(value), values,
    };
  };
  const warning={classList:classes('hidden')}, dashboard={classList:classes()}, settings={classList:classes('hidden')};
  const dashboardNav={classList:classes('active'),disabled:false};
  const settingsNav={classList:classes(),disabled:false};
  const accountCard={classList:classes('account-card')}, otherCard={classList:classes()};
  let focused=false;
  const nodes={
    '#password-change-required-warning':warning, '#dashboard-view':dashboard,
    '#settings-view':settings, '#account-message':{}, '#current-password':{focus(){focused=true;}},
  };
  const state={passwordChangeRequired:true,account:{password_change_required:true}};
  const document={
    querySelector(selector){
      if(selector==='.nav[data-view="dashboard"]')return dashboardNav;
      if(selector==='.nav[data-view="settings"]')return settingsNav;
      return nodes[selector];
    },
    querySelectorAll(selector){return selector==='.setting-card'?[accountCard,otherCard]:[];},
  };
  const context=vm.createContext({state,document,$:selector=>nodes[selector],t:key=>key});
  vm.runInContext(fn,context);
  context.renderPasswordChangeGate();
  assert.equal(warning.classList.contains('hidden'),false);
  assert.equal(accountCard.classList.contains('hidden'),false);
  assert.equal(otherCard.classList.contains('hidden'),true);
  assert.equal(dashboardNav.disabled,true);
  assert.equal(dashboard.classList.contains('hidden'),true);
  assert.equal(settings.classList.contains('hidden'),false);
  assert.equal(focused,true);

  state.passwordChangeRequired=false; state.account.password_change_required=false;
  context.renderPasswordChangeGate();
  assert.equal(warning.classList.contains('hidden'),true);
  assert.equal(otherCard.classList.contains('hidden'),false);
  assert.equal(dashboardNav.disabled,false);
});
