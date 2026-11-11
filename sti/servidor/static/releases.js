const releaseState = {releases: [], policy: null, devices: [], loading: false, loaded: false, editing: false, reference: '3.4.0'};

function initReleaseControls() {
  document.getElementById('reloadReleases').addEventListener('click', loadReleases);
  document.getElementById('uploadReleaseForm').addEventListener('submit', uploadRelease);
  document.getElementById('releasePolicyForm').addEventListener('submit', activateRelease);
  document.getElementById('pauseReleaseButton').addEventListener('click', pauseRelease);
  document.getElementById('releaseStatusFilter').addEventListener('change', renderReleaseDevices);
  document.getElementById('releasePolicyForm').addEventListener('input', () => { releaseState.editing = true; });
  document.getElementById('releaseScope').addEventListener('change', () => {
    releaseState.editing = true;
    document.getElementById('releaseTargetsLabel').hidden = document.getElementById('releaseScope').value !== 'selected';
  });
  setInterval(() => { if (state.currentView === 'updates') loadReleases(); }, 15000);
}

async function loadReleases() {
  if (releaseState.loading) return;
  releaseState.loading = true;
  try {
    const response = await checkedFetch('/api/releases');
    const data = await response.json();
    releaseState.releases = data.releases || [];
    releaseState.policy = data.policy;
    releaseState.devices = data.devices || [];
    releaseState.reference = data.build_version || '3.4.0';
    renderReleaseSettings();
    renderReleaseDevices();
    document.getElementById('releaseServerClock').textContent = `Horário do servidor agora ${data.server_time}. Deixe os dois horários vazios para distribuir a qualquer hora.`;
    releaseState.loaded = true;
  } catch (error) {
    document.getElementById('releaseFeedback').textContent = error.message;
  } finally { releaseState.loading = false; }
}

function renderReleaseSettings() {
  const version = document.getElementById('releaseVersion');
  const selected = version.value;
  version.innerHTML = '<option value="">Selecione uma release</option>' + releaseState.releases.map(item => `<option value="${escapeHtml(item.version)}">${escapeHtml(item.version)}</option>`).join('');
  version.value = selected || releaseState.policy?.version || releaseState.releases[0]?.version || '';
  const targets = document.getElementById('releaseTargets');
  const selectedIds = new Set(releaseState.editing ? [...targets.selectedOptions].map(item => item.value) : releaseState.policy?.device_ids || []);
  targets.innerHTML = state.devices.filter(device => device.device_id).map(device => `<option value="${escapeHtml(device.device_id)}"${selectedIds.has(device.device_id) ? ' selected' : ''}>${escapeHtml(device.name || device.ip)} · ${escapeHtml(device.ip)}</option>`).join('');
  if (!releaseState.editing) {
    releaseState.draftPolicyId = releaseState.policy?.rollout_id || '';
    document.getElementById('releaseScope').value = releaseState.policy?.scope || 'all';
    document.getElementById('releaseWindowStart').value = releaseState.policy?.window_start || '';
    document.getElementById('releaseWindowEnd').value = releaseState.policy?.window_end || '';
  }
  document.getElementById('releaseTargetsLabel').hidden = document.getElementById('releaseScope').value !== 'selected';
  document.getElementById('pauseReleaseButton').disabled = !releaseState.policy;
  document.getElementById('activateReleaseButton').disabled = !releaseState.releases.length;
  document.getElementById('releaseActivePolicy').textContent = releaseState.policy
    ? `Versão ${releaseState.policy.version} liberada ${releaseState.policy.scope === 'selected' ? 'para o grupo de teste' : 'para todos os agentes compatíveis'}.`
    : 'Nenhuma release liberada.';
  document.getElementById('releaseList').innerHTML = releaseState.releases.map(item => `<div class="release-entry"><div><strong>v${escapeHtml(item.version)}</strong><a href="${escapeHtml(item.installer_url)}">Baixar instalador</a></div>${item.notes ? `<details><summary>Notas da versão</summary><p>${escapeHtml(item.notes)}</p></details>` : ''}</div>`).join('') || '<p class="release-help">Envie a primeira release para disponibilizar o instalador.</p>';
}

function compareAgentVersions(first, second) {
  const parse = value => /^\d+\.\d+\.\d+$/.test(String(value || '')) ? String(value).split('.').map(Number) : null;
  const a = parse(first), b = parse(second);
  if (!a || !b) return null;
  for (let index = 0; index < 3; index++) {
    if (a[index] !== b[index]) return a[index] > b[index] ? 1 : -1;
  }
  return 0;
}

