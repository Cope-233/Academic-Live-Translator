(() => {
  'use strict';

  const selected = new Set();
  let lastSelectedId = null;
  let defenseEnabled = false;
  let config = {model:'', reasoning_effort:'medium', answer_language:'English', user_prompt:'', workspace:'', config_path:''};
  let catalog = {models:[], current_model:'', source:'none'};
  let history = [];

  const $ = (id) => document.getElementById(id);
  const isEnglish = () => ($('uiLanguage')?.value || 'zh-CN') === 'en';
  const text = (zh, en) => isEnglish() ? en : zh;

  function notify(message){
    const toast = $('toast');
    if(toast){
      toast.textContent = message;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2600);
    }
  }

  function escapeHtml(value=''){
    const div = document.createElement('div');
    div.textContent = value;
    return div.innerHTML;
  }

  function currentSessionId(){
    try{ return state?.session?.id || ''; }catch(_e){ return ''; }
  }

  async function api(path, options={}){
    const response = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
    let data = {};
    try{ data = await response.json(); }catch(_e){}
    if(!response.ok) throw new Error(data.detail || data.message || `${response.status} ${response.statusText}`);
    return data;
  }

  function segmentText(node){
    if(!node) return '';
    const clone = node.cloneNode(true);
    clone.querySelectorAll('small').forEach((el) => el.remove());
    return clone.textContent.trim();
  }

  function orderedIds(){
    return [...document.querySelectorAll('#originalList .segment[data-segment-id]')]
      .map((node) => node.dataset.segmentId)
      .filter(Boolean);
  }

  function syncSelectionStyles(){
    document.querySelectorAll('.segment[data-segment-id]').forEach((node) => {
      node.classList.toggle('defense-selected', selected.has(node.dataset.segmentId));
    });
    const count = selected.size;
    const countLabel = $('defenseSelectionCount');
    const askButton = $('defenseAskBtn');
    const clearButton = $('defenseClearBtn');
    const preview = $('defenseSelectionPreview');
    if(countLabel) countLabel.textContent = text(`已选择 ${count} 条`, `${count} selected`);
    if(askButton) askButton.disabled = count === 0;
    if(clearButton) clearButton.disabled = count === 0;
    if(preview) preview.textContent = count
      ? text('所选片段已加入问题，可发送给 Codex。','Selected segments are ready to send to Codex.')
      : text('点击原文或翻译片段选择委员会问题。','Click transcript segments to select the committee question.');
  }

  function selectedPayload(){
    const originals = [];
    const translations = [];
    for(const id of orderedIds()){
      if(!selected.has(id)) continue;
      const source = document.querySelector(`#originalList .segment[data-segment-id="${CSS.escape(id)}"]`);
      const translation = document.querySelector(`#translationList .segment[data-segment-id="${CSS.escape(id)}"]`);
      const sourceText = segmentText(source);
      const translationText = segmentText(translation);
      if(sourceText) originals.push(sourceText);
      if(translationText) translations.push(translationText);
    }
    return {
      session_id: currentSessionId(),
      original: originals.join('\n'),
      translation: translations.join('\n'),
    };
  }

  function toggleSegment(id, shiftKey){
    if(!id) return;
    if(shiftKey && lastSelectedId){
      const ids = orderedIds();
      const a = ids.indexOf(lastSelectedId);
      const b = ids.indexOf(id);
      if(a >= 0 && b >= 0){
        const [start,end] = a < b ? [a,b] : [b,a];
        ids.slice(start,end+1).forEach((sid) => selected.add(sid));
      }
    }else if(selected.has(id)){
      selected.delete(id);
    }else{
      selected.add(id);
    }
    lastSelectedId = id;
    syncSelectionStyles();
  }

  function clearSelection(){
    selected.clear();
    lastSelectedId = null;
    syncSelectionStyles();
  }

  function setDefenseMode(enabled){
    defenseEnabled = enabled;
    document.body.classList.toggle('defense-mode', enabled);
    $('defenseModeBtn').classList.toggle('active', enabled);
    $('defenseModeBtn').setAttribute('aria-pressed', enabled ? 'true' : 'false');
    if(enabled){
      loadHistory(false);
    }else{
      clearSelection();
      closeDrawer();
    }
  }

  function openDrawer(){ $('defenseDrawer').classList.add('open'); }
  function closeDrawer(){ $('defenseDrawer').classList.remove('open'); }

  function effortLabel(effort){
    const labels = {
      none:'None', minimal:'Minimal', low:'Low', medium:'Medium', high:'High',
      xhigh:'Extra High (xhigh)', max:'Max', ultra:'Ultra', persistent:'Persistent'
    };
    return labels[effort] || effort;
  }

  function selectedModelMeta(){
    const value = $('defenseModel')?.value ?? config.model ?? '';
    const slug = value || catalog.current_model || '';
    return catalog.models.find((model) => model.slug === slug) || null;
  }

  function renderModelOptions(){
    const select = $('defenseModel');
    if(!select) return;
    const saved = config.model || '';
    const options = [];
    const autoSuffix = catalog.current_model ? ` · ${catalog.current_model}` : '';
    options.push(`<option value="">${escapeHtml(text(`自动（Codex 默认${autoSuffix}）`,`Auto (Codex default${autoSuffix})`))}</option>`);
    for(const model of catalog.models){
      const label = model.display_name === model.slug ? model.slug : `${model.display_name} · ${model.slug}`;
      options.push(`<option value="${escapeHtml(model.slug)}">${escapeHtml(label)}</option>`);
    }
    if(saved && !catalog.models.some((model) => model.slug === saved)){
      options.push(`<option value="${escapeHtml(saved)}">${escapeHtml(saved)} · ${escapeHtml(text('已保存','saved'))}</option>`);
    }
    select.innerHTML = options.join('');
    select.value = saved;
  }

  function renderReasoningOptions({preserve=true}={}){
    const select = $('defenseReasoningEffort');
    if(!select) return;
    const model = selectedModelMeta();
    let levels = model?.supported_reasoning_levels || [];
    if(!levels.length && config.reasoning_effort){
      levels = [{effort:config.reasoning_effort, description:''}];
    }
    if(!levels.length){
      levels = [{effort:'medium', description:''}];
    }
    const previous = preserve ? (select.value || config.reasoning_effort) : config.reasoning_effort;
    select.innerHTML = levels.map((level) => {
      const suffix = level.description ? ` — ${level.description}` : '';
      return `<option value="${escapeHtml(level.effort)}">${escapeHtml(effortLabel(level.effort) + suffix)}</option>`;
    }).join('');
    const supported = levels.map((level) => level.effort);
    const fallback = model?.default_reasoning_level || supported[0] || 'medium';
    select.value = supported.includes(previous) ? previous : (supported.includes(fallback) ? fallback : supported[0]);
    config.reasoning_effort = select.value;
  }

  function renderHistory(){
    const container = $('defenseHistory');
    if(!container) return;
    if(!history.length){
      container.innerHTML = `<div class="defense-history-empty">${escapeHtml(text('当前会话还没有 Defense Q&A 记录。','No Defense Q&A history for this session yet.'))}</div>`;
      return;
    }
    container.innerHTML = history.map((turn, index) => {
      const question = turn.translation || turn.original || '';
      const timestamp = turn.created_at ? new Date(turn.created_at).toLocaleTimeString() : '';
      return `<article class="defense-history-item">
        <div class="defense-history-head"><strong>Q${index + 1}</strong><span>${escapeHtml(timestamp)} · ${escapeHtml(turn.model || 'auto')} · ${escapeHtml(turn.reasoning_effort || '')}</span></div>
        <div class="defense-history-question">${escapeHtml(question)}</div>
        <div class="defense-history-answer">${escapeHtml(turn.answer || '')}</div>
      </article>`;
    }).join('');
  }

  async function loadHistory(open=false){
    const sessionId = currentSessionId();
    if(!sessionId){
      history = [];
      renderHistory();
      if(open){
        openDrawer();
        notify(text('请先创建或打开一个会话。','Create or open a session first.'));
      }
      return;
    }
    try{
      const result = await api(`/api/defense/history/${encodeURIComponent(sessionId)}`);
      history = result.turns || [];
      renderHistory();
      if(open) openDrawer();
    }catch(error){
      if(open) notify(error.message);
    }
  }

  async function askCodex(){
    const payload = selectedPayload();
    if(!payload.original && !payload.translation) return;
    if(!payload.session_id){
      notify(text('请先创建或打开一个会话。','Create or open a session first.'));
      return;
    }
    openDrawer();
    $('defenseQuestionPreview').textContent = payload.translation || payload.original;
    const answer = $('defenseAnswer');
    answer.className = 'defense-answer loading';
    answer.textContent = text('Codex 正在检索答辩资料并组织回答…','Codex is searching the defense workspace and drafting an answer…');
    $('defenseAskBtn').disabled = true;
    $('defenseCopyBtn').disabled = true;
    $('defenseMeta').textContent = '';
    try{
      const result = await api('/api/defense/ask', {method:'POST', body:JSON.stringify(payload)});
      answer.className = 'defense-answer';
      answer.textContent = result.answer;
      $('defenseCopyBtn').disabled = false;
      $('defenseMeta').textContent = `${result.model} · ${result.reasoning_effort} · ${(result.duration_ms/1000).toFixed(1)}s`;
      if(result.turn) history.push(result.turn);
      renderHistory();
    }catch(error){
      answer.className = 'defense-answer error';
      answer.textContent = error.message;
    }finally{
      $('defenseAskBtn').disabled = selected.size === 0;
    }
  }

  async function copyAnswer(){
    const value = $('defenseAnswer').textContent.trim();
    if(!value) return;
    await navigator.clipboard.writeText(value);
    notify(text('回答已复制','Answer copied'));
  }

  function injectLiveControls(){
    const actions = document.querySelector('.session-actions');
    if(!actions || $('defenseModeBtn')) return;
    const button = document.createElement('button');
    button.id = 'defenseModeBtn';
    button.className = 'experimental-action';
    button.type = 'button';
    button.setAttribute('aria-pressed','false');
    button.innerHTML = '<span>🎓 Defense Q&A</span><span class="experimental-badge">Experimental</span>';
    actions.insertBefore(button, actions.firstChild);
    button.addEventListener('click', () => setDefenseMode(!defenseEnabled));

    const sessionbar = document.querySelector('.sessionbar');
    const bar = document.createElement('div');
    bar.id = 'defenseBar';
    bar.className = 'defense-bar';
    bar.innerHTML = `
      <div class="defense-bar-copy"><strong id="defenseSelectionCount"></strong><span id="defenseSelectionPreview"></span></div>
      <div class="defense-bar-actions"><button id="defenseHistoryBtn" type="button"></button><button id="defenseClearBtn" type="button"></button><button id="defenseAskBtn" class="primary" type="button"></button></div>`;
    sessionbar.insertAdjacentElement('afterend', bar);
    $('defenseHistoryBtn').addEventListener('click', () => loadHistory(true));
    $('defenseClearBtn').addEventListener('click', clearSelection);
    $('defenseAskBtn').addEventListener('click', askCodex);

    ['originalList','translationList'].forEach((id) => {
      $(id)?.addEventListener('click', (event) => {
        if(!defenseEnabled) return;
        const node = event.target.closest('.segment[data-segment-id]');
        if(!node || node.classList.contains('partial-segment')) return;
        event.preventDefault();
        toggleSegment(node.dataset.segmentId, event.shiftKey);
      });
    });
  }

  function injectDrawer(){
    if($('defenseDrawer')) return;
    const drawer = document.createElement('aside');
    drawer.id = 'defenseDrawer';
    drawer.className = 'card defense-drawer';
    drawer.innerHTML = `
      <div class="defense-drawer-header"><h3>🎓 Defense Q&A <span class="experimental-badge">Experimental</span></h3><button id="defenseCloseBtn" type="button">×</button></div>
      <div class="defense-drawer-body">
        <h4 id="defenseQuestionLabel"></h4><div id="defenseQuestionPreview" class="defense-question-preview"></div>
        <h4 id="defenseAnswerLabel"></h4><div id="defenseAnswer" class="defense-answer"></div>
        <div class="defense-history-section"><h4 id="defenseHistoryLabel"></h4><div id="defenseHistory" class="defense-history"></div></div>
      </div>
      <div class="defense-drawer-footer"><small id="defenseMeta"></small><button id="defenseCopyBtn" type="button" disabled></button></div>`;
    document.body.appendChild(drawer);
    $('defenseCloseBtn').addEventListener('click', closeDrawer);
    $('defenseCopyBtn').addEventListener('click', copyAnswer);
  }

  function injectSettings(){
    const settings = document.querySelector('#settings .settings');
    if(!settings || $('defenseSettingsCard')) return;
    const card = document.createElement('div');
    card.id = 'defenseSettingsCard';
    card.className = 'card pad wide experimental-card';
    card.innerHTML = `
      <div class="experimental-header">
        <div><h2>Defense Q&A <span class="experimental-badge">Experimental</span></h2><p id="defenseSettingsDesc" class="muted"></p></div>
        <button id="defenseCheckBtn" class="experimental-action" type="button"></button>
      </div>
      <div class="defense-settings-status"><span id="defenseStatusDot" class="defense-status-dot"></span><strong id="defenseStatusText">—</strong><span id="defenseVersion" class="muted"></span></div>
      <div class="defense-settings-grid">
        <label><span id="defenseModelLabel"></span><select id="defenseModel"></select></label>
        <label><span id="defenseReasoningLabel"></span><select id="defenseReasoningEffort"></select></label>
        <label><span id="defenseLanguageLabel"></span><select id="defenseAnswerLanguage"><option value="English">English</option><option value="same">Same as question</option></select></label>
      </div>
      <label class="defense-user-prompt"><span id="defenseUserPromptLabel"></span><textarea id="defenseUserPrompt" rows="5"></textarea></label>
      <p id="defensePromptHint" class="muted experimental-note"></p>
      <div class="defense-workspace"><code id="defenseWorkspace">data/defense</code><button id="defenseOpenWorkspaceBtn" type="button"></button></div>
      <p id="defenseWorkspaceHint" class="muted experimental-note"></p>`;
    const floating = document.querySelector('.experimental-card');
    if(floating) floating.insertAdjacentElement('afterend', card); else settings.prepend(card);

    $('defenseModel').addEventListener('change', async () => {
      config.model = $('defenseModel').value;
      renderReasoningOptions({preserve:false});
      await saveConfig();
    });
    $('defenseReasoningEffort').addEventListener('change', saveConfig);
    $('defenseAnswerLanguage').addEventListener('change', saveConfig);
    $('defenseUserPrompt').addEventListener('change', saveConfig);
    $('defenseCheckBtn').addEventListener('click', async () => {
      await Promise.all([refreshStatus(), loadModels(true)]);
    });
    $('defenseOpenWorkspaceBtn').addEventListener('click', async () => {
      try{ await api('/api/defense/open-workspace', {method:'POST'}); }
      catch(error){ notify(error.message); }
    });
  }

  async function loadModels(refresh=false){
    try{
      catalog = await api('/api/defense/models' + (refresh ? `?t=${Date.now()}` : ''));
      renderModelOptions();
      renderReasoningOptions();
    }catch(error){
      console.warn('Defense model catalog failed:', error);
    }
  }

  async function loadConfig(){
    try{
      config = await api('/api/defense/config');
      $('defenseAnswerLanguage').value = config.answer_language;
      $('defenseUserPrompt').value = config.user_prompt || '';
      $('defenseWorkspace').textContent = config.workspace || 'data/defense';
      await loadModels(false);
    }catch(error){
      console.warn('Defense Q&A config failed:', error);
    }
  }

  async function saveConfig(){
    const payload = {
      model: $('defenseModel').value,
      reasoning_effort: $('defenseReasoningEffort').value,
      answer_language: $('defenseAnswerLanguage').value,
      user_prompt: $('defenseUserPrompt').value,
    };
    try{
      config = await api('/api/defense/config', {method:'PUT', body:JSON.stringify(payload)});
      notify(text('Defense Q&A 设置已保存','Defense Q&A settings saved'));
    }catch(error){ notify(error.message); }
  }

  async function refreshStatus(){
    const dot = $('defenseStatusDot');
    const statusText = $('defenseStatusText');
    statusText.textContent = text('检测中…','Checking…');
    dot.className = 'defense-status-dot';
    try{
      const status = await api('/api/defense/status');
      $('defenseWorkspace').textContent = status.workspace;
      $('defenseVersion').textContent = status.version || '';
      if(status.installed && status.authenticated){
        dot.className = 'defense-status-dot ready';
        statusText.textContent = text(`Codex 已就绪 · ${status.reference_files.length} 个资料文件`,`Codex ready · ${status.reference_files.length} reference file(s)`);
      }else if(status.installed){
        dot.className = 'defense-status-dot warn';
        statusText.textContent = text('Codex 已安装，但尚未登录。请在终端运行 codex login。','Codex is installed but not signed in. Run codex login in a terminal.');
      }else{
        dot.className = 'defense-status-dot warn';
        statusText.textContent = text('未检测到 Codex CLI。运行 npm install -g @openai/codex 安装。','Codex CLI not found. Install with npm install -g @openai/codex.');
      }
    }catch(error){
      dot.className = 'defense-status-dot warn';
      statusText.textContent = error.message;
    }
  }

  function localize(){
    if(!$('defenseSettingsCard')) return;
    $('defenseSelectionCount').textContent = text(`已选择 ${selected.size} 条`,`${selected.size} selected`);
    $('defenseHistoryBtn').textContent = text('历史','History');
    $('defenseClearBtn').textContent = text('清除','Clear');
    $('defenseAskBtn').textContent = text('发送到 Codex','Ask Codex');
    $('defenseQuestionLabel').textContent = text('当前委员会问题','Current committee question');
    $('defenseAnswerLabel').textContent = text('建议回答','Suggested answer');
    $('defenseHistoryLabel').textContent = text('本会话 Q&A 记录','Session Q&A history');
    $('defenseCopyBtn').textContent = text('复制回答','Copy answer');
    $('defenseSettingsDesc').textContent = text('将实时识别/翻译中的委员会问题发送给 Codex，并让其读取本地答辩资料后直接给出回答。','Send selected live transcript/translation segments to Codex and answer from local defense materials.');
    $('defenseCheckBtn').textContent = text('刷新 Codex','Refresh Codex');
    $('defenseModelLabel').textContent = text('Codex 模型','Codex model');
    $('defenseReasoningLabel').textContent = text('推理强度','Reasoning effort');
    $('defenseLanguageLabel').textContent = text('回答语言','Answer language');
    $('defenseUserPromptLabel').textContent = text('用户 Prompt','User prompt');
    $('defenseUserPrompt').placeholder = text('例如：优先引用第 3–5 章；用第一人称回答；控制在 60 秒内。','Example: Prioritize Chapters 3–5; answer in first person; keep the response under 60 seconds.');
    const configPath = config.config_path || 'data/defense_config.json';
    $('defensePromptHint').textContent = text(`系统 Prompt 不在 WebUI 中暴露，可直接编辑 ${configPath} 中的 system_prompt；发送时会按“系统 Prompt + 用户 Prompt + 问题 + 追问上下文”组合。`,`The system prompt is intentionally not exposed in the WebUI. Edit system_prompt in ${configPath}; requests combine system prompt + user prompt + question + follow-up context.`);
    $('defenseOpenWorkspaceBtn').textContent = text('打开答辩资料目录','Open defense folder');
    $('defenseWorkspaceHint').textContent = text('将论文和答辩资料的 Markdown/TXT 版本放入此目录。模型与推理强度会从当前 Codex CLI 模型目录自动读取。','Put Markdown/TXT copies of the thesis and defense references here. Model and reasoning choices are read automatically from the current Codex CLI catalog.');
    syncSelectionStyles();
    renderHistory();
  }

  async function init(){
    document.title = 'Academic Live Translator 1.0';
    document.addEventListener('alt:transcript-rendered', syncSelectionStyles);
    const brandVersion = document.querySelector('.brand span');
    if(brandVersion) brandVersion.textContent = '1.0 · WebUI';
    injectLiveControls();
    injectDrawer();
    injectSettings();
    localize();
    await loadConfig();
    localize();
    refreshStatus();
    $('uiLanguage')?.addEventListener('change', () => setTimeout(localize, 0));
    ['floatingWindowBtn','floatingWindowSettingsBtn'].forEach((id) => $(id)?.addEventListener('click', () => setTimeout(() => {
      const pipWindow = window.documentPictureInPicture?.window;
      if(pipWindow && !pipWindow.closed) pipWindow.document.title = 'Academic Live Translator 1.0';
    }, 250)));
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
