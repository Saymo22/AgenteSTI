const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('modo TV mostra toda a rede e restaura os filtros ao sair', () => {
  const {run}=loadPanel();
  run(`state.devices=[{ip:'10.2.116.1',online:true,name:'PC-A'},{ip:'10.2.117.2',online:false,name:'PC-B'}];
       state.search='PC-A';state.statusFilter='online';state.currentView='116';
       state.organizationFilters.department='Informática';state.kiosk=true;`);
  assert.equal(run('getFilteredDevices().length'),2);
  run("setStatusFilter('offline')");
  assert.equal(run('state.statusFilter'),'online');
  run(`state.kiosk=false;state.organizationFilters.department='';`);
  assert.equal(run('getFilteredDevices().length'),1);
  assert.equal(run('state.search'),'PC-A');
  assert.equal(run('state.statusFilter'),'online');
});

test('modo TV move a disponibilidade e funciona mesmo sem permissão de tela cheia', async () => {
  const {run,nodes}=loadPanel();
  run(`document.body.classList.toggle=()=>{};
       switchView=view=>{state.currentView=view};updateClock=()=>{};showToast=()=>{};addEventLog=()=>{};
       document.documentElement={requestFullscreen:async()=>{throw new Error('Tela cheia bloqueada')}};
       document.getElementById('tvHealthSlot').appendChild=child=>{document.getElementById('tvHealthSlot').moved=child};
       document.getElementById('overviewSideStack').insertBefore=child=>{document.getElementById('overviewSideStack').moved=child};
       state.currentView='117';`);
  await run('toggleKiosk()');
  assert.equal(run('state.kiosk'),true);
  assert.equal(run('state.currentView'),'overview');
  assert.equal(nodes.get('tvHealthSlot').moved,nodes.get('networkHealthPanel'));
  await run('toggleKiosk()');
  assert.equal(run('state.kiosk'),false);
  assert.equal(run('state.currentView'),'117');
  assert.equal(nodes.get('overviewSideStack').moved,nodes.get('networkHealthPanel'));
});

test('relógio do modo TV acompanha o relógio do painel com data e segundos', () => {
  const {run,nodes}=loadPanel();
  run('updateClock()');
  assert.match(nodes.get('tvLiveTime').textContent,/^\d{2}:\d{2}:\d{2}$/);
  assert.equal(nodes.get('tvLiveTime').textContent,nodes.get('liveTime').textContent);
  assert.ok(Number.isFinite(Date.parse(nodes.get('tvLiveTime').dateTime)));
  assert.ok(nodes.get('tvLiveDate').textContent.length>10);
});

test('Escape sai do modo TV sem tela cheia e busca oculta não recebe foco', () => {
  const {run,nodes}=loadPanel();
  run(`state.kiosk=true;globalThis.exited=false;setKioskMode=enabled=>{exited=!enabled};
       globalThis.prevented=false;document.getElementById('searchInput').focus=()=>{throw new Error('Busca oculta recebeu foco')};
       handlePremiumKeys({key:'/',target:{tagName:'BODY'},preventDefault(){}});
       handlePremiumKeys({key:'Escape',preventDefault(){prevented=true}});`);
  assert.equal(run('exited'),true);
  assert.equal(run('prevented'),true);
});

function loadPanel() {
  const nodes = new Map();
  const context = vm.createContext({
    console, setTimeout, clearTimeout,
    document: {body:{classList:{add(){},remove(){}}},querySelectorAll:()=>[],createElement:()=>({append(){}}), getElementById: id => {
      if (!nodes.has(id)) nodes.set(id, {innerHTML: '', textContent: '', value: '', style: {}, focus(){},setAttribute(){},removeAttribute(){},replaceChildren(){},appendChild(){},classList: { contains: () => false, add() {}, remove() {}, toggle() {} }});
      return nodes.get(id);
    } },
    sessionStorage: {getItem: () => null, setItem: () => {}},
  });
  const source = fs.readFileSync(path.join(__dirname, '../sti/servidor/static/painel.js'), 'utf8');
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../sti/servidor/static/som.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../sti/servidor/static/releases.js'), 'utf8'), context);
  vm.runInContext(source.replace(/\s+init\(\);\s*$/, ''), context);
  return {run: code => vm.runInContext(code, context), nodes};
}

