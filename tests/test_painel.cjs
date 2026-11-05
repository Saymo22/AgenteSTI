const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadPanel() {
  const nodes = new Map();
  const context = vm.createContext({
    console, setTimeout, clearTimeout,
    document: { getElementById: id => {
      if (!nodes.has(id)) nodes.set(id, {innerHTML: '', textContent: '', style: {}, classList: { contains: () => false }});
      return nodes.get(id);
    } },
    sessionStorage: {getItem: () => null, setItem: () => {}},
  });
  const source = fs.readFileSync(path.join(__dirname, '../sti/servidor/static/painel.js'), 'utf8');
  vm.runInContext(source.replace(/\s+init\(\);\s*$/, ''), context);
  return {run: code => vm.runInContext(code, context), nodes};
}

test('nomes com aspas não criam atributos de evento', () => {
  const {run} = loadPanel();
  const html = run(`createDeviceCard({ip:'10.2.116.33', name:'PC" onmouseover="alert(1)', os:'Windows', online:true})`);
  assert.ok(html.includes('title="PC&quot; onmouseover=&quot;alert(1)"'));
  assert.ok(!html.includes('title="PC" onmouseover="'));
});

test('histórico combina servidor e sessão e respeita a busca', () => {
  const {run, nodes} = loadPanel();
  run(`state.serverEvents = [{title:'Persistido', text:'Servidor', date:new Date(), type:'info', persisted:true}];
       state.eventLogs = [{title:'Local', text:'Sessão', date:new Date(), type:'info'}]; renderLogs();`);
  assert.ok(nodes.get('historyLogList').innerHTML.includes('Persistido'));
  assert.ok(nodes.get('historyLogList').innerHTML.includes('Local'));
  run(`state.logFilter='persistido'; renderLogs();`);
  assert.ok(nodes.get('historyLogList').innerHTML.includes('Persistido'));
  assert.ok(!nodes.get('historyLogList').innerHTML.includes('Local'));
  run(`state.logFilter='inexistente'; renderLogs();`);
  assert.ok(nodes.get('historyLogList').innerHTML.includes('Nenhum evento'));
});

test('CSV neutraliza fórmulas inclusive com espaços e tabulação', () => {
  const {run} = loadPanel();
  for (const value of ['=1+1', '  @formula', '+1', '-1', '\ttexto']) {
    assert.equal(run(`safeCsv(${JSON.stringify(value)})`), "'" + value);
  }
  assert.equal(run(`safeCsv('PC-01')`), 'PC-01');
});

test('métrica ausente é distinguida de zero e uptime tem unidade', () => {
  const {run} = loadPanel();
  assert.equal(run('clampNumber(null)'), null);
  assert.equal(run('clampNumber(0)'), 0);
  assert.equal(run('formatUptime(90061)'), '1d 1h 1min');
});

test('faixas de IP originais permanecem no painel', () => {
  const {run} = loadPanel();
  run(`state.devices = [{ip:'10.2.116.1', online:true},{ip:'10.2.117.1',online:true}]; state.currentView='116';`);
  assert.equal(run('getFilteredDevices().length'), 1);
  assert.equal(run('getFilteredDevices()[0].ip'), '10.2.116.1');
});
