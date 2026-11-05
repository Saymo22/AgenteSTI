const state = {
      devices: [],
      currentView: 'overview',
      search: '',
      chart: null,
      currentDevice: null,
      soundEnabled: false,
      audioCtx: null,
      previousStatus: {},
      eventLogs: [],
      serverEvents: [],
      logFilter: '',
      firstLoad: true
    };

    const el = {
      navItems: () => document.querySelectorAll('.nav-item'),
      views: () => document.querySelectorAll('.view'),
      searchInput: document.getElementById('searchInput'),
      filterPill: document.getElementById('filterPill'),
      devicesGrid: document.getElementById('devicesGrid'),
      segmentsGrid: document.getElementById('segmentsGrid'),
      mappingSegmentsGrid: document.getElementById('mappingSegmentsGrid'),
      mapGroups: document.getElementById('mapGroups'),
      historyLogList: document.getElementById('historyLogList'),
      toast: document.getElementById('toast'),
      deviceModalOverlay: document.getElementById('deviceModalOverlay'),
      historyChart: document.getElementById('historyChart'),
      healthCircle: document.getElementById('healthCircle'),
      healthPercent: document.getElementById('healthPercent'),
      healthBadge: document.getElementById('healthBadge')
    };

    const icons = {
      search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>`,
      user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21a8 8 0 0 0-16 0"></path><circle cx="12" cy="7" r="4"></circle></svg>`,
      ip: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"></path><path d="M4 12h16"></path><path d="M4 17h16"></path></svg>`,
      chip: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="2"></rect><path d="M9 1v3"></path><path d="M15 1v3"></path><path d="M9 20v3"></path><path d="M15 20v3"></path><path d="M20 9h3"></path><path d="M20 14h3"></path><path d="M1 9h3"></path><path d="M1 14h3"></path></svg>`,
      network: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9a9 9 0 0 1 12 0"></path><path d="M9 12a5 5 0 0 1 6 0"></path><path d="M12 16h.01"></path></svg>`,
      clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg>`,
      win: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 4.3 10.8 3v8.6H2V4.3Zm10.1-1.5L22 1v10.6H12.1V2.8ZM2 12.5h8.8V21L2 19.7v-7.2Zm10.1 0H22V23l-9.9-1.4v-9.1Z"/></svg>`,
      linux: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c-2.2 0-3.8 1.9-3.8 4.6 0 1.7.6 2.9 1.2 4-.9 1-2.2 2.5-2.2 4.4 0 2.8 2 5 4.8 5s4.8-2.2 4.8-5c0-1.9-1.3-3.4-2.2-4.4.6-1.1 1.2-2.3 1.2-4 0-2.7-1.6-4.6-3.8-4.6Zm-1.7 5.1a1 1 0 1 1 0 2 1 1 0 0 1 0-2Zm3.4 0a1 1 0 1 1 0 2 1 1 0 0 1 0-2ZM12 10.8c.9 0 1.7.7 1.7 1.7S12.9 14.2 12 14.2s-1.7-.7-1.7-1.7.8-1.7 1.7-1.7Z"/><path d="M9.1 17.2c.9.6 1.9.9 2.9.9 1 0 2-.3 2.9-.9" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`,
      apple: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.9 12.2c0-2.1 1.7-3.2 1.8-3.2-1-1.5-2.5-1.7-3.1-1.8-1.3-.1-2.5.8-3.2.8-.7 0-1.7-.8-2.9-.8-1.5 0-2.9.9-3.6 2.2-1.6 2.8-.4 6.9 1.1 9 0.7 1 1.6 2.2 2.8 2.2 1.1 0 1.6-.7 3-.7s1.8.7 3 .7c1.2 0 2-1.1 2.7-2.1.8-1.2 1.2-2.4 1.2-2.5-.1 0-2.8-1.1-2.8-4Zm-2.2-6.6c.6-.8 1-1.8.9-2.9-.9.1-2 .6-2.7 1.4-.6.7-1.1 1.8-.9 2.8 1 0 2.1-.5 2.7-1.3Z"/></svg>`,
      android: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="m17.6 9.5 1.9-3.3c.1-.3 0-.6-.3-.8-.3-.1-.6 0-.8.3L16.5 9A10.9 10.9 0 0 0 12 8c-1.6 0-3.1.3-4.5 1L5.6 5.7c-.2-.3-.5-.4-.8-.2-.3.2-.4.5-.2.8l1.9 3.2A10.8 10.8 0 0 0 1 18h22a10.8 10.8 0 0 0-5.4-8.5ZM8 14.8A1.3 1.3 0 1 1 8 12a1.3 1.3 0 0 1 0 2.7Zm8 0A1.3 1.3 0 1 1 16 12a1.3 1.3 0 0 1 0 2.7Z"/></svg>`,
      unknown: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"></path><path d="M12 17h.01"></path></svg>`
    };