test('máquinas já offline não criam notificações nem contador vazio', () => {
  const {run,nodes}=loadPanel();
  run(`document.getElementById('notificationPanel').hidden=true;addEventLog=()=>{};
       processStatusChanges([{ip:'10.2.116.1',online:false},{ip:'10.2.117.2',online:false}]);`);
  assert.equal(run('state.notifications.length'),0);
  assert.equal(nodes.get('notificationBadge').hidden,true);
  assert.equal(nodes.get('notificationBadge').textContent,'0');
  assert.equal(nodes.get('notificationSummary').textContent,'Nenhuma notificação');
});

test('sino conta quedas e recuperações não lidas e abrir marca como lidas', () => {
  const {run,nodes}=loadPanel();
  run(`document.getElementById('notificationPanel').hidden=true;addEventLog=()=>{};
       processStatusChanges([{device_id:'pc',ip:'10.2.116.1',online:true}]);
       processStatusChanges([{device_id:'pc',ip:'10.2.116.1',online:false}]);
       processStatusChanges([{device_id:'pc',ip:'10.2.117.1',online:true}]);`);
  assert.equal(nodes.get('notificationBadge').textContent,'2');
  assert.equal(nodes.get('notificationBadge').hidden,false);
  run('toggleNotifications()');
  assert.equal(nodes.get('notificationBadge').hidden,true);
  assert.equal(run('state.notifications.length'),2);
  assert.equal(nodes.get('notificationSummary').textContent,'2 notificações • 0 não lidas');
  run(`processStatusChanges([{device_id:'pc',ip:'10.2.117.1',online:false}]);`);
  assert.equal(nodes.get('notificationBadge').hidden,true); // Alerta já visível na central aberta.
  run(`toggleNotifications();processStatusChanges([{device_id:'pc',ip:'10.2.117.1',online:true}]);`);
  assert.equal(nodes.get('notificationBadge').textContent,'1');
});

test('limpar zera lista e contador e atualização sem mudança não recria alertas', () => {
  const {run,nodes}=loadPanel();
  run(`document.getElementById('notificationPanel').hidden=true;addEventLog=()=>{};showToast=()=>{};
       processStatusChanges([{ip:'10.2.116.1',online:true}]);
       processStatusChanges([{ip:'10.2.116.1',online:false}]);clearNotifications();
       processStatusChanges([{ip:'10.2.116.1',online:false}]);`);
  assert.equal(run('state.notifications.length'),0);
  assert.equal(nodes.get('notificationBadge').hidden,true);
  assert.equal(nodes.get('notificationSummary').textContent,'Nenhuma notificação');
  run(`processStatusChanges([{ip:'10.2.116.1',online:true}]);`);
  assert.equal(nodes.get('notificationBadge').textContent,'1');
});

function mockAudio(run) {
  run(`globalThis.played=[];globalThis.stopped=0;
       globalThis.window={AudioContext:function(){}};
       const parameter=()=>({setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){}});
       state.audioCtx={state:'running',currentTime:0,destination:{},decodeAudioData:async()=>({duration:25}),
         createGain:()=>({gain:parameter(),connect(){},disconnect(){}}),
         createBufferSource:()=>({connect(){},disconnect(){},start(...args){played.push(args)},stop(){stopped++}})};
       showToast=()=>{};`);
}

