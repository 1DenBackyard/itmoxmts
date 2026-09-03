const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context={};vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/js/core.js'),'utf8'),context);
const U=context.SpecUI;
test('document rendering escapes HTML including quote marks',()=>{
  const text='<img src=x onerror="alert(1)">';
  const html=U.documentHtml(text,text);
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
  assert.ok(html.includes('id="active-quote"'));
});
test('tables and source lines remain readable without generating findings',()=>{
  const html=U.documentHtml('Общие сведения\nОписание\nA | B\n1 | 2\nКонец');
  assert.ok(html.includes('<table'));
  assert.ok(html.includes('Конец'));
  assert.ok(html.includes('Описание'));
});
test('only accepted and fixed issues count as confirmed',()=>{
  const issues=['open','accepted','rejected','fixed'].map((d,n)=>({title:'key',category:'contract',problem:'p',employee_decision:d,severity:n===0?'blocker':'major'}));
  assert.equal(U.stats(issues).confirmed,2);
  assert.equal(U.stats(issues).fixed,1);
  assert.equal(U.filter(issues,'open').length,1);
  assert.equal(U.filter(issues,'closed').length,3);
});
test('production HTML never loads demo evaluation or demo datasets',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  assert.ok(!html.includes('analyzer.js'));
  assert.ok(!html.includes('autofix.js'));
  const app=fs.readFileSync(path.join(__dirname,'../web/js/app.js'),'utf8');
  assert.ok(!app.includes('dataset.json'));
  assert.ok(app.includes("api('/reviews'"));
});
