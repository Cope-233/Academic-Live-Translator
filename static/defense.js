(() => {
  'use strict';

  const selected = new Set();
  let lastSelectedId = null;
  let defenseEnabled = false;
  let config = {response_mode:'fast', answer_language:'English', model:'', workspace:''};

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
    $('defenseSelectionCount').textContent = text(`已选择 ${count} 条`, `${count} selected`);
    $('defenseAskBtn').disabled = count === 0;
    $('defenseClearBtn').disabled = count === 0;
    const preview = selectedPayload();
    $('defenseSelectionPreview').textContent = preview.translation || preview.original || text('点击原文或翻译片段选择委员会问题。','Click transcript segments to select the committee question.');
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
    return {original: originals.join('\n'), translation: translations.join('\n')};
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
    if(!enabled){
      clearSelection();
      closeDrawer();
    }
  }

  function openDrawer(){ $('defenseDrawer').classList.add('open'); }
  function closeDrawer(){ $('defenseDrawer').classList.remove('open'); }

  async function askCodex(){
    const payload = selectedPayload();
    if(!payload.original && !payload.translation) return;
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
      $('defenseMeta').textContent = `${result.model} · ${result.response_mode} · ${(result.duration_ms/1000).toFixed(1)}s`;
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
      <div class="defense-bar-actions"><button id="defenseClearBtn" type="button"></button><button id="defenseAskBtn" class="primary" type="button"></button></div>`;
    sessionbar.insertAdjacentElement('afterend', bar);
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
        <label><span id="defenseResponseLabel"></span><select id="defenseResponseMode"><option value="fast">Fast</option><option value="balanced">Balanced</option><option value="deep">Deep</option></select></label>
        <label><span id="defenseLanguageLabel"></span><select id="defenseAnswerLanguage"><option value="English">English</option><option value="same">Same as question</option></select></label>
      </div>
      <div class="defense-workspace"><code id="defenseWorkspace">data/defense</code><button id="defenseOpenWorkspaceBtn" type="button"></button></div>
      <p id="defenseWorkspaceHint" class="muted experimental-note"></p>
      <details class="defense-advanced"><summary id="defenseAdvancedLabel"></summary><label><span>Codex model</span><input id="defenseModel" placeholder="Auto / Codex default"></label></details>`;
    const floating = document.querySelector('.experimental-card');
    if(floating) floating.insertAdjacentElement('afterend', card); else settings.prepend(card);

    $('defenseResponseMode').addEventListener('change', saveConfig);
    $('defenseAnswerLanguage').addEventListener('change', saveConfig);
    $('defenseModel').addEventListener('change', saveConfig);
    $('defenseCheckBtn').addEventListener('click', refreshStatus);
    $('defenseOpenWorkspaceBtn').addEventListener('click', async () => {
      try{ await api('/api/defense/open-workspace', {method:'POST'}); }
      catch(error){ notify(error.message); }
    });
  }

  async function loadConfig(){
    try{
      config = await api('/api/defense/config');
      $('defenseResponseMode').value = config.response_mode;
      $('defenseAnswerLanguage').value = config.answer_language;
      $('defenseModel').value = config.model || '';
      $('defenseWorkspace').textContent = config.workspace || 'data/defense';
    }catch(error){
      console.warn('Defense Q&A config failed:', error);
    }
  }

  async function saveConfig(){
    const payload = {
      response_mode: $('defenseResponseMode').value,
      answer_language: $('defenseAnswerLanguage').value,
      model: $('defenseModel').value.trim(),
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
    $('defenseClearBtn').textContent = text('清除','Clear');
    $('defenseAskBtn').textContent = text('发送到 Codex','Ask Codex');
    $('defenseQuestionLabel').textContent = text('委员会问题','Committee question');
    $('defenseAnswerLabel').textContent = text('建议回答','Suggested answer');
    $('defenseCopyBtn').textContent = text('复制回答','Copy answer');
    $('defenseSettingsDesc').textContent = text('将实时识别/翻译中的委员会问题发送给 Codex，并让其读取本地答辩资料后直接给出回答。','Send selected live transcript/translation segments to Codex and answer from local defense materials.');
    $('defenseCheckBtn').textContent = text('检查 Codex','Check Codex');
    $('defenseResponseLabel').textContent = text('响应模式','Response mode');
    $('defenseLanguageLabel').textContent = text('回答语言','Answer language');
    $('defenseOpenWorkspaceBtn').textContent = text('打开答辩资料目录','Open defense folder');
    $('defenseWorkspaceHint').textContent = text('将论文和答辩资料的 Markdown/TXT 版本放入此目录。默认 Fast = low reasoning；模型保持 Auto 即使用当前 Codex 默认模型。','Put Markdown/TXT copies of the thesis and defense references here. Fast uses low reasoning; keep Model on Auto to use the current Codex default.');
    $('defenseAdvancedLabel').textContent = text('高级设置','Advanced');
    syncSelectionStyles();
  }

  async function init(){
    document.title = 'Academic Live Translator beta 0.9';
    const brandVersion = document.querySelector('.brand span');
    if(brandVersion) brandVersion.textContent = 'beta 0.9 · WebUI';
    injectLiveControls();
    injectDrawer();
    injectSettings();
    localize();
    await loadConfig();
    refreshStatus();
    $('uiLanguage')?.addEventListener('change', () => setTimeout(localize, 0));
    ['floatingWindowBtn','floatingWindowSettingsBtn'].forEach((id) => $(id)?.addEventListener('click', () => setTimeout(() => {
      const pipWindow = window.documentPictureInPicture?.window;
      if(pipWindow && !pipWindow.closed) pipWindow.document.title = 'Academic Live Translator beta 0.9';
    }, 250)));
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();