import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

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
