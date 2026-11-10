/* Áudio pessoal do painel. O arquivo fica no IndexedDB deste navegador. */
function positionSoundPanel() {
  const panel = document.getElementById('soundSettingsPanel');
  if (panel.hidden) return;
  const button = document.getElementById('btnSound').getBoundingClientRect();
  const size = panel.getBoundingClientRect();
  panel.style.left = `${Math.max(16, Math.min(button.right - size.width, window.innerWidth - size.width - 16))}px`;
  panel.style.top = `${Math.max(16, Math.min(button.bottom + 12, window.innerHeight - size.height - 16))}px`;
}

function closeSoundPanel(focus = false) {
  document.getElementById('soundSettingsPanel').hidden = true;
  const button = document.getElementById('btnSound');
  button.setAttribute('aria-expanded', 'false');
  if (focus) button.focus();
}

function initAlertSoundControls() {
  const button = document.getElementById('btnSound');
  const panel = document.getElementById('soundSettingsPanel');
  button.addEventListener('click', () => {
    if (!panel.hidden) return closeSoundPanel(true);
    panel.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    positionSoundPanel();
    panel.focus();
  });
  document.getElementById('closeSoundSettings').addEventListener('click', () => closeSoundPanel(true));
  document.getElementById('alertSoundFile').addEventListener('change', chooseAlertSound);
  document.getElementById('btnChooseAlertSound').addEventListener('click', () => document.getElementById('alertSoundFile').click());
  document.getElementById('alertSoundVolume').addEventListener('input', changeAlertVolume);
  document.getElementById('btnToggleAlertSound').addEventListener('click', toggleSound);
  document.getElementById('btnTestAlertSound').addEventListener('click', testAlertSound);
  document.getElementById('btnResetAlertSound').addEventListener('click', resetAlertSound);
  document.addEventListener('click', event => {
    if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) closeSoundPanel();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); closeSoundPanel(true); }
  });
  window.addEventListener('resize', positionSoundPanel);
}

function soundStore(operation, file = null) {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') return reject(new Error('Armazenamento local indisponível.'));
    const opening = indexedDB.open('sti-panel-audio', 1);
    opening.onupgradeneeded = () => opening.result.createObjectStore('sounds');
    opening.onerror = () => reject(opening.error);
    opening.onblocked = () => reject(new Error('Armazenamento ocupado por outra aba.'));
    opening.onsuccess = () => {
      const db = opening.result;
      try {
        const transaction = db.transaction('sounds', operation === 'get' ? 'readonly' : 'readwrite');
        const store = transaction.objectStore('sounds');
        const request = operation === 'get' ? store.get('alert') : operation === 'delete' ? store.delete('alert') : store.put(file, 'alert');
        transaction.oncomplete = () => { db.close(); resolve(request.result); };
        transaction.onabort = transaction.onerror = () => { db.close(); reject(transaction.error || new Error('Não foi possível salvar o áudio.')); };
      } catch (error) { db.close(); reject(error); }
    };
  });
}

function syncSoundControls() {
  const enabled = state.soundEnabled;
  const playing = Boolean(state.soundSources?.length);
  const button = document.getElementById('btnSound');
  button.classList.toggle('active', enabled);
  button.setAttribute('aria-pressed', String(enabled));
  button.setAttribute('aria-label', `Configurar som dos alertas (${enabled ? 'ativado' : 'desativado'})`);
  document.getElementById('btnToggleAlertSound').textContent = enabled ? 'Desativar alertas sonoros' : 'Ativar alertas sonoros';
  document.getElementById('btnToggleAlertSound').setAttribute('aria-pressed', String(enabled));
  document.getElementById('btnTestAlertSound').textContent = playing ? 'Parar som' : 'Testar som';
  document.getElementById('alertSoundName').textContent = state.soundName || 'Som padrão do STI';
  document.getElementById('alertSoundVolume').value = state.soundVolume;
  document.getElementById('alertSoundVolumeValue').textContent = `${state.soundVolume}%`;
  for (const id of ['alertSoundFile', 'btnChooseAlertSound', 'btnToggleAlertSound', 'btnTestAlertSound', 'btnResetAlertSound']) {
    document.getElementById(id).disabled = Boolean(state.soundLoading);
  }
  if (document.getElementById('soundSettingsPanel').hidden === false) positionSoundPanel();
}

function soundContext() {
  if (!state.audioCtx) {
    const Constructor = window.AudioContext || window.webkitAudioContext;
    if (!Constructor) throw new Error('Áudio não suportado neste navegador.');
    state.audioCtx = new Constructor();
  }
  return state.audioCtx;
}

async function decodeAlertSound(file) {
  if (!file || !/\.(mp3|wav|ogg|m4a)$/i.test(file.name || '')) throw new Error('Escolha um arquivo MP3, WAV, OGG ou M4A.');
  if (!file.size || file.size > 10 * 1024 * 1024) throw new Error('O arquivo deve ter conteúdo e até 10 MB.');
  let buffer;
  try { buffer = await soundContext().decodeAudioData(await file.arrayBuffer()); }
  catch (_) { throw new Error('Não foi possível ler este áudio. Escolha um arquivo válido e compatível com o navegador.'); }
  if (!Number.isFinite(buffer.duration) || buffer.duration <= 0) throw new Error('O arquivo de áudio está vazio ou inválido.');
  return buffer;
}

