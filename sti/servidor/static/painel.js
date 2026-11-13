const state = {
      devices: [],
      currentView: 'overview',
      kiosk: false,
      kioskPreviousView: 'overview',
      kioskFullscreen: false,
      search: '',
      statusFilter: 'all',
      connected: false,
      lastFocus: null,
      organizationFilters: { department: '', room: '', responsible: '' },
      groupBy: '',
      organizationEditor: { ip: null, dirty: false, saving: false, revision: '' },
      chart: null,
      currentDevice: null,
      soundEnabled: false,
      audioCtx: null,
      soundBuffer: null,
      soundName: '',
      soundVolume: 70,
      soundSources: [],
      soundGain: null,
      soundLoading: false,
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
   initAlertSoundControls();
   initSoundSettings();
   initReleaseControls();

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
      document.getElementById('btnMobileNav').addEventListener('click', () => toggleMobileNav(!document.getElementById('adminSidebar').classList.contains('is-open')));
      document.getElementById('navBackdrop').addEventListener('click', () => toggleMobileNav(false));
      document.querySelectorAll('[data-status]').forEach(button => {
        button.addEventListener('click', () => setStatusFilter(button.dataset.status));
        if (button.tagName !== 'BUTTON') button.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setStatusFilter(button.dataset.status); }
        });
      });
      document.addEventListener('keydown', handlePremiumKeys);
      installCardSpotlight();
      document.addEventListener('pointerdown', event => {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        const button = event.target.closest('.tool-btn,.nav-item,.legend-pill,.copy-ip-btn');
        if (!button || button.disabled) return;
        const bounds = button.getBoundingClientRect(), size = Math.max(bounds.width, bounds.height) * 2;
        const ripple = document.createElement('span');
        ripple.className = 'sti-ripple';
        ripple.setAttribute('aria-hidden', 'true');
        Object.assign(ripple.style, {width:`${size}px`,height:`${size}px`,left:`${event.clientX-bounds.left-size/2}px`,top:`${event.clientY-bounds.top-size/2}px`});
        button.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
      });
      document.getElementById('btnScan').addEventListener('click', scanNetwork);
      document.getElementById('btnRemap').addEventListener('click', remapNetwork);
      document.getElementById('btnTv').addEventListener('click', toggleKiosk);
      document.getElementById('exitTv').addEventListener('click', toggleKiosk);
      document.addEventListener('fullscreenchange', () => {
        if (state.kiosk && state.kioskFullscreen && !document.fullscreenElement) setKioskMode(false);
      });
      document.getElementById('modalClose').addEventListener('click', closeModal);
      el.deviceModalOverlay.addEventListener('click', (e) => { if (e.target === el.deviceModalOverlay) closeModal(); });
      document.getElementById('btnRestart').addEventListener('click', () => sendCommand('restart'));
      document.getElementById('btnShutdown').addEventListener('click', () => sendCommand('shutdown'));
      document.getElementById('btnChat').addEventListener('click', () => sendCommand('msg'));
      document.getElementById('btnCopyModalIp').addEventListener('click', copyModalIp);
      document.getElementById('btnDeviceHistory').addEventListener('click', loadDeviceHistory);
      document.getElementById('btnReconcileIdentity').addEventListener('click', reconcileIdentity);
      document.getElementById('organizationForm').addEventListener('submit', saveOrganization);
      for (const field of DEVICE_PROFILE_FIELDS) {
        document.getElementById(ORGANIZATION_INPUTS[field]).addEventListener('input', () => {
          state.organizationEditor.dirty = true;
          document.getElementById('organizationSaveStatus').textContent = 'Alterações não salvas';
        });
        if (ORGANIZATION_FILTERS[field]) {
          document.getElementById(ORGANIZATION_FILTERS[field]).addEventListener('change', event => {
            state.organizationFilters[field] = event.target.value;
            renderAll();
          });
        }
      }
      document.getElementById('organizationGroupBy').addEventListener('change', event => {
        state.groupBy = ORGANIZATION_FIELDS.includes(event.target.value) ? event.target.value : '';
        renderDevices();
      });
      document.getElementById('clearOrganizationFilters').addEventListener('click', () => {
        state.search = '';
        state.statusFilter = 'all';
        syncStatusFilters();
        el.searchInput.value = '';
        state.organizationFilters = { department: '', room: '', responsible: '' };
        state.groupBy = '';
        document.getElementById('organizationGroupBy').value = '';
        updateOrganizationFilters();
        renderAll();
      });
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
      const tvTime = document.getElementById('tvLiveTime');
      if (tvTime) {
        tvTime.textContent = now.toLocaleTimeString('pt-BR', {hour12: false});
        tvTime.dateTime = now.toISOString();
        document.getElementById('tvLiveDate').textContent = now.toLocaleDateString('pt-BR', {weekday: 'long', day: '2-digit', month: 'long'});
      }
    }

    function switchView(view) {
      state.currentView = view;
      el.navItems().forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
        if (btn.dataset.view === view) btn.setAttribute('aria-current', 'page');
        else btn.removeAttribute('aria-current');
      });
      toggleMobileNav(false);
      el.views().forEach(section => section.classList.remove('active'));
      const actualView = ['116','117','118','119'].includes(view) ? 'overview' : view;
      document.getElementById(`view-${actualView}`).classList.add('active');
      updateFilterPill();
      renderAll();
      if (view === 'updates') loadReleases();
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
        history: 'Eventos e logs',
        updates: 'Versões e releases'
      };
      el.filterPill.textContent = labels[state.currentView] || 'Todos os dispositivos';
    }

    async function loadDevices() {
      try {
        const response = await checkedFetch('/api/devices');
        const data = await response.json();
        const devices = Array.isArray(data.devices) ? data.devices : [];
        updateSyncStatus(true);
        updateScanState(data.scan || {});
        processStatusChanges(devices);
        state.devices = devices;
        if (state.currentView === 'updates') renderReleaseDevices();
        const conflicts = Array.isArray(data.identity_conflicts) ? data.identity_conflicts : [];
        const banner = document.getElementById('identityConflictBanner');
        banner.hidden = !conflicts.length;
        banner.textContent = conflicts.map(item => `${item.ip}: ${item.description}`).join(' • ');
        updateOrganizationFilters();
        if (state.currentDevice && el.deviceModalOverlay.classList.contains('active')) {
          openModal(deviceKey(state.currentDevice), true);
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
        updateSyncStatus(false);
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

        let icon = uiIcon('report');

        if (log.type === 'error') {
            icon = uiIcon('alert');
        }

        if (log.type === 'success') {
            icon = uiIcon('check');
        }

        if (log.type === 'warning') {
            icon = uiIcon('alert');
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

      animateMetric('metricTotal', summary.total || 0);
      animateMetric('metricOnline', summary.online || 0);
      animateMetric('metricOffline', summary.offline || 0);
      animateMetric('metricLatency', avgLatency, ' ms');
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
      const latencies = devices.filter(d => d.online && d.latency != null && d.latency !== '' && Number.isFinite(Number(d.latency)) && Number(d.latency) >= 0).map(d => Number(d.latency));
      if (!latencies.length) return null;
      return Math.round(latencies.reduce((sum, val) => sum + val, 0) / latencies.length);
    }

    function renderAll() {
      renderSegments();
      renderDevices();
      renderMapping();
      renderLogs();
    }

    function getFilteredDevices() {
      if (state.kiosk) return [...state.devices].sort((a, b) => statusRank(a) - statusRank(b) || String(a.ip).localeCompare(String(b.ip), undefined, {numeric: true}));
      let devices = state.devices.filter(device => matchesStatus(device, state.statusFilter));
      if (['116','117','118','119'].includes(state.currentView)) {
        devices = devices.filter(d => String(d.ip || '').startsWith(`10.2.${state.currentView}.`));
      }
      devices = devices.filter(device => ORGANIZATION_FIELDS.every(field =>
        matchesOrganizationFilter(device.organization?.[field], state.organizationFilters[field])
      ));
      if (state.search) {
        devices = devices.filter(d => {
          const searchable = `${getDevicePlatform(d).name} ${d.organization?.display_name || ''} ${d.name || ''} ${d.ip || ''} ${d.user || ''} ${d.os || ''} ${d.device_id || ''} ${d.agent_id || ''} ${d.serial_number || ''} ${d.manufacturer || ''} ${d.model || ''} ${(d.mac_addresses || []).join(' ')} ${ORGANIZATION_FIELDS.map(field => d.organization?.[field] || '').join(' ')}`;
          return normalizeSearch(searchable).includes(normalizeSearch(state.search));
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
      if (/android/i.test(os)) return { cls: 'os-android', name: 'Android', icon: icons.android };
      if (/\bios\b|\bipados\b|iphone|ipad/i.test(os)) return { cls: 'os-ios', name: 'iOS', icon: icons.apple };
      if (/\blinux\b|\bubuntu\b|\bdebian\b|\bfedora\b/i.test(os)) return { cls: 'os-linux', name: 'Linux', icon: icons.linux };
      if (/\bapple\b|\bmacos\b|mac os|macbook|\bimac\b|\bdarwin\b/i.test(os)) return { cls: 'os-apple', name: 'macOS', icon: icons.apple };
      if (os === 'Impressora') return { cls: 'os-printer', name: os, icon: uiIcon('printer') };
      if (os === 'Equipamento de rede') return { cls: 'os-network', name: os, icon: uiIcon('network') };
      if (os === 'Outro') return { cls: 'os-other', name: os, icon: uiIcon('monitor') };
      return { cls: 'os-unk', name: 'Não identificado', icon: uiIcon('network') };
    }

    function getDevicePlatform(device) {
      const reported = getOSInfo(device.os);
      if (reported.cls !== 'os-unk') {
        const agent = device.identification_source === 'agent' || device.agent_version || device.agent_online;
        return {...reported, detail: device.os, source: agent ? 'agent' : 'inventory', label: agent ? 'Informado pelo agente' : 'Informado no inventário'};
      }
      const manual = getOSInfo(device.organization?.platform);
      if (manual.cls !== 'os-unk') return {...manual, detail: manual.name, source: 'manual', label: 'Cadastrado por você'};
      // Somente palavras explícitas do nome de rede; fabricante, IP e ping não comprovam o sistema.
      const name = String(device.name || '').split('.')[0];
      const hints = [
        [/\b(?:iphone|ipad)(?:\b|[-_])/i, 'iOS'], [/\bandroid(?:\b|[-_])/i, 'Android'],
        [/\b(?:macbook|imac|mac-mini)(?:\b|[-_])/i, 'macOS'],
        [/\b(?:ubuntu|debian|fedora|linux)(?:\b|[-_])/i, 'Linux'],
        [/\b(?:windows|win10|win11)(?:\b|[-_])/i, 'Windows']
      ];
      const hint = hints.find(([pattern]) => pattern.test(name));
      if (hint) return {...getOSInfo(hint[1]), detail: hint[1] + ' · provável', source: 'dns', label: 'Provável pelo nome · confirme'};
      return {...reported, detail: 'Sistema não identificado', source: 'unknown', label: 'Cadastre o sistema nos detalhes'};
    }

    function renderDevices() {
      const devices = getFilteredDevices();
      document.getElementById('organizationResultCount').textContent = `${devices.length} de ${state.devices.length} dispositivos • indicadores gerais consideram toda a rede`;
      if (!devices.length) {
        el.devicesGrid.innerHTML = `<div class="empty-state">Nenhum dispositivo encontrado para esse filtro.</div>`;
        return;
      }
      const groupBy = state.kiosk ? '' : state.groupBy;
      el.devicesGrid.innerHTML = groupDevices(devices, groupBy).map(group =>
        `${groupBy ? `<h3 class="device-group-heading">${escapeHtml(group.label)}<span>${group.devices.length} máquinas</span></h3>` : ''}${group.devices.map(createDeviceCard).join('')}`
      ).join('');
      document.querySelectorAll('.device-card').forEach(card => {
        card.addEventListener('click', () => openModal(card.dataset.reference));
        card.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openModal(card.dataset.reference); }
        });
      });
    }

    function createDeviceCard(device) {
      const os = getDevicePlatform(device);
      const status = getStatus(device);
      const identity = getDeviceIdentity(device);
      return `
        <article class="device-card ${status.cls}" data-ip="${escapeHtml(device.ip)}" data-reference="${escapeHtml(deviceKey(device))}" tabindex="0" role="button" aria-label="Gerenciar ${escapeHtml(identity.name)}">
          <div class="device-head">
            <div style="display:flex;gap:14px;min-width:0;">
              <div class="device-os ${os.cls}" title="${escapeHtml(os.name + ' · ' + os.label)}" aria-label="${escapeHtml(os.name)}">${os.icon}</div>
              <div class="device-title" style="min-width:0;">
                <strong title="${escapeHtml(identity.name)}">${escapeHtml(identity.name)}</strong>
                <span class="identity-source">${escapeHtml(identity.sourceLabel)}</span>
              </div>
            </div>
            <span class="status-badge ${status.cls}"><i></i>${status.text}</span>
          </div>
          <div class="device-address">${icons.ip}<span>${escapeHtml(device.ip)}</span><small>${device.address_active === false ? 'Último IP' : 'IPv4'}</small></div>
          <div class="device-platform-tag ${os.source}"><strong>${escapeHtml(os.name)}</strong><span>${escapeHtml(os.label)}</span></div>
          <div class="device-identity-tag">${uiIcon('shield')} ${device.device_id ? `Identidade permanente · ${escapeHtml(device.device_id.slice(0,8))}` : 'Cadastro por IP · confira se o endereço mudar'}</div>
          <div class="device-info">
            <div class="info-row">
              <div class="info-head">${icons.chip}<span>Sistema / tipo</span></div>
              <div class="info-value ${identity.osKnown ? '' : 'data-missing'}" title="${escapeHtml(identity.os)}">${escapeHtml(identity.os)}</div>
            </div>
            <div class="info-row">
              <div class="info-head">${icons.user}<span>${device.agent_online ? 'Usuário conectado' : 'Último usuário informado'}</span></div>
              <div class="info-value ${identity.userKnown ? '' : 'data-missing'}" title="${escapeHtml(identity.user)}">${escapeHtml(identity.user)}</div>
            </div>
            <div class="info-row">
              <div class="info-head">${uiIcon('monitor')}<span>Agente STI</span></div>
              <div class="info-value agent-state ${device.agent_online ? 'connected' : 'data-missing'}">${escapeHtml(identity.agent)}</div>
            </div>
            <div class="info-row">
              <div class="info-head">${icons.network}<span>Latência · ping</span></div>
              <div class="info-value latency-value ${identity.latencyClass}">${identity.latency}</div>
            </div>
          </div>
          <dl class="organization-summary">
            ${ORGANIZATION_FIELDS.map(field => `<div><dt>${ORGANIZATION_LABELS[field]}</dt><dd>${escapeHtml(device.organization?.[field] || 'Não informado')}</dd></div>`).join('')}
          </dl>
          <div class="device-footer">
            <span class="device-seen">${escapeHtml(timeAgo(device.seconds_ago))}</span>
            <span class="device-open">${os.source === 'unknown' ? 'Identificar dispositivo' : 'Ver detalhes'} ${uiIcon('arrow')}</span>
          </div>
        </article>
      `;
    }

    function timeAgo(seconds) {
      if (seconds == null || !Number.isFinite(Number(seconds))) return 'Sem registro recente';
      const value = Math.max(0, Number(seconds));
      if (value < 60) return 'Visto agora';
      if (value < 3600) return `Visto há ${Math.floor(value / 60)} min`;
      if (value < 86400) return `Visto há ${Math.floor(value / 3600)} h`;
      return `Visto há ${Math.floor(value / 86400)} dias`;
    }

    function getDeviceIdentity(device) {
      const provisional = !device.name || device.name === device.ip || /^host-\d+$/i.test(device.name);
      const source = device.identification_source || (device.agent_version || device.agent_online ? 'agent' : provisional ? 'network' : 'dns');
      const placeholder = !device.name || device.name === device.ip || (source !== 'agent' && provisional);
      const known = value => Boolean(value && !/^(desconhecido|não informado|unknown|none|n\/a)$/i.test(String(value).trim()));
      const platform = getDevicePlatform(device);
      const osKnown = platform.source !== 'unknown';
      const userKnown = known(device.user);
      const latencyKnown = device.latency != null && device.latency !== '' && Number.isFinite(Number(device.latency)) && Number(device.latency) >= 0;
      return {
        source, osKnown, userKnown,
        name: device.organization?.display_name || (placeholder ? 'Dispositivo sem nome' : device.name),
        sourceLabel: device.organization?.display_name ? 'Nome cadastrado por você' : source === 'agent' ? 'Identificado pelo agente' : source === 'dns' ? 'Nome da rede · DNS' : source === 'saved' ? 'Nome salvo no inventário' : 'Identificação pendente',
        os: platform.detail,
        user: userKnown ? device.user : device.agent_online ? 'Nenhuma sessão informada' : 'Aguardando agente',
        agent: device.agent_online ? 'Conectado' : source === 'agent' ? 'Sem comunicação' : 'Não identificado',
        latency: !device.online ? 'Sem resposta' : latencyKnown ? `${Number(device.latency).toLocaleString('pt-BR', {maximumFractionDigits: 1})} ms` : 'Não medida',
        latencyClass: !device.online ? 'offline' : !latencyKnown ? 'data-missing' : Number(device.latency) > 100 ? 'warn' : 'good',
        notice: device.agent_online ? 'Agente conectado. Sistema, usuário e recursos foram informados pela máquina.' : source === 'agent'
          ? 'O agente não enviou dados recentes. Sistema e usuário abaixo são do último envio; os recursos atuais estão indisponíveis.'
          : 'Equipamento detectado na rede. O IP e o ping não revelam o sistema operacional. Cadastre nome e sistema abaixo; sugestões pelo DNS são prováveis. Usuário e recursos precisam de um agente compatível.'
      };
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
        const icon = uiIcon(segment === '119' ? 'monitor' : 'globe');
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
                const os = getDevicePlatform(d);
                const status = getStatus(d);
                return `
                  <div class="map-device-row">
                    <div class="device-os ${os.cls}" style="width:42px;height:42px;border-radius:14px;">${os.icon}</div>
                    <div style="min-width:0;">
                      <div style="font-weight:800;">${escapeHtml(getDeviceIdentity(d).name)}</div>
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

    function deviceKey(device) { return String(device.device_id || device.ip || ''); }

    function openModal(reference, refresh = false) {
      const device = state.devices.find(d => deviceKey(d) === String(reference));
      if (!device) {
        if (refresh) {
          for (const id of ['btnChat','btnRestart','btnShutdown']) document.getElementById(id).disabled = true;
          document.getElementById('modalIdentificationNotice').textContent = 'O cadastro mudou. Feche esta janela e abra o equipamento novamente.';
        }
        return;
      }
      state.currentDevice = device;
      const editor = state.organizationEditor;
      if (!refresh || (!editor.dirty && !editor.saving)) {
        editor.ip = deviceKey(device);
        editor.dirty = false;
        editor.revision = device.organization?.updated_at || '';
        for (const field of DEVICE_PROFILE_FIELDS) {
          document.getElementById(ORGANIZATION_INPUTS[field]).value = device.organization?.[field] || '';
        }
        document.getElementById('organizationSaveStatus').textContent = '';
      }
      const os = getDevicePlatform(device);
      const status = getStatus(device);
      const hw = device.agent_online ? (device.hw || {}) : {};
      const identity = getDeviceIdentity(device);

      document.getElementById('modalOs').innerHTML = os.icon;
      document.getElementById('modalOs').className = `modal-os ${os.cls}`;
      document.getElementById('modalOs').title = `${os.name} · ${os.label}`;
      document.getElementById('modalName').textContent = identity.name;
      document.getElementById('modalSub').textContent = `${device.ip || '--'} • ${identity.sourceLabel}`;
      document.getElementById('modalDeviceField').textContent = identity.name;
      document.getElementById('modalIpField').textContent = `${device.ip || '--'}${device.address_active === false ? ' (último IP; sem vínculo atual)' : ''}`;
      document.getElementById('modalSystemField').textContent = identity.os;
      document.getElementById('modalSystemField').title = os.label;
      document.getElementById('modalUserField').textContent = identity.user;
      document.getElementById('modalStatusField').textContent = status.text;
      document.getElementById('modalLatencyField').textContent = identity.latency;
      document.getElementById('modalNetworkValue').textContent = status.text;
      document.getElementById('modalNetworkValue').className = status.cls;
      document.getElementById('modalAgentValue').textContent = identity.agent;
      document.getElementById('modalPingValue').textContent = identity.latency;
      document.getElementById('modalSeenValue').textContent = timeAgo(device.seconds_ago);
      document.getElementById('modalIdentificationNotice').textContent = identity.notice;
      document.getElementById('modalIdentificationNotice').className = `identification-notice ${device.agent_online ? 'connected' : 'pending'}`;
      const agentDate = new Date(device.last_agent_seen);
      document.getElementById('modalLastAgentField').textContent = device.last_agent_seen && !Number.isNaN(agentDate.getTime()) ? agentDate.toLocaleString('pt-BR') : 'Nenhum envio registrado';
      document.getElementById('modalDeviceIdField').textContent = device.device_id || 'Identificação por IP; atualize o agente';
      document.getElementById('modalAgentIdField').textContent = device.agent_id || 'Não informado';
      document.getElementById('modalSerialField').textContent = device.serial_number || 'Não disponível';
      document.getElementById('modalMacField').textContent = (device.mac_addresses || []).join(' • ') || 'Não informado';
      document.getElementById('modalModelField').textContent = [device.manufacturer, device.model].filter(Boolean).join(' · ') || 'Não disponível';
      document.getElementById('btnDeviceHistory').disabled = !device.device_id;
      if (!refresh) document.getElementById('deviceIdentityHistory').innerHTML = '';
      const recovery = device.agent_online ? device.recovery_candidates || [] : [];
      document.getElementById('identityRecovery').hidden = !recovery.length;
      const recoverySelect = document.getElementById('identityRecoveryTarget');
      const selectedRecovery = recoverySelect.value;
      recoverySelect.innerHTML = '<option value="">Selecione o cadastro anterior</option>' + recovery.map(item => `<option value="${escapeHtml(item.device_id)}">${escapeHtml(item.name)} · ${escapeHtml(item.ip)} · ${escapeHtml(item.device_id.slice(0,8))}</option>`).join('');
      if (recovery.some(item => item.device_id === selectedRecovery)) recoverySelect.value = selectedRecovery;
      document.getElementById('modalUserLabel').textContent = device.agent_online ? 'Usuário conectado' : 'Último usuário informado';

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
      document.getElementById('modalPrintersField').textContent = !device.agent_online ? 'Aguardando agente' : Array.isArray(hw.printers) && hw.printers.length ? hw.printers.join(', ') : 'Nenhuma informada';
      document.getElementById('modalAgentField').textContent = `${device.agent_online ? 'Conectado' : 'Sem comunicação recente'} • ${device.agent_version || 'Versão não informada'}`;
      for (const [id, command] of [['btnChat', 'msg'], ['btnRestart', 'restart'], ['btnShutdown', 'shutdown']]) {
        const button = document.getElementById(id);
        button.disabled = !device.agent_online || !(device.capabilities || []).includes(command);
        button.title = !device.agent_online ? 'Agente sem comunicação recente' : button.disabled ? 'Ação não habilitada neste agente' : '';
      }
      if (!refresh) state.lastFocus = document.activeElement;
      el.deviceModalOverlay.classList.add('active');
      document.body.classList.add('modal-open');
      document.getElementById('adminContent').inert = true;
      document.getElementById('adminSidebar').inert = true;
      if (!refresh) {
        const dialog = document.getElementById('machineDialog');
        dialog.focus();
        dialog.scrollTop = 0;
      }
    }

    function setUsage(valueId, barId, pct, text) {
      document.getElementById(valueId).textContent = text;
      document.getElementById(barId).style.width = `${Math.max(0, Math.min(100, Number(pct) || 0))}%`;
    }

    async function loadDeviceHistory() {
      const deviceId = state.currentDevice?.device_id;
      if (!deviceId) return;
      const button = document.getElementById('btnDeviceHistory');
      button.disabled = true;
      const container = document.getElementById('deviceIdentityHistory');
      container.textContent = 'Consultando histórico…';
      try {
        const response = await checkedFetch(`/api/events?device_id=${encodeURIComponent(deviceId)}&limit=20`);
        const data = await response.json();
        if (state.currentDevice?.device_id !== deviceId) return;
        container.innerHTML = (data.events || []).map(event => `<article><time>${escapeHtml(new Date(event.timestamp).toLocaleString('pt-BR'))}</time><strong>${escapeHtml(event.ip || '')} · ${escapeHtml(event.status)}</strong><p>${escapeHtml(event.description)}</p></article>`).join('') || '<p>Nenhum evento registrado.</p>';
      } catch (error) {
        if (state.currentDevice?.device_id === deviceId) container.textContent = error.message;
      } finally {
        button.disabled = !state.currentDevice?.device_id;
      }
    }

    async function reconcileIdentity() {
      const device = state.currentDevice;
      const targetId = document.getElementById('identityRecoveryTarget').value;
      const target = device?.recovery_candidates?.find(item => item.device_id === targetId);
      if (!device?.device_id || !target) return showToast('Selecione o cadastro anterior.');
      if (state.organizationEditor.dirty || state.organizationEditor.saving) return showToast('Salve ou descarte a edição do cadastro antes de recuperar a identidade.');
      const location = target.organization || {};
      if (!confirm(`Vincular ${device.name} (${device.ip}) ao cadastro ${target.name} (${target.ip}, ID ${targetId})?\nSetor: ${location.department || 'Não informado'}\nSala: ${location.room || 'Não informada'}\nResponsável: ${location.responsible || 'Não informado'}\nO cadastro anterior e seu histórico serão preservados. Comandos pendentes serão encerrados.`)) return;
      const button = document.getElementById('btnReconcileIdentity');
      button.disabled = true;
      try {
        const response = await checkedFetch(`/api/inventory/${encodeURIComponent(device.device_id)}/reconcile`, {
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_device_id:targetId,expected_agent_id:device.agent_id})
        });
        const data = await response.json();
        closeModal();
        await loadDevices();
        openModal(data.device_id);
        showToast('Instalação vinculada ao cadastro anterior.');
        loadEvents();
      } catch (error) { showToast(error.message); }
      finally { button.disabled = false; }
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
      if (state.organizationEditor.saving) {
        showToast('Aguarde o cadastro terminar de salvar.');
        return;
      }
      if (state.organizationEditor.dirty && !confirm('Descartar as alterações não salvas do cadastro?')) return;
      state.organizationEditor.dirty = false;
      el.deviceModalOverlay.classList.remove('active');
      document.body.classList.remove('modal-open');
      document.getElementById('adminContent').inert = false;
      document.getElementById('adminSidebar').inert = false;
      if (state.lastFocus?.isConnected) state.lastFocus.focus();
      else document.getElementById('adminContent').focus();
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
          body: JSON.stringify({ command, message: message || '', device_id: state.currentDevice.device_id || null })
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
      const button = document.getElementById('btnScan');
      button.disabled = true;
      try {
        await checkedFetch('/api/scan', {method:'POST'});
        showToast('Varredura solicitada. Acompanhe o botão de escaneamento.');
        await loadDevices();
      } catch (error) {
        button.disabled = false;
        showToast(error.message);
      }
    }

    async function remapNetwork() {
      if (state.remapSubmitting || state.scanRunning) return;
      state.remapSubmitting = true;
      const button = document.getElementById('btnRemap');
      button.disabled = true;
      try {
        const previewResponse = await checkedFetch('/api/remap');
        const preview = await previewResponse.json();
        const message = `Remapear a rede ${preview.network}?\n\nSerão removidos ${preview.removed} registros de descoberta sem agente, incluindo ${preview.offline_removed} offline.\n${preview.kept} equipamentos que já enviaram dados pelo agente serão mantidos.\n\nOs cadastros de setor, sala e responsável e o histórico serão mantidos. Uma nova varredura será iniciada.`;
        if (!confirm(message)) return;
        const response = await checkedFetch('/api/remap', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({confirm: true})
        });
        const data = await response.json();
        updateScanState(data.scan || {});
        showToast('Remapeamento solicitado. Acompanhe o resultado na seção Dispositivos.');
        await loadDevices();
      } catch (error) {
        showToast(error.message);
      } finally {
        state.remapSubmitting = false;
        button.disabled = Boolean(state.scanRunning);
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
      const header = ['IP','Dispositivo','Sistema','Status','Usuário','Latência(ms)','Setor','Sala','Responsável','ID equipamento','UUID instalação','Número de série','MACs','Fabricante','Modelo','Vínculo IP'];
      const rows = devices.map(d => [
        d.ip || '',
        getDeviceIdentity(d).name,
        getDevicePlatform(d).detail + ' (' + getDevicePlatform(d).label + ')',
        d.online ? 'Online' : 'Offline',
        d.user || '',
        d.online && d.latency != null ? d.latency : '',
        ...ORGANIZATION_FIELDS.map(field => d.organization?.[field] || ''),
        d.device_id || '',d.agent_id || '',d.serial_number || '',(d.mac_addresses || []).join(' | '),d.manufacturer || '',d.model || '',d.address_active === false ? 'Último IP conhecido' : 'Atual'
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

    function setKioskMode(enabled) {
      if (state.kiosk === enabled) return;
      if (enabled) state.kioskPreviousView = state.currentView;
      state.kiosk = enabled;
      state.kioskFullscreen = false;
      document.body.classList.toggle('kiosk', enabled);
      document.getElementById('btnTv').setAttribute('aria-pressed', String(enabled));
      const health = document.getElementById('networkHealthPanel');
      if (enabled) document.getElementById('tvHealthSlot').appendChild(health);
      else {
        const home = document.getElementById('overviewSideStack');
        home.insertBefore(health, home.firstChild);
      }
      switchView(enabled ? 'overview' : state.kioskPreviousView);
      updateClock();
      if (enabled) document.getElementById('exitTv').focus({preventScroll: true});
      else document.getElementById('btnTv').focus({preventScroll: true});
    }

    async function toggleKiosk() {
      const enabled = !state.kiosk;
      setKioskMode(enabled);
      try {
        if (enabled && document.documentElement.requestFullscreen) {
          await document.documentElement.requestFullscreen();
          state.kioskFullscreen = state.kiosk && Boolean(document.fullscreenElement);
        } else if (!enabled && document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen();
      } catch (_) { /* O layout TV também funciona quando o navegador não permite tela cheia. */ }
      showToast(enabled ? 'Modo TV ativado.' : 'Modo TV desativado.');
      addEventLog('info', 'Modo TV', enabled ? 'Modo TV ativado.' : 'Modo TV desativado.', new Date());
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

    // Detectar mudanças de estado
    devices.forEach(device => {

        const ip = String(device.ip || '');

        if (!ip) return;

        const current = device.online === true;

        const key = deviceKey(device);
        const previous = state.previousStatus[key];

        // Na primeira leitura não dispara alerta
        if (previous === undefined) {

            state.previousStatus[key] = current;
            return;

        }

        // Estado não mudou
        if (previous === current) {
            return;
        }

        state.previousStatus[key] = current;

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
            read: !document.getElementById('notificationPanel').hidden,
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

    syncNotificationSummary();

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


function syncNotificationSummary() {
    const notifications = state.notifications || [];
    const unread = notifications.filter(notification => notification.read !== true).length;
    const badge = document.getElementById('notificationBadge');
    badge.textContent = unread > 99 ? '99+' : String(unread);
    badge.hidden = unread === 0;
    document.getElementById('btnNotifications').setAttribute('aria-label',
        unread ? `Abrir notificações (${unread} não ${unread === 1 ? 'lida' : 'lidas'})` : 'Abrir notificações');
    document.getElementById('notificationSummary').textContent = notifications.length
        ? `${notifications.length} ${notifications.length === 1 ? 'notificação' : 'notificações'} • ${unread} não ${unread === 1 ? 'lida' : 'lidas'}`
        : 'Nenhuma notificação';
}


function toggleNotifications() {
    const panel = document.getElementById('notificationPanel');
    panel.hidden = !panel.hidden;
    document.getElementById('btnNotifications').setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) {
        (state.notifications || []).forEach(notification => { notification.read = true; });
    }
    renderNotifications();
}


function clearNotifications() {
    state.notifications = [];
    renderNotifications();
    showToast('Notificações recentes limpas.');
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

        toggleNotifications();

    });

    clear.addEventListener('click', clearNotifications);

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

    const ORGANIZATION_FIELDS = ['department', 'room', 'responsible'];
    const DEVICE_PROFILE_FIELDS = [...ORGANIZATION_FIELDS, 'display_name', 'platform'];
    const ORGANIZATION_LABELS = { department: 'Setor', room: 'Sala', responsible: 'Responsável' };
    const ORGANIZATION_INPUTS = { department: 'organizationDepartment', room: 'organizationRoom', responsible: 'organizationResponsible', display_name: 'organizationDisplayName', platform: 'organizationPlatform' };
    const ORGANIZATION_FILTERS = { department: 'filterDepartment', room: 'filterRoom', responsible: 'filterResponsible' };

    function normalizeSearch(value) {
      return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
    }

    function matchesOrganizationFilter(value, selection) {
      if (!selection) return true;
      if (selection === 'unassigned') return !value;
      return normalizeSearch(value) === normalizeSearch(selection.slice(6));
    }

    function updateOrganizationFilters() {
      for (const field of ORGANIZATION_FIELDS) {
        const selected = state.organizationFilters[field];
        const values = new Set(state.devices.map(device => device.organization?.[field] || '').filter(Boolean));
        if (selected.startsWith('value:')) values.add(selected.slice(6));
        const options = [...values].sort((a, b) => a.localeCompare(b, 'pt-BR'));
        const select = document.getElementById(ORGANIZATION_FILTERS[field]);
        select.innerHTML = `<option value="">Todos — ${ORGANIZATION_LABELS[field]}</option><option value="unassigned">Não informado</option>` +
          options.map(value => `<option value="value:${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
        select.value = selected;
      }
    }

    function groupDevices(devices, field) {
      if (!ORGANIZATION_FIELDS.includes(field)) return [{ label: '', devices }];
      const groups = new Map();
      for (const device of devices) {
        const value = device.organization?.[field] || '';
        const key = normalizeSearch(value);
        if (!groups.has(key)) groups.set(key, { label: value || `${ORGANIZATION_LABELS[field]} não informado`, devices: [] });
        groups.get(key).devices.push(device);
      }
      return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'));
    }

    async function saveOrganization(event) {
      event.preventDefault();
      const editor = state.organizationEditor;
      if (!editor.ip || editor.saving) return;
      const ip = editor.ip;
      const payload = { expected_updated_at: editor.revision };
      for (const field of DEVICE_PROFILE_FIELDS) payload[field] = document.getElementById(ORGANIZATION_INPUTS[field]).value;
      const status = document.getElementById('organizationSaveStatus');
      editor.saving = true;
      document.getElementById('organizationFieldset').disabled = true;
      status.textContent = 'Salvando…';
      try {
        const response = await checkedFetch(`/api/devices/${encodeURIComponent(ip)}/organization`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        const data = await response.json();
        const device = state.devices.find(item => deviceKey(item) === ip);
        if (device) device.organization = data.organization;
        editor.revision = data.organization.updated_at;
        editor.dirty = false;
        for (const field of DEVICE_PROFILE_FIELDS) document.getElementById(ORGANIZATION_INPUTS[field]).value = data.organization[field] || '';
        updateOrganizationFilters();
        renderAll();
        status.textContent = 'Cadastro salvo';
        showToast('Identificação e cadastro salvos.');
        loadEvents();
      } catch (error) {
        status.textContent = error.message;
        showToast(error.message);
      } finally {
        editor.saving = false;
        document.getElementById('organizationFieldset').disabled = false;
      }
    }

    const PREMIUM_ICONS = new Set(["grid", "monitor", "network", "history", "report", "search", "scan", "download", "bell", "menu", "close", "arrow", "logout", "sun", "list", "sound", "check", "clock", "pulse", "shield", "copy", "message", "power", "refresh", "pin", "cpu", "memory", "disk", "printer", "user", "filter", "globe", "alert"]);
    function uiIcon(name) {
      const safe = PREMIUM_ICONS.has(name) ? name : 'monitor';
      return `<svg class="sti-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="/static/icons/sti.svg#${safe}"></use></svg>`;
    }
    const metricAnimations = new Map();
    function animateMetric(id, target, suffix = '') {
      const element = document.getElementById(id);
      const start = Number.parseFloat(element.textContent) || 0;
      const previous = metricAnimations.get(id);
      if (previous && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(previous);
      if (target == null) {
        element.textContent = '—';
        metricAnimations.delete(id);
        return;
      }
      const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      if (reduced || typeof requestAnimationFrame !== 'function' || start === target) {
        element.textContent = `${target}${suffix}`;
        metricAnimations.delete(id);
        return;
      }
      const started = performance.now();
      const frame = now => {
        const progress = Math.min((now - started) / 650, 1);
        element.textContent = `${Math.round(start + (target - start) * (1 - (1 - progress) ** 3))}${suffix}`;
        if (progress < 1) metricAnimations.set(id, requestAnimationFrame(frame));
        else metricAnimations.delete(id);
      };
      metricAnimations.set(id, requestAnimationFrame(frame));
    }
    function matchesStatus(device, status) {
      if (status === 'online') return device.online === true;
      if (status === 'offline') return device.online === false;
      if (status === 'attention') return device.online === true && Number(device.latency || 0) > 100;
      return true;
    }
    function syncStatusFilters() {
      document.querySelectorAll('[data-status]').forEach(button => {
        const active = button.dataset.status === state.statusFilter;
        button.setAttribute('aria-pressed', String(active));
        button.classList.toggle('selected', active);
        if (button.classList.contains('legend-pill')) button.classList.toggle('active', active);
      });
    }
    function setStatusFilter(status) {
      if (state.kiosk) return;
      state.statusFilter = ['all','online','offline','attention'].includes(status) ? status : 'all';
      syncStatusFilters();
      renderDevices();
    }
    function toggleMobileNav(open) {
      document.getElementById('adminSidebar').classList.toggle('is-open', open);
      document.getElementById('navBackdrop').hidden = !open;
      document.getElementById('btnMobileNav').setAttribute('aria-expanded', String(open));
    }
    function updateSyncStatus(connected) {
      state.connected = connected;
      const badge = document.getElementById('syncStatus');
      badge.classList.toggle('disconnected', !connected);
      badge.textContent = connected ? 'Atualizado às ' + new Date().toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit'}) : 'Sem atualização';
    }
    function installCardSpotlight() {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !window.matchMedia('(pointer: fine)').matches) return;
      let scheduled = false, lastEvent;
      el.devicesGrid.addEventListener('pointermove', event => {
        lastEvent = event;
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
          scheduled = false;
          const card = lastEvent.target.closest('.device-card');
          if (!card || !card.isConnected) return;
          const bounds = card.getBoundingClientRect();
          card.style.setProperty('--spot-x', `${lastEvent.clientX - bounds.left}px`);
          card.style.setProperty('--spot-y', `${lastEvent.clientY - bounds.top}px`);
        });
      });
    }
    function handlePremiumKeys(event) {
      if (el.deviceModalOverlay.classList.contains('active')) {
        if (event.key === 'Escape') { event.preventDefault(); closeModal(); }
        if (event.key === 'Tab') {
          const elements = [...document.getElementById('machineDialog').querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href],textarea:not(:disabled)')].filter(item => item.offsetParent !== null);
          const first = elements[0], last = elements[elements.length-1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement.id === 'machineDialog')) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
        return;
      }
      if (state.kiosk) {
        if (event.key === 'Escape' && !document.fullscreenElement) {
          event.preventDefault();
          setKioskMode(false);
        }
        return;
      }
      if (event.key === 'Escape') toggleMobileNav(false);
      if (event.key === '/' && !event.ctrlKey && !event.metaKey && !['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName) && !event.target.isContentEditable) {
        event.preventDefault();
        el.searchInput.focus();
      }
    }

    function updateScanState(scan) {
      const button = document.getElementById('btnScan');
      const remapButton = document.getElementById('btnRemap');
      if (!state.scanMarkup) state.scanMarkup = button.innerHTML;
      if (!state.remapMarkup) state.remapMarkup = remapButton.innerHTML;
      const scanning = scan.scanning === true;
      state.scanRunning = scanning;
      button.disabled = scanning;
      remapButton.disabled = scanning || Boolean(state.remapSubmitting);
      remapButton.innerHTML = scan.remapping ? `${uiIcon('refresh')} Remapeando…` : state.remapMarkup;
      button.classList.toggle('is-scanning', scanning);
      button.innerHTML = scanning ? `${uiIcon('scan')}<span>Escaneando…</span>` : state.scanMarkup;
      button.title = scanning ? `Verificando ${Number(scan.progress) || 0} de ${Number(scan.total) || 0} endereços` : 'Escanear rede';
      if (scan.discovery_generation !== undefined) {
        if (state.discoveryGeneration !== undefined && state.discoveryGeneration !== scan.discovery_generation) {
          for (const device of state.devices) {
            if (!device.device_id && device.identification_source !== 'agent' && !Object.keys(device.hw || {}).length) {
              delete state.previousStatus[deviceKey(device)];
            }
          }
        }
        state.discoveryGeneration = scan.discovery_generation;
      }
      const feedback = document.getElementById('remapStatus');
      const remap = scan.last_remap;
      feedback.hidden = !remap;
      if (remap) {
        if (remap.status === 'completed') feedback.textContent = `Remapeamento concluído. ${remap.removed} registros sem agente removidos e nova varredura finalizada.`;
        else if (remap.status === 'error') feedback.textContent = scan.error || 'Não foi possível concluir o remapeamento. Tente escanear novamente.';
        else if (remap.status === 'queued') feedback.textContent = 'Preparando o remapeamento da rede…';
        else feedback.textContent = `Remapeamento em andamento. ${remap.removed} registros sem agente removidos. Verificando ${scan.progress || 0} de ${scan.total || 0} endereços.`;
      }
    }

    init();