test('seleção de MP3 decodifica antes de salvar e rejeita arquivos inválidos', async () => {
  const {run,nodes}=loadPanel();mockAudio(run);
  run(`globalThis.savedFiles=[];soundStore=async(operation,file)=>{savedFiles.push(file.name)};
       globalThis.file={name:'meu-alerta.mp3',size:2048,arrayBuffer:async()=>new ArrayBuffer(8)};`);
  await run(`chooseAlertSound({target:{files:[file],value:'file'}})`);
  assert.equal(run('state.soundName'),'meu-alerta.mp3');
  assert.equal(run('savedFiles.length'),1);
  await run(`chooseAlertSound({target:{files:[{...file,name:'arquivo.exe'}],value:'file'}})`);
  assert.equal(run('state.soundName'),'meu-alerta.mp3');
  assert.equal(run('savedFiles.length'),1);
  await run(`chooseAlertSound({target:{files:[{...file,size:11*1024*1024}],value:'file'}})`);
  assert.ok(nodes.get('alertSoundStatus').textContent.includes('10 MB'));
  run(`state.audioCtx.decodeAudioData=async()=>{throw new Error('Corrompido')};`);
  await run(`chooseAlertSound({target:{files:[file],value:'file'}})`);
  assert.equal(run('state.soundName'),'meu-alerta.mp3');
  assert.equal(run('savedFiles.length'),1);
});

test('restaura áudio e volume locais mantendo ativação explícita após recarregar', async () => {
  const {run,nodes}=loadPanel();mockAudio(run);
  run(`localStorage={getItem:()=> '35'};soundStore=async()=>({name:'salvo.mp3',size:2000,arrayBuffer:async()=>new ArrayBuffer(8)});`);
  await run('initSoundSettings()');
  assert.equal(run('state.soundName'),'salvo.mp3');
  assert.equal(run('state.soundVolume'),35);
  assert.equal(run('state.soundEnabled'),false);
  assert.equal(nodes.get('btnToggleAlertSound').textContent,'Ativar alertas sonoros');
  assert.equal(run('played.length'),0);
});

test('som personalizado respeita ativação, teste, limite de duração e desligamento', async () => {
  const {run}=loadPanel();mockAudio(run);
  run(`state.soundBuffer={duration:25};playAlert();`);
  assert.equal(run('played.length'),0);
  await run('testAlertSound()');
  assert.equal(run('played[0][2]'),10);
  assert.equal(run('state.soundEnabled'),false);
  run('stopAlertSound()');
  await run('toggleSound()');
  assert.equal(run('state.soundEnabled'),true);
  assert.equal(run('state.soundSources.length'),1);
  await run('toggleSound()');
  assert.equal(run('state.soundEnabled'),false);
  assert.equal(run('state.soundSources.length'),0);
});

test('falha no armazenamento mantém áudio na sessão e permite usar o som padrão', async () => {
  const {run,nodes}=loadPanel();mockAudio(run);
  run(`soundStore=async()=>{throw new Error('Sem espaço')};globalThis.file={name:'alerta.mp3',size:1000,arrayBuffer:async()=>new ArrayBuffer(8)};`);
  await run(`chooseAlertSound({target:{files:[file],value:'file'}})`);
  assert.equal(run('state.soundName'),'alerta.mp3');
  assert.ok(nodes.get('alertSoundStatus').textContent.includes('sessão'));
  await run('resetAlertSound()');
  assert.equal(run('state.soundBuffer'),null);
  assert.equal(run('state.soundName'),'');
});

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

test('UUID distingue equipamentos no mesmo último IP e acompanha mudança de endereço', () => {
  const {run,nodes}=loadPanel();
  run(`state.devices=[{device_id:'id-antigo',ip:'10.2.116.33',name:'ANTIGO',address_active:false,organization:{department:'RH'}},
       {device_id:'id-atual',ip:'10.2.116.33',name:'ATUAL',organization:{department:'TI'}}];
       openModal('id-antigo');`);
  assert.equal(nodes.get('modalName').textContent,'ANTIGO');
  assert.ok(nodes.get('modalIpField').textContent.includes('último IP'));
  assert.equal(run('state.organizationEditor.ip'),'id-antigo');
  run(`openModal('id-atual');state.organizationEditor.dirty=true;document.getElementById('organizationDepartment').value='Financeiro';state.devices[1].ip='10.2.118.45';openModal('id-atual',true);`);
  assert.equal(nodes.get('modalIpField').textContent,'10.2.118.45');
  assert.equal(nodes.get('organizationDepartment').value,'Financeiro');
  assert.equal(run('state.organizationEditor.ip'),'id-atual');
});

