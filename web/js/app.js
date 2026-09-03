/* HTML prototype UI backed exclusively by the production API. */
(() => {
  const U=window.SpecUI, E=U.escape, app=document.getElementById('app');
  const state={user:null,meta:null,page:'login',review:null,history:null,metrics:null,
    text:'',filename:'Техническое задание.txt',uploadId:null,docType:'flow',
    filter:'open',query:'',edit:false,editText:'',quote:'',job:null,timer:null,checklist:new Set(),busy:false};
  const types={flow:['Поток данных','Источники, Kafka, обработка и структура потока.'],
    source:['Система-источник','Описание источников и контрактов данных.'],
    mart:['Витрина-агрегат','Маппинг полей, формулы и регламент обновления.']};
  let noticeTimer;
  function notice(message) {
    const box=document.getElementById('notice'); box.textContent=message; box.hidden=false;
    clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>{box.hidden=true;},6500);
  }
  async function api(path, {method='GET',body}={}) {
    const headers={'X-SpecGuard-Request':'1'};
    if(state.user) headers['X-CSRF-Token']=state.user.csrf;
    if(body && !(body instanceof Blob)) {headers['Content-Type']='application/json';body=JSON.stringify(body);}
    const response=await fetch('/api'+path,{method,body,headers,credentials:'same-origin'});
    const data=await response.json();
    if(!response.ok) {
      if(response.status===401 && path!=='/login') {reset();render();}
      throw new Error(typeof data.detail==='string'?data.detail:'Не удалось выполнить запрос');
    }
    return data;
  }
  function reset() {
    clearTimeout(state.timer);
    Object.assign(state,{user:null,page:'login',review:null,history:null,metrics:null,
      text:'',uploadId:null,job:null,edit:false,busy:false,quote:'',checklist:new Set()});
  }
  function topbar(step=0) {
    return `<div class="topbar"><div class="brand">
      <button class="brand-mark" data-nav="start" aria-label="Новая проверка"><img src="/assets/mts_logo.png" alt="МТС"></button>
      <div><h1>Прожарка документации</h1><p>МТС · ревью ТЗ объектов данных</p></div></div>
      ${state.user?`<div class="topbar-right"><button class="btn btn-ghost btn-sm" data-nav="history">История</button>
      <button class="btn btn-ghost btn-sm" data-nav="progress">Мой прогресс</button>
      <button class="btn btn-ghost btn-sm" data-nav="system">Как это работает</button>
      <button class="btn btn-secondary btn-sm" id="logout" title="${E(state.user.email)}">${E(state.user.name)} · Выйти</button>
      <div class="steps">${['Документ','Ревью','Итог'].map((s,i)=>`<span class="step-pill ${step===i+1?'active':step>i+1?'done':''}">${i+1}. ${s}</span>`).join('')}</div></div>`:''}</div>`;
  }
  function bindNav() {
    document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>go(b.dataset.nav));
    const logout=document.getElementById('logout');
    if(logout) logout.onclick=async()=>{try{await api('/logout',{method:'POST'});reset();render();}catch(e){notice(e.message);}};
  }
  async function go(page) {
    if(state.edit && !confirm('Выйти из редактора? Несохранённые изменения не войдут в ревью.')) return;
    state.edit=false;
    try {
      if(page==='history') state.history=await api('/reviews');
      if(page==='progress') state.metrics=await api('/progress');
      if(page==='system') state.system=await api('/system');
      state.page=page; render();
    } catch(e){notice(e.message);}
  }
  function login() {
    app.innerHTML=`<div class="shell">${topbar()}<section class="card login-card">
      <div class="eyebrow">Личный кабинет</div><h2>Войти в SpecGuard</h2>
      <p>Проверяйте ТЗ и сохраняйте результаты в своём профиле.</p>
      <form id="login-form"><label class="field"><span>Корпоративная почта</span><input name="email" type="email" autocomplete="username" required></label>
      <label class="field"><span>Пароль</span><input name="password" type="password" autocomplete="current-password" required></label>
      <button class="btn btn-primary full" type="submit">Войти</button></form>
      ${state.meta?.demo?'<p class="login-note">Демо: analyst@example.com / demo1234</p>':''}</section></div>`;
    document.getElementById('login-form').onsubmit=async e=>{
      e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;
      const form=new FormData(e.target);
      try {state.user=await api('/login',{method:'POST',body:{email:form.get('email'),password:form.get('password')}});
        await resume();}catch(err){notice(err.message);button.disabled=false;}
    };
  }
  function start() {
    app.innerHTML=`<div class="shell">${topbar(1)}<section class="card hero hero-single">
      <div><div class="input-header"><h2>Подготовим ТЗ к проверке</h2><span class="chip">4 ревьюера + критик + судья</span></div>
      <p class="lead">Загрузите документ или начните с шаблона. Анализ выполняется на сервере.</p>
      ${state.job?'<div class="banner">Проверка уже выполняется. <button class="btn btn-secondary btn-sm" id="resume-job">Открыть статус</button></div>':''}
      <h3 class="section-label">Шаблон для нового черновика</h3><div class="type-grid">
      ${Object.entries(types).map(([key,[title,desc]])=>`<button class="type-card ${key===state.docType?'selected':''}" data-type="${key}"><strong>${title}</strong><span>${desc}</span></button>`).join('')}</div>
      <div class="btn-row"><button class="btn btn-secondary" id="template">Вставить шаблон</button></div>
      <div class="upload-box"><label for="file">Или загрузите своё ТЗ</label><input type="file" id="file" accept=".pdf,.docx,.txt,.md" ${state.busy?'disabled':''}>
      <p>PDF с текстовым слоем, DOCX, TXT, Markdown · до 20 МБ · OCR сканов пока недоступен</p></div>
      <label class="field"><span>Название документа</span><input id="filename" maxlength="255" value="${E(state.filename)}"></label>
      <label class="field"><span>Текст для проверки</span><textarea id="source" maxlength="${state.meta.max_chars}" placeholder="Вставьте текст или загрузите файл">${E(state.text)}</textarea></label>
      <div class="btn-row"><button class="btn btn-primary" id="start-review" ${state.busy||state.job?'disabled':''}>${state.busy?'Читаем файл…':'Запустить ревью'}</button>
      <span class="muted">До ${state.meta.max_chars.toLocaleString('ru-RU')} символов</span></div></div></section></div>`;
    bindNav();
    document.querySelectorAll('[data-type]').forEach(b=>b.onclick=()=>{state.docType=b.dataset.type;render();});
    document.getElementById('source').oninput=e=>{state.text=e.target.value;};
    document.getElementById('filename').oninput=e=>{state.filename=e.target.value;};
    document.getElementById('template').onclick=()=>{
      if(state.text.trim()&&!confirm('Заменить введённый текст пустым шаблоном?'))return;
      state.text=U.template(types[state.docType][0]);state.uploadId=null;render();
    };
    document.getElementById('file').onchange=async e=>{
      const file=e.target.files[0];if(!file)return;
      if(file.size>state.meta.max_upload){notice('Максимальный размер файла — 20 МБ');return;}
      state.busy=true;render();
      try{const doc=await api('/uploads?filename='+encodeURIComponent(file.name),{method:'POST',body:file});
        state.text=doc.text;state.filename=doc.filename;state.uploadId=doc.id;
      }catch(err){notice(err.message);}finally{state.busy=false;render();}
    };
    document.getElementById('start-review').onclick=()=>launch(state.text,state.filename,state.uploadId);
    const resume=document.getElementById('resume-job');if(resume)resume.onclick=()=>{state.page='busy';render();};
  }
  async function launch(text,filename,uploadId=null) {
    if(!text.trim()){notice('Добавьте текст документа');return;}
    if(state.busy||state.job)return;
    state.busy=true;
    try{const job=await api('/reviews',{method:'POST',body:{text,filename,upload_id:uploadId}});
      state.job={...job,filename,created:Date.now()/1000};state.edit=false;state.page='busy';render();poll();
    }catch(e){notice(e.message);}finally{state.busy=false;}
  }
  function busy() {
    app.innerHTML=`<div class="shell">${topbar(2)}<section class="card busy-card"><div class="spinner" aria-hidden="true"></div>
      <h2>${state.job?.status==='queued'?'Документ в очереди':'Агенты анализируют документ'}</h2>
      <p>${E(state.job?.filename||'')}</p><p class="muted">Аналитик, Data Engineer, архитектор и QA работают параллельно. Затем критик и судья проверяют замечания.</p>
      <p class="muted">Страницу можно обновить — статус и результат сохранятся. Запросы к модели могут занимать несколько минут.</p>
      <button class="btn btn-secondary" data-nav="history">Перейти в историю</button></section></div>`;bindNav();
  }
  async function poll() {
    clearTimeout(state.timer);if(!state.job||!state.user)return;
    const jobId=state.job.id;
    try{
      const job=await api('/jobs/'+jobId);if(!state.user||state.job?.id!==jobId)return;
      state.job=job;
      if(job.status==='completed') {state.job=null;
        if(state.page==='busy') await openReview(job.review_id);
        else {notice('Ревью завершено. Результат доступен в истории.');if(state.page==='history')await go('history');}
        return;}
      if(job.status==='failed'){state.job=null;state.page='start';render();notice(job.error);return;}
      if(state.page==='busy')render();
    }catch(e){if(!state.user)return;notice('Не удалось обновить статус. Повторим автоматически.');}
    state.timer=setTimeout(poll,3000);
  }
  async function openReview(id) {
    try{state.review=await api('/reviews/'+id);state.page='review';state.edit=false;
      state.quote='';state.query='';state.filter='open';render();}catch(e){notice(e.message);}
  }
  function issueHtml(i,index) {
    const color={blocker:'red',major:'orange',minor:'yellow',suggestion:'green'}[i.severity]||'orange';
    return `<article class="comment ${color} ${i.employee_decision!=='open'?'done':''}" id="issue-${E(i.id)}">
      <div class="meta"><span class="num">${index+1}</span><span>${E(U.severity[i.severity]||i.severity)}</span><span>${E(U.decisions[i.employee_decision])}</span></div>
      <h4>${E(i.title)}</h4><p class="problem">${E(i.problem)}</p>
      <details><summary>Детали и вопросы</summary><p class="muted">${E(i.agent)} · ${E(i.category)}</p>
      <p><strong>Влияние:</strong> ${E(i.impact)}</p><blockquote>${E(i.evidence)}</blockquote>
      <p><strong>Вопрос:</strong> ${E(i.question)}</p><p><strong>Рекомендация:</strong> ${E(i.recommendation)}</p></details>
      <div class="comment-actions"><button class="btn btn-ghost btn-sm" data-locate="${E(i.id)}">Найти в тексте</button>
      ${i.employee_decision==='open'?`<button class="btn btn-secondary btn-sm" data-decision="accepted" data-id="${E(i.id)}">Принять</button>`:''}
      ${i.employee_decision!=='fixed'?`<button class="btn btn-primary btn-sm" data-decision="fixed" data-id="${E(i.id)}">Исправлено</button>`:''}
      ${i.employee_decision!=='rejected'?`<button class="btn btn-ghost btn-sm" data-decision="rejected" data-id="${E(i.id)}">Отклонить</button>`:''}
      ${i.employee_decision!=='open'?`<button class="btn btn-ghost btn-sm" data-decision="open" data-id="${E(i.id)}">Вернуть</button>`:''}</div></article>`;
  }
  function review() {
    const r=state.review,s=U.stats(r.issues),visible=U.filter(r.issues,state.filter,state.query);
    app.innerHTML=`<div class="review-shell">${topbar(2)}<div class="statusbar"><div class="status-left">
      <span class="chip">${E(r.document)}</span><span class="chip critical">${s.critical} критичных</span><span class="chip">${s.open} открыто</span><span class="chip ok">${s.confirmed} подтверждено</span></div>
      <div class="status-actions">${state.edit?'<button class="btn btn-primary btn-sm" id="save-recheck">Сохранить и перепроверить</button><button class="btn btn-secondary btn-sm" id="cancel-edit">Отмена</button>':
      `<button class="btn btn-secondary btn-sm" id="edit" ${!r.text?'disabled':''}>✎ Редактировать текст</button>
      <button class="btn btn-secondary btn-sm" id="recheck" ${!r.text||state.job?'disabled':''}>Перепроверить</button><button class="btn btn-primary btn-sm" id="summary">К итогу</button>`}</div></div>
      <div class="banner ${r.status.startsWith('Проверка')?'':'neutral'}">${E(r.status)}${r.warnings.length?' · '+E(r.warnings.join('; ')):''}</div>
      <div class="workspace"><div class="doc-pane"><div class="doc-paper"><div class="doc-title">${E(r.document)}</div>
      ${state.edit?`<textarea id="doc-editor" class="doc-editor" aria-label="Текст ТЗ" maxlength="${state.meta.max_chars}">${E(state.editText)}</textarea>`:U.documentHtml(r.text,state.quote)}</div></div>
      <aside class="comments-pane"><div class="comments-head"><div class="comments-head-row"><span>Замечания · ${visible.length}</span><span>${s.fixed}/${s.total} исправлено</span></div>
      <input class="search-input" id="search" aria-label="Поиск замечаний" placeholder="Поиск замечаний" value="${E(state.query)}"></div>
      <div class="comments-filters">${[['critical','Критичные'],['open','Открытые'],['closed','Закрытые'],['all','Все']].map(([key,label])=>`<button class="filter-btn ${state.filter===key?'active':''}" data-filter="${key}">${label}</button>`).join('')}</div>
      <div class="comments-list" id="comments-list">${visible.length?visible.map(i=>issueHtml(i,r.issues.indexOf(i))).join(''):'<p class="muted" style="padding:16px">В этом фильтре замечаний нет.</p>'}</div></aside></div>
      <p class="muted">Решения относятся к исходному ревью. После правок запустите новую проверку. Рекомендации ИИ требуют подтверждения автором.</p></div>`;
    bindNav();bindIssues();
    document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{state.filter=b.dataset.filter;render();});
    document.getElementById('search').oninput=e=>{
      state.query=e.target.value;document.getElementById('comments-list').innerHTML=U.filter(r.issues,state.filter,state.query).map(i=>issueHtml(i,r.issues.indexOf(i))).join('')||'<p class="muted">Ничего не найдено</p>';bindIssues();
    };
    const edit=document.getElementById('edit');if(edit)edit.onclick=()=>{state.edit=true;state.editText=r.text;render();};
    const editor=document.getElementById('doc-editor');if(editor)editor.oninput=e=>{state.editText=e.target.value;};
    const cancel=document.getElementById('cancel-edit');if(cancel)cancel.onclick=()=>{state.edit=false;render();};
    const save=document.getElementById('save-recheck');if(save)save.onclick=()=>launch(document.getElementById('doc-editor').value,r.document);
    const recheck=document.getElementById('recheck');if(recheck)recheck.onclick=()=>launch(r.text,r.document);
    const summary=document.getElementById('summary');if(summary)summary.onclick=()=>{state.page='summary';render();};
  }
  function bindIssues() {
    document.querySelectorAll('[data-decision]').forEach(b=>b.onclick=async()=>{
      b.disabled=true;
      try{await api('/issues/'+b.dataset.id+'/decision',{method:'POST',body:{decision:b.dataset.decision}});
        state.review.issues.find(i=>i.id===b.dataset.id).employee_decision=b.dataset.decision;
        if(state.edit){notice('Решение сохранено');b.disabled=false;}else render();
      }catch(e){notice(e.message);b.disabled=false;}
    });
    document.querySelectorAll('[data-locate]').forEach(b=>b.onclick=()=>{
      if(state.edit){notice('Сначала завершите редактирование');return;}
      const issue=state.review.issues.find(i=>i.id===b.dataset.locate);
      const quotes=issue.evidence.split('\n---\n');
      const quote=quotes.find(q=>state.review.text?.includes(q));
      if(!quote){notice('Дословная цитата не найдена в исходном тексте');return;}
      state.quote=quote;render();document.getElementById('active-quote')?.scrollIntoView({block:'center',behavior:'smooth'});
    });
  }
  function download(name,type,content) {
    const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function summary() {
    const r=state.review,s=U.stats(r.issues);
    app.innerHTML=`<div class="shell">${topbar(3)}<section class="card content-card"><div class="eyebrow">Итог проверки</div><h2>${E(r.document)}</h2>
      <div class="banner ${r.status.startsWith('Проверка')?'':'neutral'}">${E(r.status)}</div>
      <p class="muted">Вердикт получен для исходного текста. Отметка «Исправлено» не заменяет повторный анализ.</p>
      <div class="summary-grid">${[['Замечаний',s.total],['Открыто',s.open],['Подтверждено',s.confirmed],['Исправлено',s.fixed]].map(([label,n])=>`<div class="card summary-card"><span>${label}</span><strong>${n}</strong></div>`).join('')}</div>
      ${r.warnings.map(w=>`<p class="banner">${E(w)}</p>`).join('')}
      <div class="btn-row"><button class="btn btn-primary" id="back-review">К замечаниям</button><button class="btn btn-secondary" id="json">Скачать отчёт JSON</button>
      <button class="btn btn-secondary" id="print">Печать / PDF</button><button class="btn btn-secondary" id="text" ${!r.text?'disabled':''}>Скачать текст ТЗ</button>
      ${r.has_original?`<a class="btn btn-secondary" href="/api/reviews/${E(r.id)}/original" download>Исходный файл</a>`:''}
      <button class="btn btn-ghost" data-nav="start">Новая проверка</button></div></section></div>`;
    bindNav();document.getElementById('back-review').onclick=()=>{state.page='review';render();};
    document.getElementById('json').onclick=()=>download('review.json','application/json',JSON.stringify(r,null,2));
    document.getElementById('text').onclick=()=>download('specification.txt','text/plain;charset=utf-8',r.text);
    document.getElementById('print').onclick=()=>{
      document.getElementById('print-report').innerHTML=`<h1>${E(r.document)}</h1><p>${E(r.status)}</p><pre>${E(r.text||'Исходный текст не сохранён')}</pre><h2>Замечания</h2>`+
        r.issues.map(i=>`<article><h3>${E(i.title)}</h3><p>${E(U.severity[i.severity])} · ${E(U.decisions[i.employee_decision])}</p><p>${E(i.problem)}</p><pre>${E(i.evidence)}</pre><p>${E(i.question)}</p><p>${E(i.recommendation)}</p></article>`).join('');window.print();
    };
  }
  function history() {
    const h=state.history;
    app.innerHTML=`<div class="shell">${topbar()}<section class="card content-card"><div class="input-header"><h2>История проверок</h2><button class="btn btn-primary" data-nav="start">Новое ревью</button></div>
      ${h.jobs.map(j=>`<div class="banner">${E(j.filename)} · ${E(j.status==='failed'?j.error:j.status==='queued'?'В очереди':'Анализируется')}
      ${j.status!=='failed'?`<button class="btn btn-secondary btn-sm" data-job="${E(j.id)}">Открыть</button>`:''}</div>`).join('')}
      ${h.reviews.length?`<div class="table-scroll"><table class="history-table"><thead><tr><th>Документ</th><th>Дата</th><th>Результат</th><th>Замечаний</th><th></th></tr></thead><tbody>
      ${h.reviews.map(r=>`<tr><td>${E(r.document)}</td><td>${E(new Date(r.created_at).toLocaleString('ru-RU'))}</td><td>${E(r.status)}</td><td>${r.issues.length}</td><td><button class="btn btn-secondary btn-sm" data-review="${E(r.id)}">Открыть</button></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">Пока нет проверок. Загрузите первое ТЗ.</p>'}
      <p class="muted">Показаны последние 100 проверок вашего аккаунта.</p></section></div>`;
    bindNav();document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>openReview(b.dataset.review));
    document.querySelectorAll('[data-job]').forEach(b=>b.onclick=()=>{state.job=h.jobs.find(j=>j.id===b.dataset.job);state.page='busy';render();poll();});
  }
  function progress() {
    const m=state.metrics,categories=Object.entries(m.categories).sort((a,b)=>b[1]-a[1]);
    app.innerHTML=`<div class="shell">${topbar()}<h2>Мой прогресс</h2><p class="muted">В статистику входят только принятые и исправленные замечания, а не неподтверждённые гипотезы ИИ.</p>
      <div class="summary-grid">${[['Проверено ТЗ',m.reviews],['Открыто',m.open],['Подтверждено',m.confirmed],['Исправлено',m.fixed]].map(([label,n])=>`<div class="card summary-card"><span>${label}</span><strong>${n}</strong></div>`).join('')}</div>
      <section class="card content-card"><h3>Повторяющиеся ошибки</h3>${categories.length?categories.map(([name,count])=>`<div class="category-row"><span>${E(name)}</span><strong>${count}</strong></div>`).join(''):'<p class="muted">Подтверждённых ошибок пока нет.</p>'}
      ${m.confirmed?`<p class="muted">Исправлено ${Math.round(m.fixed/m.confirmed*100)}% подтверждённых замечаний.</p>`:''}</section>
      <section class="card content-card"><h3>Чек-лист перед передачей ТЗ</h3><div class="checklist">${[...state.meta.checklist,...categories.slice(0,5).map(([name])=>'Перепроверить: '+name)].map((label,index)=>`<label><input type="checkbox" data-check="${index}" ${state.checklist.has(index)?'checked':''}><span>${E(label)}</span></label>`).join('')}</div>
      <p class="muted">Чек-лист кейсодателя. Отметки действуют в этой вкладке и не меняют результаты ревью.</p></section></div>`;
    bindNav();document.querySelectorAll('[data-check]').forEach(c=>c.onchange=()=>{const n=Number(c.dataset.check);c.checked?state.checklist.add(n):state.checklist.delete(n);});
  }
  function system() {
    const s=state.system;
    app.innerHTML=`<div class="shell">${topbar()}<section class="card content-card"><h2>Как работает проверка</h2>
      <ol><li>Из файла извлекается полный текст.</li><li>Аналитик, Data Engineer, архитектор и QA проверяют документ параллельно.</li>
      <li>Критик проверяет основания замечаний.</li><li>Судья объединяет дубли и уточняет приоритет.</li><li>Вы принимаете решения; только подтверждённые ошибки попадают в профиль.</li></ol>
      <p>Модель: ${E(s.model)}</p><p>Критик и судья: ${s.controls?'включены':'выключены'}</p><p>Хранилище: ${E(s.storage)}</p>
      ${!s.configured?'<div class="banner">Модель не настроена. Анализ недоступен.</div>':''}
      <p class="muted">Результат ИИ — предварительное ревью, не гарантия отсутствия дефектов.</p></section></div>`;bindNav();
  }
  function render() {
    if(!state.user){login();return;}
    ({start,review,summary,history,progress,system,busy}[state.page]||start)();
  }
  async function resume() {
    const h=await api('/reviews');state.history=h;
    const active=h.jobs.find(j=>j.status==='queued'||j.status==='running');
    state.page=active?'busy':'start';state.job=active||null;render();if(active)poll();
  }
  window.addEventListener('beforeunload',e=>{if(state.edit){e.preventDefault();e.returnValue='';}});
  async function boot() {
    try{state.meta=await api('/meta');
      try{state.user=await api('/me');}catch{state.user=null;}
      if(state.user)await resume();else render();
    }catch{app.innerHTML='<div class="boot">Не удалось подключиться к серверу. Обновите страницу.</div>';}
  }
  boot();
})();
