const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadPanel() {
  const nodes = new Map();
  const context = vm.createContext({
    console, setTimeout, clearTimeout,
    document: {body:{classList:{add(){},remove(){}}},querySelectorAll:()=>[], getElementById: id => {
      if (!nodes.has(id)) nodes.set(id, {innerHTML: '', textContent: '', value: '', style: {}, focus(){},setAttribute(){},removeAttribute(){},classList: { contains: () => false, add() {}, remove() {}, toggle() {} }});
      return nodes.get(id);
    } },
    sessionStorage: {getItem: () => null, setItem: () => {}},
  });
  const source = fs.readFileSync(path.join(__dirname, '../sti/servidor/static/painel.js'), 'utf8');
  vm.runInContext(source.replace(/\s+init\(\);\s*$/, ''), context);
  return {run: code => vm.runInContext(code, context), nodes};
}

test('cartões distinguem ping, agente, nomes provisórios e latência ausente', () => {
  const {run} = loadPanel();
  const html = run(`createDeviceCard({ip:'10.2.117.33',name:'host-33',os:'Desconhecido',user:'Não informado',online:true,latency:null,identification_source:'network'})`);
  assert.ok(html.includes('Dispositivo sem nome'));
  assert.ok(html.includes('10.2.117.33'));
  assert.ok(html.includes('Identificação pendente'));
  assert.ok(html.includes('Aguardando agente'));
  assert.ok(html.includes('Não medida'));
  assert.ok(!html.includes('0 ms'));
  assert.equal(run(`getDeviceIdentity({online:true,latency:0}).latency`), '0 ms');
  assert.equal(run(`getOSInfo('Linux Android 14').name`), 'Android');
  assert.equal(run(`getDeviceIdentity({name:'host-33',agent_online:true}).name`), 'host-33');
  assert.equal(run(`calcAvgLatency([{online:true,latency:null},{online:true,latency:40}])`), 40);
  assert.equal(run(`calcAvgLatency([{online:true,latency:null}])`), null);
});

test('pop-up mostra dados históricos e orienta quando não há agente', () => {
  const {run,nodes} = loadPanel();
  run(`state.devices=[{ip:'10.2.116.33',name:'PC-01',os:'Windows 11',user:'EMPRESA\\\\ana',online:true,agent_online:false,agent_version:'3.2.0',latency:null,hw:{cpu:75}}];openModal('10.2.116.33');`);
  assert.equal(nodes.get('modalLatencyField').textContent,'Não medida');
  assert.equal(nodes.get('modalAgentValue').textContent,'Sem comunicação');
  assert.equal(nodes.get('modalUserLabel').textContent,'Último usuário informado');
  assert.ok(nodes.get('modalIdentificationNotice').textContent.includes('último envio'));
  assert.equal(nodes.get('modalCpuValue').textContent,'Aguardando');
  run(`state.devices[0].agent_online=true;state.devices[0].user='';openModal('10.2.116.33',true);`);
  assert.equal(nodes.get('modalUserField').textContent,'Nenhuma sessão informada');
  assert.equal(nodes.get('modalUserLabel').textContent,'Usuário conectado');
});

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

test('busca encontra setor, sala e responsável sem depender de acentos', () => {
  const {run} = loadPanel();
  run(`state.devices = [{ip:'10.2.116.33',organization:{department:'Administração',room:'Sala 204',responsible:'João Silva'}}];`);
  for (const search of ['administracao','204','joao silva']) {
    run(`state.search=${JSON.stringify(search)};`);
    assert.equal(run('getFilteredDevices().length'), 1);
  }
});

test('filtros combinam localização, responsável e faixa de IP', () => {
  const {run} = loadPanel();
  run(`state.devices = [
    {ip:'10.2.116.1', organization:{department:'TI',room:'204',responsible:'Ana'}},
    {ip:'10.2.117.1', organization:{department:'TI',room:'204',responsible:'Ana'}},
    {ip:'10.2.116.2', organization:{department:'TI',room:'205',responsible:'Ana'}}];
    state.currentView='116'; state.organizationFilters={department:'value:TI',room:'value:204',responsible:'value:Ana'};`);
  assert.equal(run('getFilteredDevices().length'), 1);
  assert.equal(run('getFilteredDevices()[0].ip'), '10.2.116.1');
  assert.equal(run(`matchesOrganizationFilter('', 'unassigned')`), true);
  assert.equal(run(`matchesOrganizationFilter('unassigned', 'value:unassigned')`), true);
});

test('agrupamento inclui máquinas sem cadastro e metadados são escapados', () => {
  const {run} = loadPanel();
  run(`state.devices=[{ip:'10.2.116.1', organization:{department:'TI'}},{ip:'10.2.116.2',organization:{department:'ti'}},{ip:'10.2.116.3'}];`);
  assert.equal(run(`groupDevices(state.devices,'department').length`), 2);
  assert.equal(run(`groupDevices(state.devices,'department').find(group=>group.label==='TI').devices.length`), 2);
  const html = run(`createDeviceCard({ip:'10.2.116.1',organization:{department:'<script>teste</script>',responsible:'"<img>'}})`);
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<img>'));
});