test('busca encontra MAC, série e UUID sem misturar cadastros por IP', () => {
  const {run}=loadPanel();
  run(`state.devices=[{device_id:'uuid-estavel',ip:'10.2.116.33',serial_number:'ABC-123',mac_addresses:['02:11:22:33:44:55']},{device_id:'outro',ip:'10.2.116.33'}];`);
  for(const query of ['uuid-estavel','abc-123','02:11:22:33:44:55']){
    run(`state.search=${JSON.stringify(query)};`);
    assert.equal(run('getFilteredDevices().length'),1);
    assert.equal(run('getFilteredDevices()[0].device_id'),'uuid-estavel');
  }
});

test('salvar cadastro usa UUID e mantém outro equipamento do mesmo IP intacto', async () => {
  const {run}=loadPanel();
  run(`state.devices=[{device_id:'um',ip:'10.2.116.33',organization:{department:'RH'}},{device_id:'dois',ip:'10.2.116.33',organization:{department:'TI'}}];
       openModal('um');showToast=()=>{};renderAll=()=>{};loadEvents=()=>{};
       checkedFetch=async(url,options)=>{globalThis.savedURL=url;return {json:async()=>({organization:{department:'Novo',updated_at:'revision'}})}};`);
  await run('saveOrganization({preventDefault(){}})');
  assert.equal(run('savedURL'),'/api/devices/um/organization');
  assert.equal(run('state.devices[0].organization.department'),'Novo');
  assert.equal(run('state.devices[1].organization.department'),'TI');
});

test('comando inclui a identidade esperada e histórico escapa conteúdo recebido', async () => {
  const {run,nodes}=loadPanel();
  run(`state.currentDevice={device_id:'uuid-do-alvo',ip:'10.2.116.33'};showToast=()=>{};addEventLog=()=>{};closeModal=()=>{};
       checkedFetch=async(url,options)=>{globalThis.commandPayload=JSON.parse(options.body);return {json:async()=>({command_id:'job'})}};`);
  await run(`postCommand('msg','teste')`);
  assert.equal(run('commandPayload.device_id'),'uuid-do-alvo');
  run(`checkedFetch=async()=>({json:async()=>({events:[{timestamp:'2026-11-10T10:00:00',ip:'10.2.116.33',status:'ip_alterado',description:'<img src=x onerror=alert(1)>'}]})});`);
  await run('loadDeviceHistory()');
  assert.ok(nodes.get('deviceIdentityHistory').innerHTML.includes('&lt;img'));
  assert.ok(!nodes.get('deviceIdentityHistory').innerHTML.includes('<img'));
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
  assert.equal(nodes.get('btnRemap').disabled,true);
  assert.ok(nodes.get('btnScan').innerHTML.includes('Escaneando'));
  assert.ok(nodes.get('btnScan').title.includes('20 de 100'));
  run('updateScanState({scanning:false});');
  assert.equal(nodes.get('btnScan').disabled,false);
  assert.equal(nodes.get('btnRemap').disabled,false);
  assert.equal(nodes.get('btnScan').innerHTML,'Escanear rede');
});

test('cancelar remapeamento mostra contagens e não envia pedido de limpeza', async () => {
  const {run,nodes}=loadPanel();
  run(`globalThis.requests=[];checkedFetch=async(url,options)=>{requests.push(options?.method || 'GET');return {json:async()=>({network:'10.2.116.0/22',removed:110,offline_removed:90,kept:20})}};
       globalThis.confirmation='';globalThis.confirm=text=>{confirmation=text;return false};showToast=()=>{};`);
  await run('remapNetwork()');
  assert.equal(run('requests.length'),1);
  assert.ok(run('confirmation').includes('110'));
  assert.ok(run('confirmation').includes('20'));
  assert.equal(nodes.get('btnRemap').disabled,false);
});

