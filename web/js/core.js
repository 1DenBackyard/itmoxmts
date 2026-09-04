/* Pure rendering helpers. No demo findings, scoring, or simulated analysis. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const severity = {blocker:'Блокирующее',major:'Существенное',minor:'Незначительное',suggestion:'Рекомендация'};
  const decisions = {open:'Открыто',accepted:'Принято',fixed:'Исправлено',rejected:'Отклонено'};
  const ranks = {blocker:0,major:1,minor:2,suggestion:3};
  function filter(issues, mode, query='', level='all') {
    return [...issues].filter(i => (mode === 'all' ||
      (mode === 'open' && i.employee_decision === 'open') ||
      (mode === 'closed' && i.employee_decision !== 'open') ||
      (mode === 'critical' && ['blocker','major'].includes(i.severity) && i.employee_decision === 'open')) &&
      (level === 'all' || i.severity === level) &&
      `${severity[i.severity] || ''} ${i.title} ${i.problem} ${i.category}`.toLowerCase().includes(query.toLowerCase()))
      .sort((a,b) => (ranks[a.severity] ?? 9) - (ranks[b.severity] ?? 9));
  }
  function stats(issues) {
    return {total:issues.length, open:issues.filter(i=>i.employee_decision==='open').length,
      confirmed:issues.filter(i=>['accepted','fixed'].includes(i.employee_decision)).length,
      fixed:issues.filter(i=>i.employee_decision==='fixed').length,
      critical:issues.filter(i=>['blocker','major'].includes(i.severity)).length};
  }
  function anchors(text, issues) {
    const found=[];
    issues.forEach((issue,index)=>{
      const quotes=String(issue.evidence||'').split('\n---\n').map(q=>q.trim()).filter(Boolean);
      for(const quote of new Set(quotes)) {
        const start=(text||'').indexOf(quote);
        if(start>=0) found.push({start,end:start+quote.length,id:issue.id,number:index+1,
          severity:issue.severity,decision:issue.employee_decision,
          repeated:text.indexOf(quote,start+1)>=0});
      }
    });
    return found;
  }
  function documentHtml(text, quote='', issues=[], selectedId='') {
    if (!text) return '<p class="muted">Исходный текст этой старой проверки не сохранён. Загрузите исходный файл для нового ревью.</p>';
    if (!issues.length && quote && text.includes(quote)) {
      const at=text.indexOf(quote);
      return `<div class="body-text">${escape(text.slice(0,at))}<mark class="cmt active" id="active-quote" tabindex="0">${escape(quote)}</mark>${escape(text.slice(at+quote.length))}</div>`;
    }
    const ranges=anchors(text,issues), numbered=new Set();
    function rich(value,offset) {
      const end=offset+value.length, local=ranges.filter(r=>r.start<end&&r.end>offset);
      const cuts=[...new Set([offset,end,...local.flatMap(r=>[Math.max(offset,r.start),Math.min(end,r.end)])])].sort((a,b)=>a-b);
      let result='';
      for(let i=0;i<cuts.length-1;i++) {
        const a=cuts[i],b=cuts[i+1],active=local.filter(r=>r.start<b&&r.end>a);
        const escaped=escape(value.slice(a-offset,b-offset));
        if(!active.length){result+=escaped;continue;}
        const selected=active.some(r=>r.id===selectedId);
        result+=`<mark class="issue-highlight ${selected?'selected':''} ${active.every(r=>['fixed','rejected'].includes(r.decision))?'resolved':''}">${escaped}</mark>`;
        for(const r of active) if(!numbered.has(r.id)) {
          numbered.add(r.id);
          result+=`<button class="annotation-index ${r.id===selectedId?'selected':''}" data-annotation="${escape(r.id)}" id="anchor-${escape(r.id)}" aria-label="Замечание ${r.number}" title="Замечание ${r.number}${r.repeated?' — первое совпадение повторяющейся цитаты':''}">[${r.number}]</button>`;
        }
      }
      return result;
    }
    const headings = /^(общие сведения|решаемая проблема|продуктовые метрики|заказчики|нефункциональные требования|системы-источники|data catalog|исходники проекта|команда|jira|источники данных|источники обогащения данных|при[её]мники данных|схема потоков данных|алгоритм обработки потока|структура данных|пример данных|ddl|faq|история изменений|формирование ключа.*|шаг \d+\..*)$/i;
    const lines=text.split('\n'); let out='', body=[],position=0;
    const offsets=lines.map(line=>{const offset=position;position+=line.length+1;return offset;});
    const flush=()=>{if(body.length){out+=`<div class="body-text">${body.join('\n')}</div>`;body=[];}};
    for(let n=0;n<lines.length;n++) {
      const line=lines[n];
      if(line.includes('|') && (lines[n+1]||'').includes('|')) {
        flush(); const rows=[];
        while(n<lines.length && lines[n].includes('|')) {rows.push({text:lines[n],offset:offsets[n]});n++;} n--;
        out+='<div class="table-wrap"><table class="doc-table"><tbody>';
        rows.filter(row=>!/^\s*\|?[\s:|\-]+\|?\s*$/.test(row.text)).forEach((row,index)=>{
          const trimmed=row.text.trim(), leading=row.text.indexOf(trimmed);
          let cursor=row.offset+leading+(trimmed.startsWith('|')?1:0);
          const cells=trimmed.replace(/^\|/,'').replace(/\|$/,'').split('|');
          const tag=index===0?'th':'td'; out+='<tr>'+cells.map(c=>{
            const content=c.trim(),start=cursor+c.indexOf(content);cursor+=c.length+1;
            return `<${tag}>${rich(content,start)}</${tag}>`;
          }).join('')+'</tr>';
        }); out+='</tbody></table></div>';
      } else if(headings.test(line.trim()) || /^#{1,4}\s/.test(line)) {
        const label=line.replace(/^#{1,4}\s/,'');
        flush(); out+=`<section class="doc-section"><h3>${rich(label,offsets[n]+line.length-label.length)}</h3></section>`;
      } else {body.push(rich(line,offsets[n]));}
    } flush(); return out;
  }
  const template = title => `${title}\n\nОбщие сведения\n\nРешаемая проблема\n\nПродуктовые метрики\n\nЗаказчики\n\nНефункциональные требования\n\nСистемы-источники\n\nData Catalog\n\nИсходники проекта\n\nКоманда\n\nJIRA\n\nИсточники данных\nОписание | Тип источника | Ссылка | Сериализация\n\nИсточники обогащения данных\n\nПриемники данных\nОписание | Кластер | Ссылка на Каталог | Сериализация\n\nСхема потоков данных\n\nАлгоритм обработки потока\n\nШаг 1. Фильтрация данных\n\nШаг 2. Обогащение данных\n\nШаг 3. Преобразования\n\nФормирование ключа Kafka / партиции HDFS\n\nСтруктура данных\nАтрибут | Тип | NULL / NOT NULL | Описание | Источник | Исходный атрибут | Формула\n\nПример данных\n\nDDL\n\nFAQ\n\nИстория изменений\n`;
  function applyProposal(text, snapshot, proposal, replacement, limit=120000) {
    if(text!==snapshot) throw new Error('Текст изменился. Запросите правку заново.');
    if(proposal.needs_input || !replacement.trim()) throw new Error('Сначала уточните недостающие данные.');
    let updated;
    if(proposal.mode==='replace') {
      const before=proposal.before,at=text.indexOf(before);
      if(!before || at<0 || text.indexOf(before,at+1)>=0) throw new Error('Место замены неоднозначно. Используйте редактор.');
      updated=text.slice(0,at)+replacement+text.slice(at+before.length);
    } else if(proposal.mode==='append') updated=text+'\n\n'+replacement;
    else throw new Error('Автоматическая замена недоступна.');
    if(updated.length>limit) throw new Error('После правки текст превышает лимит.');
    return updated;
  }
  globalThis.SpecUI = {escape,severity,decisions,filter,stats,anchors,documentHtml,template,applyProposal};
})();
