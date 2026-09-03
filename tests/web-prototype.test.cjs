const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../prototypes/web-review/web');
const context = vm.createContext({
  window: {}, localStorage: { getItem: () => null, setItem: () => {} },
});
for (const name of ['autofix', 'analyzer', 'learning']) {
  vm.runInContext(fs.readFileSync(path.join(web, `js/${name}.js`), 'utf8'), context);
  Object.assign(context, context.window);
}
const analyzer = context.window.MTSAnalyzer;
const dataset = JSON.parse(fs.readFileSync(path.join(web, 'data/dataset.json'), 'utf8'));

test('each sample renders and can be rechecked without backend', () => {
  for (const sample of dataset.samples) {
    const copy = analyzer.cloneSample(sample);
    analyzer.ensureStableNumbers(copy.findings, copy.blocks);
    const { html } = analyzer.buildDocumentHtml(copy.blocks, copy.findings, copy.filename);
    assert.ok(html.includes('doc-table'));
    const result = analyzer.refreshAfterEdit(copy, copy.text, dataset.block_defs, copy.doc_type);
    assert.ok(Array.isArray(result.blocks));
    assert.ok(Array.isArray(result.findings));
  }
});

test('untrusted HTML is escaped by document renderer', () => {
  const { html } = analyzer.buildDocumentHtml(
    [{id: 'general', present: true, title: '<script>bad</script>', content: '<img src=x onerror=alert(1)>'}],
    [], '<script>bad</script>',
  );
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<img src=x'));
});

test('learning excludes rejected and unconfirmed findings', () => {
  const learning = context.window.MTSLearning;
  const raw = JSON.parse(fs.readFileSync(path.join(web, 'data/learning.json'), 'utf8'));
  const data = learning.hydrate(raw);
  assert.equal(data.demo, true);
  const result = learning.summary(data, learning.defaultFilters());
  assert.ok(result.docs > 0);
  assert.ok(result.confirmedList.every(f => f.confirm_status === 'confirmed'));
});

test('heading-only template has missing required sections', () => {
  for (const [type, text] of Object.entries(dataset.blank_templates)) {
    const blocks = analyzer.parseDocumentBlocks(text, dataset.block_defs, type);
    const issues = analyzer.buildBlankFindings(blocks, type);
    assert.ok(issues.length > 0, type);
  }
});