test('remapeamento confirmado envia escopo fixo e acompanha o estado do servidor', async () => {
  const {run,nodes}=loadPanel();
  run(`globalThis.payload=null;globalThis.confirm=()=>true;showToast=()=>{};loadDevices=async()=>{};
       checkedFetch=async(url,options)=>({json:async()=>{if(options){payload=JSON.parse(options.body);return {scan:{scanning:true,remapping:true,last_remap:{id:'job',status:'queued',removed:0}}}}return {network:'10.2.116.0/22',removed:10,offline_removed:8,kept:5}}});`);
  await run('remapNetwork()');
  assert.equal(run('payload.confirm'),true);
  assert.equal(nodes.get('btnRemap').disabled,true);
  assert.ok(nodes.get('btnRemap').innerHTML.includes('Remapeando'));
  run(`updateScanState({scanning:false,last_remap:{id:'job',status:'completed',removed:10}});`);
  assert.equal(nodes.get('btnRemap').disabled,false);
  assert.ok(nodes.get('remapStatus').textContent.includes('10 registros'));
});

test('remapeamento reinicia detecção dos IPs sem agente sem criar notificações falsas', () => {
  const {run}=loadPanel();
  run(`state.devices=[{ip:'10.2.116.1',online:false,identification_source:'dns',hw:{}},{device_id:'agente',ip:'10.2.116.2',online:true,identification_source:'agent'}];
       state.previousStatus={'10.2.116.1':false,agente:true};state.notifications=[];addEventLog=()=>{};
       updateScanState({discovery_generation:0});updateScanState({discovery_generation:1});
       processStatusChanges([{ip:'10.2.116.1',online:true},{device_id:'agente',ip:'10.2.116.2',online:true}]);`);
  assert.equal(run('state.notifications.length'),0);
  assert.equal(run('state.previousStatus.agente'),true);
});

test('lista de releases mantém seleção válida quando a versão antiga sai da lista', () => {
  const {run,nodes}=loadPanel();
  run(`releaseState.releases=[{version:'3.5.1',installer_url:'/new'},{version:'3.5.0',installer_url:'/previous'}];
       releaseState.policy={version:'3.4.3',scope:'all',device_ids:[]};
       document.getElementById('releaseVersion').value='3.4.3';renderReleaseSettings();`);
  assert.equal(nodes.get('releaseVersion').value,'3.5.1');
  assert.equal((nodes.get('releaseList').innerHTML.match(/class="release-entry"/g)||[]).length,2);
  assert.match(nodes.get('releaseActivePolicy').textContent,/3\.4\.3/);
  run(`document.getElementById('releaseVersion').value='3.5.0';renderReleaseSettings();`);
  assert.equal(nodes.get('releaseVersion').value,'3.5.0');
});

test('controle de versões distingue versão atual, inicialização manual, grupo e recuperação', () => {
  const {run}=loadPanel();
  run(`releaseState.policy={version:'3.4.0',scope:'selected',device_ids:['teste']};`);
  assert.equal(run(`releaseDeviceStatus({agent_version:'3.4.0'},{}).key`),'current');
  assert.equal(run(`releaseDeviceStatus({agent_version:'3.3.0'},{}).key`),'manual');
  assert.equal(run(`releaseDeviceStatus({device_id:'outro',agent_version:'3.3.0'},{supported:true}).label`),'Fora do grupo de teste');
  assert.equal(run(`releaseDeviceStatus({agent_version:'3.4.0'},{status:'rolled_back'}).key`),'failed');
  assert.equal(run(`compareAgentVersions('3.10.0','3.9.0')`),1);
  assert.equal(run(`compareAgentVersions('legado','3.4.0')`),null);
});


test('plataformas distinguem iOS, macOS, Android e Linux sem confundir BIOS', () => {
  const {run}=loadPanel();
  for(const [text, expected] of [['iOS 18','iOS'],['iPadOS 18','iOS'],['macOS Sonoma','macOS'],['Linux Android 14','Android'],['Ubuntu 24','Linux'],['Windows 11','Windows']]) {
    assert.equal(run('getOSInfo('+JSON.stringify(text)+').name'),expected);
  }
  assert.equal(run("getOSInfo('BIOS').cls"),'os-unk');
});

test('ícone usa agente antes do cadastro e identifica origem manual', () => {
  const {run}=loadPanel();
  assert.equal(run("getDevicePlatform({os:'Windows 11',agent_version:'3.4.2',organization:{platform:'Android'}}).name"),'Windows');
  assert.equal(run("getDevicePlatform({os:'Desconhecido',organization:{platform:'iOS'}}).source"),'manual');
  const html=run("createDeviceCard({ip:'10.2.116.20',organization:{platform:'Android',display_name:'Celular da recepção'}})");
  assert.ok(html.includes('os-android'));assert.ok(html.includes('Cadastrado por você'));assert.ok(html.includes('Celular da recepção'));
});