function init() {

   bindEvents();
   initNotifications();

    updateClock();

    setInterval(
        updateClock,
        1000
    );

    loadDevices();

    loadHistory();

    loadEvents();
    pollCommands();
    setInterval(pollCommands, 5000);

    setInterval(
        loadDevices,
        5000
    );

    setInterval(
        loadHistory,
        20000
    );

    setInterval(
        loadEvents,
        10000
    );

    document.getElementById(
        'logSearch'
    ).addEventListener('input', event => {

        state.logFilter = event.target.value
            .trim()
            .toLowerCase();

        renderLogs();

    });

    document.getElementById(
        'logReload'
    ).addEventListener('click', () => {

        loadEvents();

    });

    renderLogs();

}


    function bindEvents() {
      el.navItems().forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
      el.searchInput.addEventListener('input', e => {
        state.search = e.target.value.toLowerCase();
        renderAll();
      });
      document.getElementById('btnExport').addEventListener('click', exportCSV);
      document.getElementById('btnScan').addEventListener('click', scanNetwork);
      document.getElementById('btnSound').addEventListener('click', toggleSound);
      document.getElementById('btnTv').addEventListener('click', toggleKiosk);
      document.getElementById('modalClose').addEventListener('click', closeModal);
      el.deviceModalOverlay.addEventListener('click', (e) => { if (e.target === el.deviceModalOverlay) closeModal(); });
      document.getElementById('btnRestart').addEventListener('click', () => sendCommand('restart'));
      document.getElementById('btnShutdown').addEventListener('click', () => sendCommand('shutdown'));
      document.getElementById('btnChat').addEventListener('click', () => sendCommand('msg'));
      document.getElementById('btnCopyModalIp').addEventListener('click', copyModalIp);
    }

    async function enableAudioContext() {
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextCtor) throw new Error('Audio não suportado neste navegador.');
      if (!state.audioCtx) state.audioCtx = new AudioContextCtor();
      if (state.audioCtx.state === 'suspended') await state.audioCtx.resume();
      if (state.audioCtx.state !== 'running') throw new Error('Áudio bloqueado pelo navegador.');
    }

    function updateClock() {
      const now = new Date();
      document.getElementById('liveTime').textContent = now.toLocaleTimeString('pt-BR');
      document.getElementById('liveDate').textContent = now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });
    }

    function switchView(view) {
      state.currentView = view;
      el.navItems().forEach(btn => btn.classList.toggle('active', btn.dataset.view === view));
      el.views().forEach(section => section.classList.remove('active'));
      const actualView = ['116','117','118','119'].includes(view) ? 'overview' : view;
      document.getElementById(`view-${actualView}`).classList.add('active');
      updateFilterPill();
      renderAll();
      const viewNames = {overview:'Visão Geral','116':'Faixa IP 116','117':'Faixa IP 117','118':'Faixa IP 118','119':'Rede Servidor 119',mapping:'Mapeamento',history:'Histórico de Log'};
      addEventLog('info', 'Navegação do painel', `A visualização foi alterada para ${viewNames[view] || view}.`, new Date());
    }

    function updateFilterPill() {
      const labels = {
        overview: 'Todos os dispositivos',
        '116': 'Faixa 10.2.116.x',
        '117': 'Faixa 10.2.117.x',
        '118': 'Faixa 10.2.118.x',
        '119': 'Rede Servidor 10.2.119.x',
        mapping: 'Visualização por rede',
        history: 'Eventos e logs'
      };
      el.filterPill.textContent = labels[state.currentView] || 'Todos os dispositivos';
    }

    async function loadDevices() {
      try {
        const response = await checkedFetch('/api/devices');
        const data = await response.json();
        const devices = Array.isArray(data.devices) ? data.devices : [];
        processStatusChanges(devices);
        state.devices = devices;
        if (state.currentDevice && el.deviceModalOverlay.classList.contains('active')) {
          openModal(state.currentDevice.ip);
        }
        const summary = data.summary || buildSummary(devices);
        updateSummary(summary);
        renderAll();
        if (state.firstLoad) {
          addEventLog('success', 'Painel carregado', `Inventário inicial com ${devices.length} dispositivos.`, new Date());
          state.firstLoad = false;
        }
      } catch (err) {
        console.error(err);
        addEventLog('error', 'Falha ao carregar dispositivos', 'Não foi possível consultar /api/devices.', new Date());
        renderAll();
      }
    }

    async function loadHistory() {
      try {
        const response = await checkedFetch('/api/history');
        const data = await response.json();
        const snapshots = Array.isArray(data.snapshots) ? data.snapshots : [];
        renderHistoryChart(snapshots);
        mergeSnapshotLogs(snapshots);
      } catch (err) {
        console.error(err);
        addEventLog('warning', 'Histórico indisponível', 'Não foi possível consultar /api/history.', new Date());
      }
    }


/* ==========================================
   STI - HISTÓRICO PERSISTENTE
   ========================================== */