function releaseDeviceStatus(device, report = {}) {
  if (['failed', 'rolled_back'].includes(report.status)) return {key: 'failed', label: report.status === 'rolled_back' ? 'Versão anterior recuperada' : 'Falha na atualização'};
  if (['downloading', 'installing'].includes(report.status)) return {key: 'progress', label: report.status === 'downloading' ? 'Baixando atualização' : 'Instalando atualização'};
  const expected = releaseState.policy?.version || releaseState.reference;
  const comparison = compareAgentVersions(device.agent_version, expected);
  if (comparison !== null && comparison >= 0) return {key: 'current', label: comparison === 0 ? 'Atualizado' : 'Versão superior'};
  if (!report.supported) return {key: 'manual', label: 'Instalador inicial necessário'};
  if (releaseState.policy?.scope === 'selected' && !releaseState.policy.device_ids.includes(device.device_id)) return {key: 'pending', label: 'Fora do grupo de teste'};
  return {key: 'pending', label: releaseState.policy ? 'Atualização disponível' : 'Aguardando liberação'};
}

function renderReleaseDevices() {
  if (!document.getElementById('releaseDevices')) return;
  const reports = new Map(releaseState.devices.map(item => [item.device_id, item]));
  const agents = state.devices.filter(device => device.device_id || device.identification_source === 'agent' || device.agent_version || Object.keys(device.hw || {}).length);
  const filter = document.getElementById('releaseStatusFilter').value || 'all';
  const rows = agents.map(device => {
    const report = reports.get(device.device_id) || {};
    return {device, report, status: releaseDeviceStatus(device, report)};
  });
  const current = rows.filter(row => row.status.key === 'current').length;
  document.getElementById('releaseVersionSummary').textContent = `${agents.length} agentes • ${current} atualizados • referência ${releaseState.policy?.version || releaseState.reference}`;
  document.getElementById('releaseDevices').innerHTML = rows.filter(row => filter === 'all' || row.status.key === filter).map(({device, report, status}) => `<tr><td><strong>${escapeHtml(device.name || 'Dispositivo')}</strong><small>${escapeHtml(device.ip)}${device.agent_online ? '' : ' · sem comunicação recente'}</small></td><td class="mono">${escapeHtml(device.agent_version || 'Não informada')}</td><td><span class="release-status ${status.key}">${escapeHtml(status.label)}</span>${report.result ? `<small>${escapeHtml(report.result)}</small>` : ''}</td><td>${report.supported ? 'Habilitada pelo instalador' : 'Instale o pacote V3.4 ou superior'}</td></tr>`).join('') || '<tr><td colspan="4">Nenhum agente encontrado para esse filtro.</td></tr>';
}

async function uploadRelease(event) {
  event.preventDefault();
  const file = document.getElementById('releaseBundle').files[0];
  if (!file) return;
  const form = new FormData();
  form.append('release', file);
  const button = document.getElementById('uploadReleaseButton');
  button.disabled = true;
  document.getElementById('releaseFeedback').textContent = 'Enviando e verificando a assinatura da release…';
  try {
    const response = await checkedFetch('/api/releases', {method: 'POST', body: form});
    const data = await response.json();
    document.getElementById('releaseBundle').value = '';
    releaseState.editing = true;
    await loadReleases();
    document.getElementById('releaseVersion').value = data.version;
    document.getElementById('releaseFeedback').textContent = `Release ${data.version} publicada. Escolha os equipamentos e libere a distribuição.`;
  } catch (error) { document.getElementById('releaseFeedback').textContent = error.message; }
  finally { button.disabled = false; }
}

async function activateRelease(event) {
  event.preventDefault();
  const payload = {version: document.getElementById('releaseVersion').value,
    expected_rollout_id: releaseState.draftPolicyId || '',
    scope: document.getElementById('releaseScope').value,
    device_ids: [...document.getElementById('releaseTargets').selectedOptions].map(option => option.value),
    window_start: document.getElementById('releaseWindowStart').value, window_end: document.getElementById('releaseWindowEnd').value};
  const button = document.getElementById('activateReleaseButton');
  button.disabled = true;
  try {
    await checkedFetch('/api/releases/activate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    releaseState.editing = false;
    await loadReleases();
    document.getElementById('releaseFeedback').textContent = 'Distribuição liberada. Os agentes verificarão a atualização na próxima comunicação dentro da janela configurada.';
  } catch (error) { document.getElementById('releaseFeedback').textContent = error.message; }
  finally { button.disabled = false; }
}

async function pauseRelease() {
  try {
    await checkedFetch('/api/releases/pause', {method: 'POST'});
    releaseState.editing = false;
    await loadReleases();
    document.getElementById('releaseFeedback').textContent = 'Novas ofertas de atualização suspensas. Atualizações já iniciadas podem terminar.';
  } catch (error) { document.getElementById('releaseFeedback').textContent = error.message; }
}
