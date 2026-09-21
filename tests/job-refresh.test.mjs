import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

test('GigaFile form queues immediately without synchronous inspection', async () => {
  const source = await readFile(new URL('../synology/web/app.js', import.meta.url), 'utf8');
  const line = source.split('\n').find(line => line.includes('$("#download-form").addEventListener'));
  let submit;
  const nodes = {
    '#download-form': {addEventListener(_event, fn){submit=fn;}},
    '#start-button': {}, '#download-url': {value:'https://123.gigafile.nu/1231-abcdef'},
    '#extract-download': {checked:true}, '#archive-password': {value:'synthetic'}, '#notice': {}
  };
  const requests=[];
  vm.runInNewContext(line, {$:key=>nodes[key], URL, t:key=>key,
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