async function loadEvents() {

    try {

        const response = await checkedFetch(
            '/api/events?limit=300',
            {
                credentials: 'same-origin'
            }
        );

        if (!response.ok) {

            throw new Error(
                `Erro HTTP ${response.status}`
            );

        }

        const data = await response.json();

        if (!Array.isArray(data.events)) {

            throw new Error(
                'Formato de eventos inválido'
            );

        }

        state.serverEvents = data.events.map(event => {

            const status = String(
                event.status || ''
            ).toLowerCase();

            let type = 'info';

            if ([
                'offline',
                'erro',
                'error',
                'falha'
            ].includes(status)) {

                type = 'error';

            } else if ([
                'online',
                'entregue',
                'login',
                'sucesso'
            ].includes(status)) {

                type = 'success';

            } else if ([
                'pendente',
                'solicitado',
                'warning'
            ].includes(status)) {

                type = 'warning';

            }

            return {

                type: type,

                title:
                    `${event.category || 'Sistema'} · ${event.status || 'Evento'}`,

                text:
                    `${event.name || event.ip || 'STI'} — ${event.description || ''}`,

                date: new Date(event.timestamp),

                signature:
                    `server-${event.timestamp}-${event.category}-${event.ip}-${event.status}-${event.description}`,

                persisted: true

            };

        });

        renderLogs();

    } catch (error) {

        console.error(
            'Erro ao carregar histórico:',
            error
        );

        if (!state.serverEvents.length) {

            el.historyLogList.innerHTML = `
                <div class="empty-state">
                    Não foi possível carregar os
                    registros do servidor.
                    Verifique a API /api/events.
                </div>
            `;

        }

    }

}


/* ==========================================
   RENDERIZAR HISTÓRICO DE LOGS
   ========================================== */

