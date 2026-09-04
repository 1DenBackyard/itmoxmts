const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context={};vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/js/core.js'),'utf8'),context);
const U=context.SpecUI;
test('severity filters combine with status and search, without renumbering',()=>{
  const issues=['blocker','major','minor','suggestion'].flatMap((severity,n)=>
    ['open','fixed'].map((employee_decision,j)=>({id:`${n}-${j}`,severity,employee_decision,title:'storage'})));
  assert.equal(U.filter(issues,'open','','blocker').length,1);
  assert.equal(U.filter(issues,'all','','major').length,2);
  assert.equal(U.filter(issues,'closed','storage','major')[0].id,'1-1');
  assert.equal(U.filter(issues,'open','Блокирующее','all').length,1);
  assert.equal(U.filter(issues,'open','absent','major').length,0);
  assert.equal(issues[2].id,'1-0');
});
test('applying a fix is explicit, literal, bounded and snapshot-safe',()=>{
  const p={mode:'replace',before:'old',needs_input:false};
  assert.equal(U.applyProposal('old text','old text',p,'new $&'),'new $& text');
  assert.throws(()=>U.applyProposal('changed','old text',p,'new'));
  assert.throws(()=>U.applyProposal('old old','old old',p,'new'));
  assert.throws(()=>U.applyProposal('old','old',{...p,needs_input:true},'new'));
  assert.throws(()=>U.applyProposal('old','old',p,'too long',3));
  assert.equal(U.applyProposal('text','text',{mode:'append',needs_input:false},'Added'),'text\n\nAdded');
});
const issue=(id,evidence)=>({id,evidence,severity:'major',employee_decision:'open'});
test('stable issue numbers annotate overlapping quotes without losing tables',()=>{
  const text='Шаг 1. Фильтрация\nПоле | Тип\nid | string\nКонец';
  const issues=[issue('a','id | string'),issue('b','string'),issue('c','нет такой цитаты')];
  const html=U.documentHtml(text,'',issues,'b');
  assert.ok(html.includes('<table'));
  assert.ok(html.includes('data-annotation="a"'));
  assert.ok(html.includes('data-annotation="b"'));
  assert.ok(!html.includes('data-annotation="c"'));
  assert.ok(html.includes('[1]')&&html.includes('[2]'));
  assert.equal((html.match(/id="anchor-b"/g)||[]).length,1);
  assert.ok(html.includes('issue-highlight selected'));
});
test('multiline quotes, duplicate quotes and hostile IDs remain safe',()=>{
  const text='первая строка\nвторая строка\nпервая строка';
  const issues=[issue('x" onclick="bad','первая строка\nвторая строка'),issue('b','первая строка')];
  const html=U.documentHtml(text,'',issues);
  assert.ok(html.includes('первая строка'));
  assert.ok(!html.includes(' onclick="bad'));
  assert.equal(U.anchors(text,issues)[1].repeated,true);
  assert.equal((html.match(/id="anchor-b"/g)||[]).length,1);
  assert.equal(U.anchors(text,[issue('c','несуществующая')]).length,0);
});
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
