(() => {
  const nativeStartTimeoutMs = 7000;
  const ASR_MODES = ['local_whisper', 'openai_chat'];
  const TRANSLATION_MODES = ['bing_web', 'azure_translator', 'openai_chat'];

  Object.assign(I18N['zh-CN'], {
    customSettings:'自定义设置', customSettingsHint:'以下参数都有可直接使用的默认值。修改后会保存到本地配置，下次启动自动恢复。',
    outputMode:'输出模式', sentenceMode:'整句模式', realtimeMode:'实时模式 · Experimental',
    translationSettings:'语言与翻译', contextSegments:'上下文片段数', preserveTerms:'保护学术术语',
    speechSegmentation:'语音检测与分段', speechThreshold:'语音触发阈值', silenceEnd:'停顿结束阈值 (ms)', minSpeech:'最短语音长度 (ms)', maxSegment:'最长语音片段 (ms)', preRoll:'前置音频保留 (ms)',
    realtimeSettings:'实时模式', realtimeSettingsHint:'实时模式使用增量 ASR 和节流后的增量翻译。数值越小延迟越低，但本地推理和网络请求会更频繁。', realtimeMinAudio:'首次增量识别等待 (ms)', partialInterval:'ASR 更新间隔 (ms)', partialTranslationInterval:'翻译更新间隔 (ms)',
    captureStorage:'采集与保存', audioFormat:'音频格式', screenshotMonitor:'截图显示器编号', livePartial:'实时识别中'
  });
  Object.assign(I18N.en, {
    customSettings:'Custom settings', customSettingsHint:'Every option has a usable default. Changes are stored in the local config and restored on the next launch.',
    outputMode:'Output mode', sentenceMode:'Sentence mode', realtimeMode:'Realtime · Experimental',
    translationSettings:'Language & translation', contextSegments:'Context segments', preserveTerms:'Preserve academic terms',
    speechSegmentation:'Speech detection & segmentation', speechThreshold:'Speech threshold', silenceEnd:'Silence endpoint (ms)', minSpeech:'Minimum speech (ms)', maxSegment:'Maximum segment (ms)', preRoll:'Pre-roll audio (ms)',
    realtimeSettings:'Realtime mode', realtimeSettingsHint:'Realtime mode uses incremental ASR and throttled incremental translation. Lower values reduce latency but increase local inference and network requests.', realtimeMinAudio:'First partial after (ms)', partialInterval:'ASR update interval (ms)', partialTranslationInterval:'Translation update interval (ms)',
    captureStorage:'Capture & storage', audioFormat:'Audio format', screenshotMonitor:'Screenshot monitor', livePartial:'Live recognition'
  });

  state.livePartial = null;

  function renderPartialUi() {
    const partial = state.livePartial;
    const original = $('originalList');
    const translation = $('translationList');
    original?.querySelectorAll('.partial-segment').forEach(node => node.remove());
    translation?.querySelectorAll('.partial-segment').forEach(node => node.remove());

    if (partial && original && translation) {
      original.classList.remove('empty');
      translation.classList.remove('empty');
      if (!state.session?.segments?.length) {
        original.textContent = '';
        translation.textContent = '';
      }
      const stamp = fmt(partial.start_ms || 0);
      original.insertAdjacentHTML('beforeend', `<div class="segment partial-segment"><small>${stamp} · ${esc(tr('livePartial'))}</small>${esc(partial.source || '…')}</div>`);
      translation.insertAdjacentHTML('beforeend', `<div class="segment partial-segment"><small>${stamp} · ${esc(tr('livePartial'))}</small>${esc(partial.translation || '…')}</div>`);
      if (state.autoFollow) {
        requestAnimationFrame(() => {
          original.scrollTop = original.scrollHeight;
          translation.scrollTop = translation.scrollHeight;
        });
      }
    }

    if (floatingWindowIsOpen()) {
      const list = state.floatingWindow.document.querySelector('[data-role="floating-list"]');
      list?.querySelectorAll('[data-partial="true"]').forEach(node => node.remove());
      if (partial && list) {
        const row = state.floatingWindow.document.createElement('div');
        row.className = 'row partial-row';
        row.dataset.partial = 'true';
        const stamp = fmt(partial.start_ms || 0);
        row.innerHTML = `<div class="cell"><small class="time">${stamp} · ${esc(tr('livePartial'))}</small>${esc(partial.source || '…')}</div><div class="cell"><small class="time">${stamp} · ${esc(tr('livePartial'))}</small>${esc(partial.translation || '…')}</div>`;
        list.appendChild(row);
        if (state.floatingAutoFollow) list.scrollTop = list.scrollHeight;
      }
    }
  }

  const baseRenderSession = renderSession;
  renderSession = function renderSessionBeta08(options = {}) {
    baseRenderSession(options);
    renderPartialUi();
  };

  // Final ASR remains a durable session segment. Realtime partials are visual-only
  // and are replaced by the final segment once the endpoint is reached.
  const baseHandleWs = handleWs;
  handleWs = function handleWsBeta08(event) {
    let message = null;
    try { message = JSON.parse(event.data); } catch {}

    if (message?.type === 'partial' && state.session) {
      state.livePartial = { ...(state.livePartial || {}), ...(message.partial || {}) };
      renderPartialUi();
      return;
    }

    if (message?.type === 'segment') {
      state.livePartial = null;
      baseHandleWs(event);
      return;
    }

    if (message?.type === 'segment_update' && state.session) {
      const updated = message.segment;
      const index = state.session.segments.findIndex(seg => seg.id === updated?.id);
      if (index >= 0) state.session.segments[index] = updated;
      else if (updated) state.session.segments.push(updated);
      renderSession();
      return;
    }

    if (message?.type === 'stopped') {
      state.livePartial = null;
      renderPartialUi();
    }

    baseHandleWs(event);
  };

  const clone = value => structuredClone(value);

  function defaultAsrProfile(mode) {
    if (mode === 'openai_chat') {
      return {
        name: 'OpenAI-compatible ASR', mode: 'openai_chat',
        base_url: 'http://127.0.0.1:8080/v1', api_key: '', model: '', endpoint: null,
        timeout_seconds: 120, temperature: 0, max_tokens: 4096,
        device: 'auto', compute_type: 'auto', region: ''
      };
    }
    return {
      name: 'Local Whisper', mode: 'local_whisper', base_url: '', api_key: '',
      model: 'base', endpoint: null, timeout_seconds: 120, temperature: 0,
      max_tokens: 4096, device: 'auto', compute_type: 'auto', region: ''
    };
  }

  function defaultTranslationProfile(mode) {
    if (mode === 'azure_translator') {
      return {
        name: 'Microsoft Translator', mode, base_url: 'https://api.cognitive.microsofttranslator.com',
        api_key: '', model: 'translator-v3', endpoint: null, timeout_seconds: 120,
        temperature: 0, max_tokens: 4096, device: 'auto', compute_type: 'auto', region: ''
      };
    }
    if (mode === 'openai_chat') {
      return {
        name: 'OpenAI-compatible Translation', mode, base_url: '', api_key: '', model: '',
        endpoint: null, timeout_seconds: 120, temperature: 0, max_tokens: 4096,
        device: 'auto', compute_type: 'auto', region: ''
      };
    }
    return {
      name: 'Bing Translate (Free)', mode: 'bing_web', base_url: '', api_key: '',
      model: 'bing', endpoint: null, timeout_seconds: 120, temperature: 0,
      max_tokens: 4096, device: 'auto', compute_type: 'auto', region: ''
    };
  }

  function ensureProviderProfiles(config) {
    config.providers = config.providers || {};
    const p = config.providers;
    p.asr = p.asr || {};
    p.translation = p.translation || {};

    const currentAsrMode = ASR_MODES.includes(config.asr?.mode) ? config.asr.mode : 'local_whisper';
    const currentTranslationMode = TRANSLATION_MODES.includes(config.translation?.mode)
      ? config.translation.mode : 'bing_web';

    p.active_asr = ASR_MODES.includes(p.active_asr) ? p.active_asr : currentAsrMode;
    p.active_translation = TRANSLATION_MODES.includes(p.active_translation)
      ? p.active_translation : currentTranslationMode;

    for (const mode of ASR_MODES) {
      if (!p.asr[mode]) {
        p.asr[mode] = currentAsrMode === mode && config.asr
          ? clone(config.asr) : defaultAsrProfile(mode);
      }
      p.asr[mode].mode = mode;
    }

    for (const mode of TRANSLATION_MODES) {
      if (!p.translation[mode]) {
        p.translation[mode] = currentTranslationMode === mode && config.translation
          ? clone(config.translation) : defaultTranslationProfile(mode);
      }
      p.translation[mode].mode = mode;
    }
    return p;
  }

  function readAsrProfile(mode) {
    const p = ensureProviderProfiles(state.config);
    const profile = clone(p.asr[mode] || defaultAsrProfile(mode));
    profile.mode = mode;

    if (mode === 'local_whisper') {
      profile.model = $('asrModel').value;
      profile.device = $('asrDevice').value;
      profile.compute_type = $('asrCompute').value || 'auto';
    } else {
      profile.model = $('asrModelRemote').value.trim();
      profile.base_url = $('asrBaseUrl').value.trim();
      profile.api_key = $('asrApiKey').value;
    }
    return profile;
  }

  function writeAsrProfile(mode) {
    const p = ensureProviderProfiles(state.config);
    const profile = p.asr[mode] || defaultAsrProfile(mode);
    $('asrMode').value = mode;

    if (mode === 'local_whisper') {
      const localModels = ['tiny', 'base', 'small', 'medium', 'large-v3-turbo'];
      $('asrModel').value = localModels.includes(profile.model) ? profile.model : 'base';
      if ([...$('asrDevice').options].some(option => option.value === (profile.device || 'auto'))) {
        $('asrDevice').value = profile.device || 'auto';
      }
      $('asrCompute').value = profile.compute_type || 'auto';
    } else {
      $('asrModelRemote').value = profile.model || '';
      $('asrBaseUrl').value = profile.base_url || '';
      $('asrApiKey').value = profile.api_key || '';
    }

    state.config.asr = clone(profile);
  }

  function readTranslationProfile(mode) {
    const p = ensureProviderProfiles(state.config);
    const profile = clone(p.translation[mode] || defaultTranslationProfile(mode));
    profile.mode = mode;

    if (mode === 'openai_chat') {
      profile.base_url = $('mtBaseUrl').value.trim();
      profile.model = $('mtModel').value.trim();
      profile.api_key = $('mtApiKey').value;
    } else if (mode === 'azure_translator') {
      profile.base_url = 'https://api.cognitive.microsofttranslator.com';
      profile.model = 'translator-v3';
      profile.api_key = $('mtAzureKey').value;
      profile.region = $('mtRegion').value.trim();
    } else {
      profile.model = 'bing';
    }
    return profile;
  }

  function writeTranslationProfile(mode) {
    const p = ensureProviderProfiles(state.config);
    const profile = p.translation[mode] || defaultTranslationProfile(mode);
    $('mtMode').value = mode;

    if (mode === 'openai_chat') {
      $('mtBaseUrl').value = profile.base_url || '';
      $('mtModel').value = profile.model || '';
      $('mtApiKey').value = profile.api_key || '';
    } else if (mode === 'azure_translator') {
      $('mtAzureKey').value = profile.api_key || '';
      $('mtRegion').value = profile.region || '';
    }

    state.config.translation = clone(profile);
  }

  function updateProviderBadges() {
    if (!state.config) return;
    $('asrMini').textContent = `${state.config.asr.name} · ${state.config.asr.model}`;
    $('mtMini').textContent = `${state.config.translation.name} · ${state.config.translation.model}`;
  }

  function restoreProviderUi(config) {
    const p = ensureProviderProfiles(config);
    state._activeAsrMode = p.active_asr;
    state._activeTranslationMode = p.active_translation;
    writeAsrProfile(p.active_asr);
    writeTranslationProfile(p.active_translation);
    providerUI();
    updateProviderBadges();
  }

  function restoreCustomSettings(config) {
    const live = config.live || {};
    const academic = config.academic || {};
    const capture = config.capture || {};
    $('liveOutputMode').value = live.output_mode || 'sentence';
    $('speechThreshold').value = live.speech_threshold ?? 0.010;
    $('preRollMs').value = live.pre_roll_ms ?? 220;
    $('realtimeMinAudioMs').value = live.realtime_min_audio_ms ?? 900;
    $('partialIntervalMs').value = live.partial_interval_ms ?? 1000;
    $('partialTranslationIntervalMs').value = live.partial_translation_interval_ms ?? 1800;
    $('contextSegments').value = academic.context_segments ?? 1;
    $('preserveAcademicTerms').value = String(academic.preserve_academic_terms ?? true);
    $('screenshotMonitor').value = capture.screenshot_monitor ?? 1;
    if ($('liveSourceLanguage')) $('liveSourceLanguage').value = academic.source_language || 'auto';
    if ($('liveTargetLanguage')) $('liveTargetLanguage').value = academic.target_language || 'Chinese';
  }

  function restoreBeta08Ui(config) {
    restoreProviderUi(config);
    restoreCustomSettings(config);
    applyLanguage(config.interface?.language || 'zh-CN');
  }

  function switchAsrProfile() {
    if (!state.config) return providerUI();
    const p = ensureProviderProfiles(state.config);
    const next = $('asrMode').value;
    const previous = state._activeAsrMode || p.active_asr;

    if (ASR_MODES.includes(previous) && previous !== next) {
      p.asr[previous] = readAsrProfile(previous);
    }
    p.active_asr = next;
    state._activeAsrMode = next;
    writeAsrProfile(next);
    providerUI();
    updateProviderBadges();
  }

  function switchTranslationProfile() {
    if (!state.config) return providerUI();
    const p = ensureProviderProfiles(state.config);
    const next = $('mtMode').value;
    const previous = state._activeTranslationMode || p.active_translation;

    if (TRANSLATION_MODES.includes(previous) && previous !== next) {
      p.translation[previous] = readTranslationProfile(previous);
    }
    p.active_translation = next;
    state._activeTranslationMode = next;
    writeTranslationProfile(next);
    providerUI();
    updateProviderBadges();
  }

  function captureCurrentProviderProfiles() {
    const p = ensureProviderProfiles(state.config);
    const asrMode = ASR_MODES.includes($('asrMode').value) ? $('asrMode').value : p.active_asr;
    const translationMode = TRANSLATION_MODES.includes($('mtMode').value)
      ? $('mtMode').value : p.active_translation;

    p.active_asr = asrMode;
    p.asr[asrMode] = readAsrProfile(asrMode);
    p.active_translation = translationMode;
    p.translation[translationMode] = readTranslationProfile(translationMode);
    state._activeAsrMode = asrMode;
    state._activeTranslationMode = translationMode;
  }

  const baseLoadConfig = loadConfig;
  loadConfig = async function loadConfigBeta08() {
    const config = await baseLoadConfig();
    restoreBeta08Ui(config);
    return config;
  };

  const baseFormConfig = formConfig;
  formConfig = function formConfigBeta08() {
    captureCurrentProviderProfiles();
    const c = baseFormConfig();
    const p = ensureProviderProfiles(state.config);
    c.providers = clone(p);
    c.asr = clone(p.asr[p.active_asr]);
    c.translation = clone(p.translation[p.active_translation]);
    c.live.output_mode = $('liveOutputMode').value || 'sentence';
    c.live.speech_threshold = Number($('speechThreshold').value) || 0.010;
    c.live.pre_roll_ms = Number($('preRollMs').value) || 0;
    c.live.realtime_min_audio_ms = Number($('realtimeMinAudioMs').value) || 900;
    c.live.partial_interval_ms = Number($('partialIntervalMs').value) || 1000;
    c.live.partial_translation_interval_ms = Number($('partialTranslationIntervalMs').value) || 1800;
    c.academic.context_segments = Number($('contextSegments').value) || 0;
    c.academic.preserve_academic_terms = $('preserveAcademicTerms').value === 'true';
    c.capture.screenshot_monitor = Math.max(1, Number($('screenshotMonitor').value) || 1);
    return c;
  };

  const baseSaveConfig = saveConfig;
  saveConfig = async function saveConfigBeta08() {
    await baseSaveConfig();
    restoreCustomSettings(state.config);
  };

  const baseSyncLive = syncLive;
  syncLive = async function syncLiveBeta08() {
    await ensureConfigLoaded();
    state.config.live.output_mode = $('liveOutputMode').value || 'sentence';
    await baseSyncLive();
  };

  $('asrMode').onchange = switchAsrProfile;
  $('mtMode').onchange = switchTranslationProfile;
  $('liveOutputMode').onchange = () => {
    if (state.config) state.config.live.output_mode = $('liveOutputMode').value;
  };

  startNative = async function startNativeBeta08() {
    const dev = $('nativeDevice').value;
    if (!dev) throw new Error(tr('noAudioDevice'));

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(
      `${proto}://${location.host}/ws/native?session_id=${state.session.id}&source=${$('audioSource').value}&device=${dev}`
    );
    state.ws = ws;

    await new Promise((resolve, reject) => {
      let settled = false;
      const timeout = setTimeout(() => {
        fail(new Error(
          state.language === 'en'
            ? 'Windows audio device did not open in time. Try another WASAPI device or check Windows audio settings.'
            : 'Windows 原生音频设备未能及时打开。请尝试其他 WASAPI 设备，或检查 Windows 音频设置。'
        ));
      }, nativeStartTimeoutMs);

      function finish() {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        resolve();
      }

      function fail(error) {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        try { ws.close(); } catch {}
        if (state.ws === ws) state.ws = null;
        reject(error);
      }

      ws.onmessage = event => {
        let message = null;
        try { message = JSON.parse(event.data); } catch {}

        if (message?.type === 'error' && message?.stage !== 'translation') {
          fail(new Error(message.message || tr('failed')));
          return;
        }

        handleWs(event);
        if (message?.type === 'ready') finish();
      };

      ws.onerror = () => fail(new Error(
        state.language === 'en'
          ? 'Windows microphone WebSocket failed.'
          : 'Windows 原生麦克风连接失败。'
      ));

      ws.onclose = () => {
        if (!settled) {
          fail(new Error(
            state.language === 'en'
              ? 'Windows audio capture closed before the device became ready.'
              : 'Windows 原生音频设备就绪前，采集连接已关闭。'
          ));
        }
      };
    });

    ws.onmessage = event => {
      let message = null;
      try { message = JSON.parse(event.data); } catch {}
      handleWs(event);
      if (message?.type === 'error' && message?.stage !== 'translation' && state.ws === ws) {
        state.listening = false;
        state.ws = null;
        cleanup();
        $('micBtn').textContent = tr('startListening');
        try { ws.close(); } catch {}
      }
    };
    ws.onerror = null;
    ws.onclose = null;
  };

  const baseToggleFloatingWindow = toggleFloatingWindow;
  const toggleFloatingWindowBeta08 = async () => {
    await baseToggleFloatingWindow();
    if (floatingWindowIsOpen()) {
      state.floatingWindow.document.title = 'Academic Live Translator beta 0.8';
      const style = state.floatingWindow.document.createElement('style');
      style.textContent = '.partial-row{opacity:.68;font-style:italic}';
      state.floatingWindow.document.head.appendChild(style);
      renderPartialUi();
    }
  };
  $('floatingWindowBtn').onclick = toggleFloatingWindowBeta08;
  $('floatingWindowSettingsBtn').onclick = toggleFloatingWindowBeta08;

  document.title = 'Academic Live Translator beta 0.8';
  const brandVersion = document.querySelector('.brand span');
  if (brandVersion) brandVersion.textContent = 'beta 0.8 · WebUI';

  if (state.config) {
    restoreBeta08Ui(state.config);
  } else {
    ensureConfigLoaded()
      .then(config => restoreBeta08Ui(config))
      .catch(error => toast(`${tr('startupError')}: ${error.message}`));
  }
})();