function renderLogs() {

    const combined = [
        ...state.serverEvents,
        ...state.eventLogs
    ];

    const filtered = combined.filter(log => {

        if (!state.logFilter) {
            return true;
        }

        const search = `
            ${log.title}
            ${log.text}
        `.toLowerCase();

        return search.includes(
            state.logFilter
        );

    });

    filtered.sort((a, b) => {

        return (
            new Date(b.date) -
            new Date(a.date)
        );

    });

    const logs = filtered.slice(0, 300);

    if (!logs.length) {

        el.historyLogList.innerHTML = `
            <div class="empty-state">
                Nenhum evento encontrado.
            </div>
        `;

        return;

    }

    el.historyLogList.innerHTML = logs.map(log => {

        const date = new Date(log.date);

        const dateText = Number.isNaN(
            date.getTime()
        )
            ? 'Data indisponível'
            : date.toLocaleString('pt-BR');

        let icon = 'ℹ️';

        if (log.type === 'error') {
            icon = '🚨';
        }

        if (log.type === 'success') {
            icon = '✅';
        }

        if (log.type === 'warning') {
            icon = '⚠️';
        }

        const origem = log.persisted
            ? 'Salvo no servidor'
            : 'Evento desta sessão';

        return `
            <article class="log-item">

                <div class="log-icon">
                    ${icon}
                </div>

                <div>

                    <div class="log-title">
                        ${escapeHtml(log.title)}
                    </div>

                    <div class="log-meta">
                        ${escapeHtml(dateText)}
                        • ${origem}
                    </div>

                    <div class="log-text">
                        ${escapeHtml(log.text)}
                    </div>

                </div>

            </article>
        `;

    }).join('');

}


    function buildSummary(devices) {
      const online = devices.filter(d => d.online).length;
      const offline = devices.length - online;
      return { total: devices.length, online, offline };
    }

    function updateSummary(summary) {
      const highLatency = state.devices.filter(d => d.online && Number(d.latency || 0) > 100).length;
      const avgLatency = calcAvgLatency(state.devices);

      document.getElementById('metricTotal').textContent = summary.total || 0;
      document.getElementById('metricOnline').textContent = summary.online || 0;
      document.getElementById('metricOffline').textContent = summary.offline || 0;
      document.getElementById('metricLatency').textContent = `${avgLatency} ms`;
      document.getElementById('sideOnline').textContent = summary.online || 0;
      document.getElementById('sideOffline').textContent = summary.offline || 0;
      document.getElementById('sideHighLatency').textContent = highLatency;

      updateHealth(summary, highLatency);
    }

    function updateHealth(summary, highLatency) {
      const total = Math.max(summary.total || state.devices.length || 0, 1);
      const onlinePct = Math.round(((summary.online || 0) / total) * 100);
      const offlinePct = Math.round(((summary.offline || 0) / total) * 100);
      const latencyPct = Math.round((highLatency / total) * 100);

      document.getElementById('healthPercent').textContent = `${onlinePct}%`;
      document.getElementById('healthOnlineText').textContent = `${onlinePct}%`;
      document.getElementById('healthOfflineText').textContent = `${offlinePct}%`;
      document.getElementById('healthLatencyText').textContent = `${latencyPct}%`;
      document.getElementById('healthOnlineBar').style.width = `${onlinePct}%`;
      document.getElementById('healthOfflineBar').style.width = `${offlinePct}%`;
      document.getElementById('healthLatencyBar').style.width = `${latencyPct}%`;
      el.healthCircle.style.background = `conic-gradient(var(--green) 0deg, var(--green) ${onlinePct * 3.6}deg, rgba(255,255,255,0.06) ${onlinePct * 3.6}deg 360deg)`;

      let badgeClass = 'online';
      let badgeText = 'Estável';
      if (offlinePct >= 30) { badgeClass = 'offline'; badgeText = 'Crítica'; }
      else if (latencyPct >= 20 || offlinePct >= 10) { badgeClass = 'warning'; badgeText = 'Atenção'; }
      el.healthBadge.className = `status-badge ${badgeClass}`;
      el.healthBadge.textContent = badgeText;
    }

    function calcAvgLatency(devices) {
      const latencies = devices.filter(d => d.online && Number.isFinite(Number(d.latency))).map(d => Number(d.latency));
      if (!latencies.length) return 0;
      return Math.round(latencies.reduce((sum, val) => sum + val, 0) / latencies.length);
    }

    function renderAll() {
      renderSegments();
      renderDevices();
      renderMapping();
      renderLogs();
    }

    function getFilteredDevices() {
      let devices = [...state.devices];
      if (['116','117','118','119'].includes(state.currentView)) {
        devices = devices.filter(d => String(d.ip || '').startsWith(`10.2.${state.currentView}.`));
      }
      if (state.search) {
        devices = devices.filter(d => {
          const searchable = `${d.name || ''} ${d.ip || ''} ${d.user || ''} ${d.os || ''}`.toLowerCase();
          return searchable.includes(state.search);
        });
      }
      devices.sort((a, b) => statusRank(a) - statusRank(b) || String(a.ip).localeCompare(String(b.ip), undefined, { numeric: true }));
      return devices;
    }

    function statusRank(d) {
      if (!d.online) return 2;
      if (Number(d.latency || 0) > 100) return 1;
      return 0;
    }

    function getOSInfo(osString = '') {
      const os = String(osString);
      if (/windows/i.test(os)) return { cls: 'os-win', name: 'Windows', icon: icons.win };
      if (/linux/i.test(os)) return { cls: 'os-linux', name: 'Linux', icon: icons.linux };
      if (/apple|mac|ios/i.test(os)) return { cls: 'os-apple', name: 'Apple', icon: icons.apple };
      if (/android/i.test(os)) return { cls: 'os-android', name: 'Android', icon: icons.android };
      return { cls: 'os-unk', name: os || 'Desconhecido', icon: icons.unknown };
    }

    function renderDevices() {
      const devices = getFilteredDevices();
      if (!devices.length) {
        el.devicesGrid.innerHTML = `<div class="empty-state">Nenhum dispositivo encontrado para esse filtro.</div>`;
        return;
      }
      el.devicesGrid.innerHTML = devices.map(createDeviceCard).join('');
      document.querySelectorAll('.device-card').forEach(card => {
        card.addEventListener('click', () => openModal(card.dataset.ip));
      });
    }

    function createDeviceCard(device) {
      const os = getOSInfo(device.os);
      const status = getStatus(device);
      const latencyVal = device.online ? `${Number(device.latency || 0)} ms` : 'Offline';
      const latencyClass = !device.online ? 'offline' : Number(device.latency || 0) > 100 ? 'warn' : 'good';
      return `
        <article class="device-card ${status.cls}" data-ip="${escapeHtml(device.ip)}">
          <div class="device-head">
            <div style="display:flex;gap:14px;min-width:0;">
              <div class="device-os ${os.cls}">${os.icon}</div>
              <div class="device-title" style="min-width:0;">
                <strong title="${escapeHtml(device.name || 'Dispositivo')}">${escapeHtml(device.name || 'Dispositivo')}</strong>
                <span>${escapeHtml(os.name)}</span>
              </div>
            </div>
            <span class="status-badge ${status.cls}">${status.label}</span>
          </div>
          <div class="device-info">
            <div class="info-row">
              <div class="info-head">${icons.ip}<span>IP</span></div>
              <div class="info-value">${escapeHtml(device.ip || '--')}</div>
            </div>
            <div class="info-row">
              <div class="info-head">${icons.chip}<span>Sistema</span></div>
              <div class="info-value">${escapeHtml(device.os || '--')}</div>
            </div>
            <div class="info-row">
              <div class="info-head">${icons.user}<span>Usuário</span></div>
              <div class="info-value">${escapeHtml(device.user || 'Não informado')}</div>
            </div>
            <div class="info-row">
              <div class="info-head">${icons.network}<span>Status</span></div>
              <div class="info-value">${status.text}</div>
            </div>
          </div>
          <div class="device-footer">
            <span style="color:var(--muted);font-weight:700;">Clique para abrir o pop-up</span>
            <span class="latency-pill ${latencyClass}">${latencyVal}</span>
          </div>
        </article>
      `;
    }

    function getStatus(device) {
      if (!device.online) return { cls: 'offline', label: 'OFF', text: 'Offline' };
      if (Number(device.latency || 0) > 100) return { cls: 'warning', label: 'LAT', text: 'Alta latência' };
      return { cls: 'online', label: 'ON', text: 'Online' };
    }

    function renderSegments() {
      const html = ['116','117','118','119'].map(segment => {
        const devices = state.devices.filter(d => String(d.ip || '').startsWith(`10.2.${segment}.`));
        const online = devices.filter(d => d.online).length;
        const total = devices.length;
        const label = segment === '119' ? 'Rede Servidor 119' : `Faixa ${segment}`;
        const icon = segment === '119' ? '🖥️' : '🌐';
        const pct = total ? Math.round((online/total)*100) : 0;
        return `
          <article class="segment-card">
            <div class="segment-top">
              <div class="segment-name">${label}</div>
              <div class="segment-icon">${icon}</div>
            </div>
            <div class="segment-values">
              <strong>${total}</strong>
              <span>${online} online • ${pct}% disponível</span>
            </div>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:linear-gradient(90deg,var(--cyan),var(--blue))"></div></div>
          </article>
        `;
      }).join('');
      el.segmentsGrid.innerHTML = html || `<div class="empty-state">Sem segmentos disponíveis.</div>`;
      el.mappingSegmentsGrid.innerHTML = html || `<div class="empty-state">Sem segmentos disponíveis.</div>`;
    }

    function renderMapping() {
      const segments = ['116','117','118','119'];
      const groupHtml = segments.map(segment => {
        const devices = state.devices.filter(d => String(d.ip || '').startsWith(`10.2.${segment}.`));
        const title = segment === '119' ? 'Rede Servidor 119' : `Faixa de IP ${segment}`;
        if (!devices.length) {
          return `
            <article class="map-group">
              <div class="map-group-head"><h3>${title}</h3><span>0 dispositivos</span></div>
              <div class="empty-state">Nenhum dispositivo nesta faixa.</div>
            </article>
          `;
        }
        return `
          <article class="map-group">
            <div class="map-group-head"><h3>${title}</h3><span>${devices.length} dispositivos</span></div>
            <div class="map-device-list">
              ${devices.slice(0, 8).map(d => {
                const os = getOSInfo(d.os);
                const status = getStatus(d);
                return `
                  <div class="map-device-row">
                    <div class="device-os ${os.cls}" style="width:42px;height:42px;border-radius:14px;">${os.icon}</div>
                    <div style="min-width:0;">
                      <div style="font-weight:800;">${escapeHtml(d.name || 'Dispositivo')}</div>
                      <div class="mono">${escapeHtml(d.ip || '--')}</div>
                    </div>
                    <span class="status-badge ${status.cls}">${status.label}</span>
                    <span style="color:var(--muted);font-size:0.9rem;">${escapeHtml(d.user || 'Sem usuário')}</span>
                  </div>
                `;
              }).join('')}
            </div>
          </article>
        `;
      }).join('');
      el.mapGroups.innerHTML = groupHtml;
    }

    function openModal(ip) {
      const device = state.devices.find(d => String(d.ip) === String(ip));
      if (!device) return;
      state.currentDevice = device;
      const os = getOSInfo(device.os);
      const status = getStatus(device);
      const hw = device.agent_online ? (device.hw || {}) : {};

      document.getElementById('modalOs').innerHTML = os.icon;
      document.getElementById('modalOs').className = `modal-os ${os.cls}`;
      document.getElementById('modalName').textContent = device.name || 'Dispositivo';
      document.getElementById('modalSub').textContent = `${device.ip || '--'} • ${device.os || 'Sistema não identificado'}`;
      document.getElementById('modalDeviceField').textContent = device.name || '--';
      document.getElementById('modalIpField').textContent = device.ip || '--';
      document.getElementById('modalSystemField').textContent = device.os || '--';
      document.getElementById('modalUserField').textContent = device.user || 'Não informado';
      document.getElementById('modalStatusField').textContent = status.text;
      document.getElementById('modalLatencyField').textContent = device.online ? `${Number(device.latency || 0)} ms` : 'Offline';

      const cpu = clampNumber(hw.cpu);
      setUsage('modalCpuValue', 'modalCpuBar', cpu, cpu !== null ? `${cpu}%` : 'Aguardando');

      if (hw.ram_total != null && hw.ram_free != null && Number.isFinite(Number(hw.ram_total)) && Number.isFinite(Number(hw.ram_free))) {
        const total = Number(hw.ram_total);
        const free = Number(hw.ram_free);
        const used = Math.max(total - free, 0);
        const pct = total ? Math.round((used / total) * 100) : 0;
        setUsage('modalRamValue', 'modalRamBar', pct, `${used.toFixed(1)} / ${total} GB`);
      } else {
        setUsage('modalRamValue', 'modalRamBar', 0, 'Aguardando');
      }

      if (hw.disk_total != null && hw.disk_free != null && Number.isFinite(Number(hw.disk_total)) && Number.isFinite(Number(hw.disk_free))) {
        const total = Number(hw.disk_total);
        const free = Number(hw.disk_free);
        const usedPct = total ? Math.round(((total - free) / total) * 100) : 0;
        setUsage('modalDiskValue', 'modalDiskBar', usedPct, `${free} GB livres`);
      } else {
        setUsage('modalDiskValue', 'modalDiskBar', 0, 'Aguardando');
      }

      document.getElementById('modalUptimeValue').textContent = formatUptime(hw.uptime);
      document.getElementById('modalPrintersField').textContent = Array.isArray(hw.printers) && hw.printers.length ? hw.printers.join(', ') : 'Nenhuma informada';
      document.getElementById('modalAgentField').textContent = `${device.agent_online ? 'Conectado' : 'Sem comunicação recente'} • ${device.agent_version || 'Versão não informada'}`;
      for (const [id, command] of [['btnChat', 'msg'], ['btnRestart', 'restart'], ['btnShutdown', 'shutdown']]) {
        const button = document.getElementById(id);
        button.disabled = !device.agent_online || !(device.capabilities || []).includes(command);
        button.title = !device.agent_online ? 'Agente sem comunicação recente' : button.disabled ? 'Ação não habilitada neste agente' : '';
      }
      el.deviceModalOverlay.classList.add('active');
    }

    function setUsage(valueId, barId, pct, text) {
      document.getElementById(valueId).textContent = text;
      document.getElementById(barId).style.width = `${Math.max(0, Math.min(100, Number(pct) || 0))}%`;
    }

    async function copyModalIp() {
      const ip = String(state.currentDevice?.ip || '').trim();
      if (!ip) { showToast('IP não disponível.'); return; }
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(ip);
        } else {
          const temp = document.createElement('textarea');
          temp.value = ip;
          temp.style.position = 'fixed';
          temp.style.opacity = '0';
          document.body.appendChild(temp);
          temp.select();
          const success = document.execCommand('copy');
          temp.remove();
          if (!success) throw new Error('Cópia indisponível');
        }
        showToast(`IP ${ip} copiado!`);
      } catch (error) {
        console.error('Erro ao copiar IP:', error);
        showToast('Não foi possível copiar o IP.');
      }
    }

    function closeModal() {
      el.deviceModalOverlay.classList.remove('active');
    }

    async function sendCommand(command) {
      if (!state.currentDevice) return;
      if (command === 'msg') {
        const message = prompt('Digite a mensagem para o usuário:');
        if (!message) return;
        await postCommand(command, message);
        return;
      }
      const confirmed = confirm(`Deseja enviar o comando "${command.toUpperCase()}" para ${state.currentDevice.name || state.currentDevice.ip}?`);
      if (!confirmed) return;
      await postCommand(command);
    }

    async function checkedFetch(url, options = {}) {
      const response = await fetch(url, options);
      if (response.status === 401) {
        window.location.assign('/login');
        throw new Error('Sessão encerrada. Faça login novamente.');
      }
      if (!response.ok) {
        let message = `Erro HTTP ${response.status}`;
        try { message = (await response.json()).error || message; } catch (_) { /* resposta sem JSON */ }
        throw new Error(message);
      }
      return response;
    }

    function formatUptime(value) {
      if (value == null || !Number.isFinite(Number(value))) return 'Aguardando';
      const minutes = Math.floor(Number(value) / 60);
      return `${Math.floor(minutes / 1440)}d ${Math.floor(minutes / 60) % 24}h ${minutes % 60}min`;
    }

    const pendingCommands = new Map();
    try {
      const saved = JSON.parse(sessionStorage.getItem('sti-pending-commands') || '[]');
      if (Array.isArray(saved)) saved.slice(-50).forEach(([id, job]) => pendingCommands.set(id, job));
    } catch (_) { /* armazenamento indisponível ou inválido */ }

    function savePendingCommands() {
      try { sessionStorage.setItem('sti-pending-commands', JSON.stringify([...pendingCommands])); }
      catch (_) { /* o acompanhamento continua em memória */ }
    }

    async function postCommand(command, message) {
      const ip = state.currentDevice.ip;
      try {
        const response = await checkedFetch(`/api/command/${encodeURIComponent(ip)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command, message: message || '' })
        });
        const data = await response.json();
        pendingCommands.set(data.command_id, { ip, command, status: 'queued' });
        savePendingCommands();
        showToast('Solicitação na fila. Aguardando o agente.');
        addEventLog('info', 'Comando na fila', `${command.toUpperCase()} solicitado para ${ip}.`, new Date());
        closeModal();
      } catch (error) {
        showToast(error.message);
      }
    }

    let pollingCommands = false;
    async function pollCommands() {
      if (pollingCommands || !pendingCommands.size) return;
      pollingCommands = true;
      const labels = { queued: 'Na fila', delivered: 'Entregue', accepted: 'Aceito pelo agente',
        completed: 'Concluído', initiated: 'Ação iniciada', rejected: 'Recusado', failed: 'Falhou', expired: 'Prazo excedido; resultado incerto' };
      try {
        for (const [id, previous] of pendingCommands) {
          try {
            const response = await checkedFetch(`/api/commands/${encodeURIComponent(id)}`);
            const { job } = await response.json();
            if (previous.status !== job.status) {
              const text = `${previous.ip}: ${labels[job.status] || job.status}. ${job.result || ''}`;
              addEventLog(['failed', 'rejected', 'expired'].includes(job.status) ? 'warning' : 'info', 'Resultado do comando', text);
              previous.status = job.status;
              showToast(text);
            }
            if (!['queued', 'delivered', 'accepted'].includes(job.status)) pendingCommands.delete(id);
          } catch (error) {
            console.error('Falha ao consultar comando:', error);
            // Uma resposta 404 indica job removido; não criar consultas infinitas.
            if (error.message.includes('Comando não encontrado')) pendingCommands.delete(id);
          }
        }
        savePendingCommands();
      } finally { pollingCommands = false; }
    }

    async function scanNetwork() {
      const btn = document.getElementById('btnScan');
      btn.disabled = true;
      const original = btn.innerHTML;
      btn.innerHTML = `<span>⏳ Escaneando...</span>`;
      try {
        const response = await checkedFetch('/api/scan', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        showToast('Escaneamento iniciado.');
        addEventLog('success', 'Escaneamento executado', 'A rotina de scan da rede foi acionada.', new Date());
        setTimeout(() => loadDevices(), 1000);
      } catch (err) {
        console.error(err);
        showToast(err.message);
      } finally {
        setTimeout(() => {
          btn.disabled = false;
          btn.innerHTML = original;
        }, 1000);
      }
    }

    function safeCsv(value) {
      const text = String(value ?? '');
      return /^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text) ? "'" + text : text;
    }

    function exportCSV() {
      const devices = getFilteredDevices();
      if (!devices.length) {
        showToast('Nenhum dado para exportar.');
        return;
      }
      const header = ['IP','Dispositivo','Sistema','Status','Usuário','Latência(ms)'];
      const rows = devices.map(d => [
        d.ip || '',
        d.name || '',
        d.os || '',
        d.online ? 'Online' : 'Offline',
        d.user || '',
        Number(d.latency || 0)
      ]);
      const csv = [header, ...rows].map(row => row.map(value => `"${safeCsv(value).replace(/"/g, '""')}"`).join(',')).join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'inventario_sti_premium.csv';
      link.click();
      URL.revokeObjectURL(url);
      showToast('CSV exportado com sucesso.');
      addEventLog('success', 'Exportação CSV', `Exportação realizada com ${devices.length} registros.`, new Date());
    }

    async function toggleSound() {
      const btn = document.getElementById('btnSound');
      if (state.soundEnabled) {
        state.soundEnabled = false;
        btn.classList.remove('active');
        btn.setAttribute('aria-pressed', 'false');
        showToast('Alerta sonoro desativado.');
        addEventLog('info', 'Alerta sonoro', 'O alerta sonoro foi desativado.', new Date());
        return;
      }
      try {
        await enableAudioContext();
        state.soundEnabled = true;
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
        playAlert(); // Teste audível na ativação
        showToast('Som ativado: teste de alerta reproduzido.');
        addEventLog('success', 'Alerta sonoro', 'Som ativado e teste disparado.', new Date());
      } catch (err) {
        showToast('O navegador bloqueou o áudio: ' + err.message);
        addEventLog('warning', 'Alerta sonoro', 'Não foi possível ativar o áudio.', new Date());
      }
    }

    function playAlert() {
      if (!state.soundEnabled || !state.audioCtx || state.audioCtx.state !== 'running') return;
      const now = state.audioCtx.currentTime;
      [0, 0.42].forEach(delay => {
        const osc = state.audioCtx.createOscillator();
        const gain = state.audioCtx.createGain();
        osc.connect(gain); gain.connect(state.audioCtx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(740, now + delay);
        osc.frequency.setValueAtTime(880, now + delay + .13);
        gain.gain.setValueAtTime(.0001, now + delay);
        gain.gain.linearRampToValueAtTime(.18, now + delay + .025);
        gain.gain.exponentialRampToValueAtTime(.0001, now + delay + .35);
        osc.start(now + delay);
        osc.stop(now + delay + .36);
      });
    }

    function toggleKiosk() {
      document.body.classList.toggle('kiosk');
      if (document.body.classList.contains('kiosk')) {
        if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
        showToast('Modo TV ativado.');
        addEventLog('info', 'Modo TV', 'Modo TV ativado.', new Date());
      } else {
        if (document.exitFullscreen) document.exitFullscreen();
        showToast('Modo TV desativado.');
        addEventLog('info', 'Modo TV', 'Modo TV desativado.', new Date());
      }
    }


/* ==========================================
   STI — MONITORAMENTO DE QUEDAS
   ========================================== */

function processStatusChanges(devices) {

    // Controle de estado
    if (!state.notifications) {
        state.notifications = [];
    }

    let houveQueda = false;

    // Contagem atual de equipamentos offline
    const offline = devices.filter(
        device => device.online === false
    );

    const badge = document.getElementById(
        'notificationBadge'
    );

    const summary = document.getElementById(
        'notificationSummary'
    );

    badge.textContent = offline.length > 99
        ? '99+'
        : offline.length;

    badge.hidden = offline.length === 0;

    summary.textContent =
        `${offline.length} dispositivos offline`;

    // Detectar mudanças de estado
    devices.forEach(device => {

        const ip = String(device.ip || '');

        if (!ip) return;

        const current = device.online === true;

        const previous = state.previousStatus[ip];

        // Na primeira leitura não dispara alerta
        if (previous === undefined) {

            state.previousStatus[ip] = current;
            return;

        }

        // Estado não mudou
        if (previous === current) {
            return;
        }

        state.previousStatus[ip] = current;

        const nome = device.name || ip;

        const titulo = current
            ? 'Dispositivo voltou'
            : 'Dispositivo caiu';

        const descricao = current
            ? `${nome} (${ip}) voltou a ficar online.`
            : `${nome} (${ip}) ficou offline.`;

        // Adicionar ao histórico existente
        addEventLog(
            current ? 'success' : 'error',
            titulo,
            descricao,
            new Date()
        );

        // Adicionar à central de notificações
        state.notifications.unshift({

            ip: ip,
            name: nome,
            title: titulo,
            text: descricao,
            recovered: current,
            date: new Date()

        });

        // Manter as últimas 30 notificações
        state.notifications =
            state.notifications.slice(0, 30);

        if (!current) {
            houveQueda = true;
        }

    });

    // Um único som por atualização,
    // mesmo que vários dispositivos caiam juntos.
    if (houveQueda && state.soundEnabled) {

        playAlert();

        showToast(
            'Atenção: dispositivo(s) ficaram offline!'
        );

    }

    renderNotifications();
}


/* ==========================================
   RENDERIZAR NOTIFICAÇÕES
   ========================================== */

function renderNotifications() {

    const container = document.getElementById(
        'notificationList'
    );

    if (!state.notifications ||
        !state.notifications.length) {

        container.innerHTML = `
            <p class="sti-notification-empty">
                Nenhuma ocorrência recente.
            </p>
        `;

        return;
    }

    // Limpar elementos anteriores
    container.replaceChildren();

    state.notifications.forEach(notification => {

        const item = document.createElement('div');

        item.className =
            'sti-notification-item' +
            (notification.recovered ? ' recovered' : '');

        const dot = document.createElement('span');
        dot.className = 'sti-notification-dot';

        const info = document.createElement('div');
        info.className = 'sti-notification-info';

        const title = document.createElement('strong');
        title.textContent = notification.title;

        const description = document.createElement('p');
        description.textContent = notification.text;

        const date = document.createElement('small');

        date.textContent =
            new Date(notification.date)
                .toLocaleString('pt-BR');

        info.append(
            title,
            description,
            date
        );

        item.append(dot, info);

        container.appendChild(item);

    });

}


/* ==========================================
   ABRIR / FECHAR CENTRAL
   ========================================== */

function initNotifications() {

    state.notifications = [];

    const button = document.getElementById(
        'btnNotifications'
    );

    const panel = document.getElementById(
        'notificationPanel'
    );

    const clear = document.getElementById(
        'btnClearNotifications'
    );

    button.addEventListener('click', event => {

        event.stopPropagation();

        panel.hidden = !panel.hidden;

        button.setAttribute(
            'aria-expanded',
            String(!panel.hidden)
        );

    });

    clear.addEventListener('click', () => {

        state.notifications = [];

        renderNotifications();

        showToast('Notificações recentes limpas.');

    });

    document.addEventListener('click', event => {

        if (!event.target.closest(
            '.sti-notification-wrap'
        )) {

            panel.hidden = true;

            button.setAttribute(
                'aria-expanded',
                'false'
            );

        }

    });

    renderNotifications();

}


    function mergeSnapshotLogs(snapshots) {
      if (!snapshots.length) return;
      const latest = snapshots[snapshots.length - 1];
      if (!latest) return;
      const date = new Date(latest[0]);
      const signature = `snapshot-${date.toISOString()}-${latest[1]}-${latest[2]}`;
      if (!state.eventLogs.some(log => log.signature === signature)) {
        state.eventLogs.unshift({
          type: 'info',
          title: 'Snapshot de disponibilidade',
          text: `${latest[1]} dispositivos online de um total de ${latest[2]}.`,
          date,
          signature
        });
        state.eventLogs = state.eventLogs.slice(0, 40);
        renderLogs();
      }
    }

    function addEventLog(type, title, text, date = new Date()) {
      const signature = `${type}-${title}-${text}-${new Date(date).toISOString()}`;
      if (state.eventLogs.some(log => log.signature === signature)) return;
      state.eventLogs.unshift({ type, title, text, date, signature });
      state.eventLogs = state.eventLogs.slice(0, 40);
      renderLogs();
    }

    function renderHistoryChart(snapshots) {
      const ctx = el.historyChart.getContext('2d');
      if (state.chart) state.chart.destroy();
      const labels = snapshots.map(s => new Date(s[0]).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));
      const online = snapshots.map(s => s[1]);
      const total = snapshots.map(s => s[2]);
      state.chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Online',
              data: online,
              borderColor: '#2be38c',
              backgroundColor: 'rgba(43,227,140,0.16)',
              fill: true,
              tension: 0.36,
              pointRadius: 0,
              borderWidth: 2.5
            },
            {
              label: 'Total',
              data: total,
              borderColor: 'rgba(255,255,255,0.45)',
              borderDash: [6, 6],
              tension: 0.36,
              fill: false,
              pointRadius: 0,
              borderWidth: 1.8
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { labels: { color: '#edf4ff', font: { family: 'Inter', weight: '700' } } }
          },
          scales: {
            x: { ticks: { color: '#8fa4c2' }, grid: { color: 'rgba(255,255,255,0.05)' } },
            y: { ticks: { color: '#8fa4c2' }, grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true }
          }
        }
      });
    }

    function showToast(message) {
      el.toast.textContent = message;
      el.toast.classList.add('show');
      clearTimeout(showToast.timeout);
      showToast.timeout = setTimeout(() => el.toast.classList.remove('show'), 2600);
    }

    function clampNumber(value) {
      if (value == null || value === '') return null;
      const n = Number(value);
      return Number.isFinite(n) ? Math.max(0, Math.min(100, Math.round(n))) : null;
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[character]));
    }

    init();
