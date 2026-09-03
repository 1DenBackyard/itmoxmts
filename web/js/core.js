/* Pure rendering helpers. No demo findings, scoring, or simulated analysis. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const severity = {blocker:'Блокирующее',major:'Существенное',minor:'Незначительное',suggestion:'Рекомендация'};
  const decisions = {open:'Открыто',accepted:'Принято',fixed:'Исправлено',rejected:'Отклонено'};
  const ranks = {blocker:0,major:1,minor:2,suggestion:3};
  function filter(issues, mode, query='') {
    return [...issues].filter(i => (mode === 'all' ||
      (mode === 'open' && i.employee_decision === 'open') ||
      (mode === 'closed' && i.employee_decision !== 'open') ||
      (mode === 'critical' && ['blocker','major'].includes(i.severity) && i.employee_decision === 'open')) &&
      `${i.title} ${i.problem} ${i.category}`.toLowerCase().includes(query.toLowerCase()))
      .sort((a,b) => (ranks[a.severity] ?? 9) - (ranks[b.severity] ?? 9));
  }
  function stats(issues) {
    return {total:issues.length, open:issues.filter(i=>i.employee_decision==='open').length,
      confirmed:issues.filter(i=>['accepted','fixed'].includes(i.employee_decision)).length,
      fixed:issues.filter(i=>i.employee_decision==='fixed').length,
      critical:issues.filter(i=>['blocker','major'].includes(i.severity)).length};
  }
  function documentHtml(text, quote='') {
    if (!text) return '<p class="muted">Исходный текст этой старой проверки не сохранён. Загрузите исходный файл для нового ревью.</p>';
    if (quote && text.includes(quote)) {
      const at=text.indexOf(quote);
      return `<div class="body-text">${escape(text.slice(0,at))}<mark class="cmt active" id="active-quote" tabindex="0">${escape(quote)}</mark>${escape(text.slice(at+quote.length))}</div>`;
    }
    const headings = /^(общие сведения|решаемая проблема|продуктовые метрики|заказчики|нефункциональные требования|системы-источники|data catalog|исходники проекта|команда|jira|источники данных|источники обогащения данных|при[её]мники данных|схема потоков данных|алгоритм обработки потока|структура данных|пример данных|ddl|faq|история изменений|формирование ключа.*|шаг \d+\..*)$/i;
    const lines=text.split('\n'); let out='', body=[];
    const flush=()=>{if(body.length){out+=`<div class="body-text">${escape(body.join('\n'))}</div>`;body=[];}};
    for(let n=0;n<lines.length;n++) {
      const line=lines[n];
      if(line.includes('|') && (lines[n+1]||'').includes('|')) {
        flush(); const rows=[];
        while(n<lines.length && lines[n].includes('|')) {rows.push(lines[n++]);} n--;
        out+='<div class="table-wrap"><table class="doc-table"><tbody>';
        rows.filter(row=>!/^\s*\|?[\s:|\-]+\|?\s*$/.test(row)).forEach((row,index)=>{
          const cells=row.trim().replace(/^\|/,'').replace(/\|$/,'').split('|');
          const tag=index===0?'th':'td'; out+='<tr>'+cells.map(c=>`<${tag}>${escape(c.trim())}</${tag}>`).join('')+'</tr>';
        }); out+='</tbody></table></div>';
      } else if(headings.test(line.trim()) || /^#{1,4}\s/.test(line)) {
        flush(); out+=`<section class="doc-section"><h3>${escape(line.replace(/^#{1,4}\s/,''))}</h3></section>`;
      } else {body.push(line);}
    } flush(); return out;
  }
  const template = title => `${title}\n\nОбщие сведения\n\nРешаемая проблема\n\nПродуктовые метрики\n\nЗаказчики\n\nНефункциональные требования\n\nСистемы-источники\n\nData Catalog\n\nИсходники проекта\n\nКоманда\n\nJIRA\n\nИсточники данных\nОписание | Тип источника | Ссылка | Сериализация\n\nИсточники обогащения данных\n\nПриемники данных\nОписание | Кластер | Ссылка на Каталог | Сериализация\n\nСхема потоков данных\n\nАлгоритм обработки потока\n\nШаг 1. Фильтрация данных\n\nШаг 2. Обогащение данных\n\nШаг 3. Преобразования\n\nФормирование ключа Kafka / партиции HDFS\n\nСтруктура данных\nАтрибут | Тип | NULL / NOT NULL | Описание | Источник | Исходный атрибут | Формула\n\nПример данных\n\nDDL\n\nFAQ\n\nИстория изменений\n`;
  globalThis.SpecUI = {escape,severity,decisions,filter,stats,documentHtml,template};
})();
