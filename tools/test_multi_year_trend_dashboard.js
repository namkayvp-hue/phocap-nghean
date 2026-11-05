// Run: node tools/test_multi_year_trend_dashboard.js [read-only dashboard JSON]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../app/templates/surveys/multi_year_trend.html'), 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map(match => match[1]).find(text => text.includes("let TAB='roadmap'"));
assert.ok(script, 'Dashboard script exists');

function element() {
  return {
    value: '', textContent: '', innerHTML: '', dataset: {}, attributes: {}, handlers: {},
    classList: {add() {}, remove() {}},
    addEventListener(type, callback) {this.handlers[type] = callback;},
    dispatchEvent(event) {this.handlers[event.type]?.(event);},
    setAttribute(key, value) {this.attributes[key] = value;},
    scrollIntoView() {this.scrolled = true;},
  };
}

async function check(data) {
  const fields = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], element()]));
  const tabs = ['roadmap', 'five'].map(tab => Object.assign(element(), {dataset: {tab}}));
  const buttons = ['2026', '2027', '2028', '2029', '2030'].map(year => Object.assign(element(), {dataset: {year}}));
  const quickSearch = element();
  let quickSearchRefreshes = 0;
  quickSearch.addEventListener('input', () => {quickSearchRefreshes++;});
  fields['pcgd-recognition-dashboard'].querySelectorAll = selector => selector === '.pcgd-tab' ? tabs : [quickSearch];
  fields['db-roadmap-bars'].querySelectorAll = () => buttons;
  let fetches = 0;
  vm.runInNewContext(script, {
    document: {getElementById: id => fields[id]},
    window: {location: {pathname: '/dieu-tra/1/xu-huong-lien-nam'}}, Event,
    fetch: async (url, options) => {
      fetches++;
      assert.equal(url, '/dieu-tra/1/dashboard-dat-chuan-data');
      assert.equal(options.method, undefined, 'Only a GET request');
      return {json: async () => data};
    },
  });
  // Controls are safe even before the data request finishes.
  fields['db-search'].dispatchEvent(new Event('input'));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(fields['db-total'].textContent, String(data.summary.total_communes));
  assert.equal((fields['db-roadmap-bars'].innerHTML.match(/<button type="button"/g) || []).length, 5);
  const barsHtml = fields['db-roadmap-bars'].innerHTML;
  const body = () => fields['db-table-body'].innerHTML;
  const clickYear = year => fields['db-roadmap-bars'].handlers.click({target: {
    closest: () => buttons.find(button => button.dataset.year === year),
  }});
  function verify(rows) {
    assert.equal(fields['db-total'].textContent, String(rows.length));
    assert.equal(fields['db-row-count'].textContent, `${rows.length} xã/phường`);
    assert.equal(fields['db-complete'].textContent, String(rows.filter(row => row.survey_complete).length));
    assert.equal(fields['db-five-pass'].textContent, String(rows.filter(row => row.five_status_code === 'PASS').length));
    assert.equal(fields['db-special'].textContent, String(rows.filter(row => row.is_special).length));
    assert.equal((body().match(/<tr>/g) || []).length, Math.max(1, rows.length));
    for (const row of rows) assert.ok(body().includes(`<strong>${row.name}</strong>`));
    if (!rows.length) assert.ok(body().includes('Không có dữ liệu phù hợp.'));
  }
  for (const year of ['2026', '2027', '2028', '2029', '2030']) {
    fields['db-search'].value = 'no-match';
    fields['db-status-filter'].value = 'FAIL';
    quickSearch.value = 'previous search';
    clickYear(year);
    const rows = data.rows.filter(row => String(row.target_year_3_5) === year);
    verify(rows);
    assert.equal(fields['db-year-filter'].value, year);
    assert.equal(quickSearch.value, '');
    assert.equal(fields['db-due'].textContent, String(rows.length));
    assert.ok(fields['db-due-label'].textContent.includes(year));
    assert.ok(fields['db-table-title'].textContent.endsWith(year));
    assert.ok(fields['db-table-title'].scrolled);
    for (const button of buttons) assert.equal(button.attributes['aria-pressed'], String(button.dataset.year === year));
    for (const row of rows) {
      assert.ok(body().includes(`<strong>${row.completed_forms}/${row.forms}</strong>`));
      assert.ok(body().includes(`<td>${row.age_3_5_total}</td>`));
    }
  }
  clickYear('2026');
  tabs[1].dispatchEvent(new Event('click'));
  const selected = data.rows.filter(row => String(row.target_year_3_5) === '2026');
  verify(selected);
  for (const row of selected) {
    assert.ok(body().includes(`<td>${row.age_5_total}</td>`));
    assert.ok(body().includes(`${row.age_5_completed} · `));
  }
  fields['db-status-filter'].value = 'PASS';
  fields['db-status-filter'].dispatchEvent(new Event('change'));
  verify(selected.filter(row => row.five_status_code === 'PASS'));
  fields['db-status-filter'].value = '';
  fields['db-year-filter'].value = '2027';
  fields['db-year-filter'].dispatchEvent(new Event('change'));
  verify(data.rows.filter(row => String(row.target_year_3_5) === '2027'));
  fields['db-search'].value = 'no such commune';
  fields['db-search'].dispatchEvent(new Event('input'));
  verify([]);
  fields['db-search'].value = '';
  fields['db-year-filter'].value = 'NONE';
  fields['db-year-filter'].dispatchEvent(new Event('change'));
  verify(data.rows.filter(row => row.target_year_3_5 === null));
  fields['db-year-filter'].value = '';
  fields['db-year-filter'].dispatchEvent(new Event('change'));
  verify(data.rows);
  assert.equal(fields['db-due'].textContent, String(data.summary.roadmap_current_year));
  assert.equal(fields['db-roadmap-bars'].innerHTML, barsHtml, 'Global year counts remain unchanged');
  assert.equal(fetches, 1, 'Filtering does not send writes or further requests');
  assert.ok(quickSearchRefreshes > 5, 'Existing quick search refreshes after table updates');
}

const rows = [2026, 2026, 2027, 2028, 2029, null].map((year, index) => ({
  name: `Commune ${index}`, code: `C${index}`, target_year_3_5: year,
  roadmap_code: year === 2026 ? 'DUE' : 'ON_TRACK', roadmap_status: 'Roadmap',
  survey_complete: index === 0, is_special: index % 2 === 0,
  forms: 10, completed_forms: index === 0 ? 10 : 3,
  age_3_5_total: 30, age_3_5_attending: 27, rate_3_5_attending: 90,
  age_5_total: 10, age_5_attending: 10, rate_5_attending: 100,
  age_5_completed: 9, rate_5_completed: 90, attend_threshold: 95, complete_threshold: 85,
  five_status_code: index === 0 ? 'PASS' : 'DATA', five_status: 'Indicator',
}));
const fixture = {ok: true, rows, roadmap_loaded: 5, target_counts: {'2026': 2, '2027': 1, '2028': 1, '2029': 1},
  summary: {total_communes: 6, roadmap_current_year: 2, survey_complete: 1, five_child_indicator_pass: 1, special_difficulty: 3}};
(async () => {
  await check(fixture);
  if (process.argv[2]) await check(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
  console.log('PASS: year clicks, statistics, indicators, filters, empty year, reset, quick search and read-only requests');
})().catch(error => {console.error(error); process.exitCode = 1;});
