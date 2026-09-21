import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';
const root=new URL('../chrome-extension/',import.meta.url),c=vm.createContext({});
vm.runInContext(await readFile(new URL('i18n.js',root),'utf8'),c);
const i18n=c.NASDropI18n;
test('unknown, empty and unsupported languages default to English',()=>{
  for(const value of [undefined,null,'','fr-FR','xx','auto'])assert.equal(i18n.normalize(value),'en');
  for(const [value,expected] of [['en-US','en'],['ko-KR','ko'],['zh-CN','zh'],['zh-TW','zh'],['ja-JP','ja']])assert.equal(i18n.normalize(value),expected);
  assert.equal(i18n.resolve('auto','fr'),'en');assert.equal(i18n.resolve('ja','ko'),'ja');
});
test('all common messages and placeholders exist in every language',()=>{
  const base=i18n.dictionaries.en;
  for(const lang of i18n.locales)for(const key of Object.keys(base)){
    assert.ok(i18n.dictionaries[lang][key]);
    assert.deepEqual(i18n.dictionaries[lang][key].match(/\{\w+\}/g),base[key].match(/\{\w+\}/g));
  }
  assert.equal(i18n.error('ko','Synthetic remote error'),'Synthetic remote error');
  assert.equal(i18n.error('ja','NASDrop request failed (403).'),i18n.t('ja','httpError',{status:403}));
});
test('Chrome metadata ships all four locales with English fallback',async()=>{
  const manifest=JSON.parse(await readFile(new URL('manifest.json',root),'utf8'));
  assert.equal(manifest.default_locale,'en');
  for(const lang of ['en','ko','zh_CN','ja'])assert.ok(JSON.parse(await readFile(new URL(`_locales/${lang}/messages.json`,root),'utf8')).extensionDescription.message);
});