test('atualização periódica preserva os campos que o administrador está editando', () => {
  const {run, nodes} = loadPanel();
  run(`state.devices=[{ip:'10.2.116.1',organization:{department:'TI',updated_at:'old'}}];
       openModal('10.2.116.1'); state.organizationEditor.dirty=true;
       document.getElementById('organizationDepartment').value='Financeiro';
       state.devices[0].organization={department:'Outro',updated_at:'new'};
       openModal('10.2.116.1',true);`);
  assert.equal(nodes.get('organizationDepartment').value, 'Financeiro');
  assert.equal(run('state.organizationEditor.revision'), 'old');
});

test('CSV de inventário inclui setor, sala e responsável', () => {
  const {run} = loadPanel();
  run(`globalThis.Blob=class { constructor(parts){globalThis.exportedCSV=parts.join('');} };
       globalThis.URL={createObjectURL:()=>'',revokeObjectURL:()=>{}};
       document.createElement=()=>({click(){}}); showToast=()=>{}; addEventLog=()=>{};
       state.devices=[{ip:'10.2.116.1',organization:{department:'TI',room:'204',responsible:'Ana'}}]; exportCSV();`);
  const csv = run('exportedCSV');
  assert.ok(csv.includes('"Setor","Sala","Responsável"'));
  assert.ok(csv.includes('"TI","204","Ana"'));
});

test('falha ao salvar mantém campos e permite tentar novamente', async () => {
  const {run, nodes} = loadPanel();
  run(`state.devices=[{ip:'10.2.116.1',organization:{department:'TI',updated_at:'rev'}}];
       openModal('10.2.116.1'); state.organizationEditor.dirty=true;
       document.getElementById('organizationDepartment').value='Financeiro';
       checkedFetch=async()=>{throw new Error('Falha de conexão')}; showToast=()=>{};`);
  await run('saveOrganization({preventDefault(){}})');
  assert.equal(nodes.get('organizationDepartment').value, 'Financeiro');
  assert.equal(nodes.get('organizationSaveStatus').textContent, 'Falha de conexão');
  assert.equal(run('state.organizationEditor.dirty'), true);
  assert.equal(run('state.organizationEditor.saving'), false);
  assert.equal(nodes.get('organizationFieldset').disabled, false);
});

test('opções de filtro escapam aspas e preservam a seleção atual', () => {
  const {run, nodes} = loadPanel();
  run(`state.devices=[{organization:{department:'TI" autofocus onfocus="teste'}}];
       state.organizationFilters.room='value:204'; updateOrganizationFilters();`);
  assert.ok(nodes.get('filterDepartment').innerHTML.includes('value:TI&quot; autofocus onfocus=&quot;teste'));
  assert.equal(nodes.get('filterRoom').value, 'value:204');
});

test('ícones locais usam uma lista permitida e não interpolam nomes arbitrários', () => {
  const {run}=loadPanel();
  assert.ok(run("uiIcon('cpu')").includes('/static/icons/sti.svg#cpu'));
  const icon=run(`uiIcon('" onload="alert(1)')`);
  assert.ok(icon.includes('/static/icons/sti.svg#monitor'));
  assert.ok(!icon.includes('onload'));
});

test('filtros de disponibilidade combinam com as faixas originais', () => {
  const {run}=loadPanel();
  run(`state.devices=[{ip:'10.2.116.1',online:true,latency:5},{ip:'10.2.116.2',online:false},{ip:'10.2.117.1',online:true,latency:150}];state.statusFilter='offline';`);
  assert.equal(run('getFilteredDevices()[0].ip'),'10.2.116.2');
  run(`state.statusFilter='attention';`);
  assert.equal(run('getFilteredDevices()[0].ip'),'10.2.117.1');
  run(`state.currentView='116';`);
  assert.equal(run('getFilteredDevices().length'),0);
});

test('contadores terminam no valor real e respeitam movimento reduzido', () => {
  const {run,nodes}=loadPanel();
  run(`globalThis.frames=[];globalThis.performance={now:()=>0};globalThis.requestAnimationFrame=callback=>{frames.push(callback);return frames.length;};animateMetric('metricTotal',42);frames.shift()(650);`);
  assert.equal(nodes.get('metricTotal').textContent,'42');
  run(`globalThis.window={matchMedia:()=>({matches:true})};globalThis.requestAnimationFrame=()=>{throw new Error('Não deve animar')};animateMetric('metricTotal',12);`);
  assert.equal(nodes.get('metricTotal').textContent,'12');
});

test('indicador de escaneamento usa o estado real e restaura o botão', () => {
  const {run,nodes}=loadPanel();
  run(`document.getElementById('btnScan').innerHTML='Escanear rede';updateScanState({scanning:true,progress:20,total:100});`);
  assert.equal(nodes.get('btnScan').disabled,true);
  assert.ok(nodes.get('btnScan').innerHTML.includes('Escaneando'));
  assert.ok(nodes.get('btnScan').title.includes('20 de 100'));
  run('updateScanState({scanning:false});');
  assert.equal(nodes.get('btnScan').disabled,false);
  assert.equal(nodes.get('btnScan').innerHTML,'Escanear rede');
});