async function initSoundSettings() {
  state.soundVolume = 70;
  try {
    const saved = localStorage.getItem('sti-alert-volume');
    if (saved !== null && Number.isFinite(Number(saved))) state.soundVolume = Math.max(0, Math.min(100, Number(saved)));
  } catch (_) { /* Preferência em memória quando o armazenamento estiver bloqueado. */ }
  state.soundLoading = true;
  syncSoundControls();
  try {
    const file = await soundStore('get');
    if (file) {
      state.soundBuffer = await decodeAlertSound(file);
      state.soundName = file.name;
      document.getElementById('alertSoundStatus').textContent = 'Áudio salvo neste navegador. Ative os alertas ao abrir o painel.';
    }
  } catch (_) {
    document.getElementById('alertSoundStatus').textContent = 'Você pode escolher um áudio para esta sessão. Não foi possível carregar o armazenamento local.';
  } finally {
    state.soundLoading = false;
    syncSoundControls();
  }
}

async function chooseAlertSound(event) {
  const input = event.target;
  const file = input.files?.[0];
  if (!file || state.soundLoading) return;
  state.soundLoading = true;
  syncSoundControls();
  const status = document.getElementById('alertSoundStatus');
  status.textContent = 'Preparando áudio…';
  try {
    const buffer = await decodeAlertSound(file);
    stopAlertSound();
    state.soundBuffer = buffer;
    state.soundName = file.name;
    try {
      await soundStore('put', file);
      status.textContent = 'Áudio salvo neste navegador. Use “Testar som” para ouvir.';
    } catch (_) {
      status.textContent = 'Áudio pronto para esta sessão. O navegador não permitiu salvá-lo para a próxima visita.';
    }
  } catch (error) {
    status.textContent = error.message;
    showToast(error.message);
  } finally {
    input.value = '';
    state.soundLoading = false;
    syncSoundControls();
  }
}

function stopAlertSound() {
  const sources = state.soundSources || [];
  state.soundSources = [];
  for (const source of sources) {
    source.onended = null;
    try { source.stop(); } catch (_) { /* Fonte já encerrada. */ }
    source.disconnect();
  }
  state.soundGain?.disconnect();
  state.soundGain = null;
  syncSoundControls();
}

function playAlert(preview = false) {
  if ((!state.soundEnabled && !preview) || !state.audioCtx || state.audioCtx.state !== 'running') return;
  stopAlertSound();
  const context = state.audioCtx, now = context.currentTime;
  const master = context.createGain();
  master.gain.setValueAtTime((state.soundVolume ?? 70) / 100, now);
  master.connect(context.destination);
  state.soundGain = master;
  const track = source => {
    state.soundSources.push(source);
    source.onended = () => {
      source.disconnect();
      state.soundSources = state.soundSources.filter(item => item !== source);
      if (!state.soundSources.length) { master.disconnect(); state.soundGain = null; }
      syncSoundControls();
    };
  };
  if (state.soundBuffer) {
    const source = context.createBufferSource();
    source.buffer = state.soundBuffer;
    source.connect(master);
    track(source);
    source.start(now, 0, Math.min(10, state.soundBuffer.duration));
  } else {
    [0, .42].forEach(delay => {
      const oscillator = context.createOscillator(), gain = context.createGain();
      oscillator.connect(gain); gain.connect(master);
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(740, now + delay);
      oscillator.frequency.setValueAtTime(880, now + delay + .13);
      gain.gain.setValueAtTime(.0001, now + delay);
      gain.gain.linearRampToValueAtTime(.18, now + delay + .025);
      gain.gain.exponentialRampToValueAtTime(.0001, now + delay + .35);
      track(oscillator);
      oscillator.start(now + delay); oscillator.stop(now + delay + .36);
      const ended = oscillator.onended;
      oscillator.onended = () => { gain.disconnect(); ended(); };
    });
  }
  syncSoundControls();
}

async function toggleSound() {
  if (state.soundLoading) return;
  if (state.soundEnabled) {
    state.soundEnabled = false;
    stopAlertSound();
    showToast('Alerta sonoro desativado.');
  } else {
    try {
      await enableAudioContext();
      state.soundEnabled = true;
      playAlert();
      showToast('Alertas sonoros ativados. Som de teste reproduzido.');
    } catch (error) {
      state.soundEnabled = false;
      showToast('Não foi possível ativar o áudio: ' + error.message);
    }
  }
  syncSoundControls();
}

async function testAlertSound() {
  if (state.soundLoading) return;
  if (state.soundSources?.length) return stopAlertSound();
  try { await enableAudioContext(); playAlert(true); }
  catch (error) { showToast('Não foi possível testar o áudio: ' + error.message); }
}

async function resetAlertSound() {
  if (state.soundLoading) return;
  state.soundLoading = true;
  stopAlertSound();
  state.soundBuffer = null; state.soundName = '';
  const status = document.getElementById('alertSoundStatus');
  try {
    await soundStore('delete');
    status.textContent = 'Som padrão restaurado.';
  } catch (_) {
    status.textContent = 'Som padrão aplicado nesta sessão. Não foi possível remover o áudio salvo para a próxima visita.';
  } finally {
    state.soundLoading = false;
    syncSoundControls();
  }
}

function changeAlertVolume(event) {
  state.soundVolume = Math.max(0, Math.min(100, Number(event.target.value) || 0));
  state.soundGain?.gain.setValueAtTime(state.soundVolume / 100, state.audioCtx.currentTime);
  try { localStorage.setItem('sti-alert-volume', String(state.soundVolume)); } catch (_) { /* Preferência apenas nesta sessão. */ }
  syncSoundControls();
}