test('nomes de rede geram sugestões prováveis e IP sozinho mantém sistema desconhecido', () => {
  const {run}=loadPanel();
  for(const [name, expected] of [['iPhone-de-Ana','iOS'],['android-abc','Android'],['debian-server','Linux'],['MacBook-da-Ana','macOS'],['windows-pc','Windows']]) {
    assert.equal(run('getDevicePlatform({name:'+JSON.stringify(name)+'}).name'),expected);
    assert.equal(run('getDevicePlatform({name:'+JSON.stringify(name)+'}).source'),'dns');
  }
  const unknown=run("getDevicePlatform({ip:'10.2.116.123',name:'host-123'})");
  assert.equal(unknown.source,'unknown');assert.equal(unknown.name,'Não identificado');
  assert.ok(!run("createDeviceCard({ip:'10.2.116.123'})").includes('r="10"></circle><path d="M9.1'));
});

test('nome cadastrado é escapado e participa da busca junto com o sistema', () => {
  const {run}=loadPanel();
  run("state.devices=[{ip:'10.2.116.1',organization:{display_name:'Celular Recepção',platform:'iOS'}}]");
  for(const search of ['recepcao','ios']) {run('state.search='+JSON.stringify(search));assert.equal(run('getFilteredDevices().length'),1);}
  const html=run("createDeviceCard({organization:{display_name:'<img src=x onerror=alert(1)>',platform:'Android'}})");
  assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
});

test('cadastro de identificação preserva rascunho e envia nome e plataforma', async () => {
  const {run,nodes}=loadPanel();
  run("state.devices=[{ip:'10.2.116.9',organization:{display_name:'Antigo',platform:'Linux'}}];openModal('10.2.116.9');state.organizationEditor.dirty=true;document.getElementById('organizationDisplayName').value='Novo';document.getElementById('organizationPlatform').value='Android';openModal('10.2.116.9',true)");
  assert.equal(nodes.get('organizationDisplayName').value,'Novo');assert.equal(nodes.get('organizationPlatform').value,'Android');
  run("showToast=()=>{};renderAll=()=>{};loadEvents=()=>{};checkedFetch=async(url,options)=>{globalThis.profilePayload=JSON.parse(options.body);return {json:async()=>({organization:{...profilePayload,updated_at:'new'}})}}");
  await run('saveOrganization({preventDefault(){}})');
  assert.equal(run('profilePayload.platform'),'Android');assert.equal(run('profilePayload.display_name'),'Novo');
});


test('atualização offline não fica apresentada como instalação em andamento', () => {
 const {run}=loadPanel();
 for(const status of ['downloading','installing','updated']) {
   assert.equal(run('releaseDeviceStatus({agent_online:false,agent_version:"3.4.2"},{status:'+JSON.stringify(status)+',supported:true}).key'),'unconfirmed');
 }
 assert.equal(run('releaseDeviceStatus({agent_online:true},{status:"installing"}).key'),'progress');
 assert.equal(run('releaseDeviceStatus({agent_online:false},{status:"rolled_back"}).key'),'failed');
});

test('tabela separa último resultado de confirmação atual e permite filtro sem comunicação', () => {
 const {run,nodes}=loadPanel();
 run('state.devices=[{device_id:"test",ip:"10.2.116.20",agent_online:false,agent_version:"3.4.2"}];releaseState.devices=[{device_id:"test",supported:true,status:"installing",result:"Último evento"}];document.getElementById("releaseStatusFilter").value="unconfirmed";renderReleaseDevices()');
 const html=nodes.get('releaseDevices').innerHTML;
 assert.ok(html.includes('Atualização sem confirmação recente'));assert.ok(html.includes('Última versão informada'));assert.ok(html.includes('Último resultado:'));assert.ok(html.includes('Configurada no último envio'));
 assert.ok(!html.includes('Instalando atualização'));
});
