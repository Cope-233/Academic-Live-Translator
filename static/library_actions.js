(() => {
  'use strict';

  const selected = new Set();
  let decorating = false;

  const TEXT = {
    'zh-CN': {
      selectAll: '全选',
      selected: n => `已选择 ${n} 项`,
      batchExport: '批量导出 MD',
      batchDelete: '批量删除',
      export: '导出',
      exportMenu: '导出格式',
      markdown: 'Markdown (.md)',
      txt: '文本 (.txt)',
      srt: '字幕 (.srt)',
      srtTranslation: '翻译字幕 (.srt)',
      json: 'JSON (.json)',
      deleteConfirm: n => `确定删除选中的 ${n} 个会话？此操作会同时删除对应的录音和截图，且无法撤销。`,
      exportFailed: '导出失败',
      deleteFailed: '部分会话删除失败',
      exported: n => `已导出 ${n} 个 Markdown 会话`,
      deleted: n => `已删除 ${n} 个会话`,
      noSelection: '请先选择至少一个会话',
      pickerFallback: '当前浏览器不支持选择保存路径，已使用浏览器默认下载方式。'
    },
    en: {
      selectAll: 'Select all',
      selected: n => `${n} selected`,
      batchExport: 'Export MD ZIP',
      batchDelete: 'Delete selected',
      export: 'Export',
      exportMenu: 'Export format',
      markdown: 'Markdown (.md)',
      txt: 'Text (.txt)',
      srt: 'Subtitles (.srt)',
      srtTranslation: 'Translated subtitles (.srt)',
      json: 'JSON (.json)',
      deleteConfirm: n => `Delete the selected ${n} sessions? Their recordings and screenshots will also be removed. This cannot be undone.`,
      exportFailed: 'Export failed',
      deleteFailed: 'Some sessions could not be deleted',
      exported: n => `Exported ${n} Markdown sessions`,
      deleted: n => `Deleted ${n} sessions`,
      noSelection: 'Select at least one session first',
      pickerFallback: 'This browser cannot choose a save path, so the normal browser download was used.'
    }
  };

  const FORMAT = {
    md: {ext: '.md', mime: 'text/markdown'},
    txt: {ext: '.txt', mime: 'text/plain'},
    srt: {ext: '.srt', mime: 'application/x-subrip'},
    'srt-translation': {ext: '.translation.srt', mime: 'application/x-subrip'},
    json: {ext: '.json', mime: 'application/json'}
  };

  function lang() {
    return document.documentElement.lang === 'en' ? 'en' : 'zh-CN';
  }

  function t(key, ...args) {
    const value = TEXT[lang()][key] ?? TEXT['zh-CN'][key] ?? key;
    return typeof value === 'function' ? value(...args) : value;
  }

  function notify(message) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(el._libraryActionsTimer);
    el._libraryActionsTimer = setTimeout(() => el.classList.remove('show'), 2600);
  }

  function safeFilename(name) {
    const cleaned = String(name || 'session')
      .replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_')
      .replace(/[. ]+$/g, '')
      .trim();
    return (cleaned || 'session').slice(0, 120);
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function saveBlob(blob, filename, mime) {
    if ('showSaveFilePicker' in window && window.isSecureContext) {
      try {
        const ext = filename.includes('.') ? filename.slice(filename.indexOf('.')) : '';
        const handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: [{description: 'Academic Live Translator export', accept: {[mime || blob.type || 'application/octet-stream']: ext ? [ext] : ['.dat']}}]
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return true;
      } catch (error) {
        if (error && error.name === 'AbortError') return false;
        console.warn('File picker failed, falling back to download:', error);
      }
    }
    downloadBlob(blob, filename);
    notify(t('pickerFallback'));
    return true;
  }

  async function fetchExport(id, format) {
    const response = await fetch(`/api/sessions/${encodeURIComponent(id)}/export/${format}`);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.blob();
  }

  async function exportOne(row) {
    const id = row.dataset.id;
    const select = row.querySelector('.session-export-format');
    const format = select?.value || 'md';
    const meta = FORMAT[format] || FORMAT.md;
    const title = row.querySelector('strong')?.textContent || id;
    const filename = `${safeFilename(title)}${meta.ext}`;
    try {
      const blob = await fetchExport(id, format);
      await saveBlob(blob, filename, meta.mime);
    } catch (error) {
      console.error(error);
      notify(`${t('exportFailed')}: ${error.message}`);
    }
  }

  function writeU16(view, offset, value) { view.setUint16(offset, value, true); }
  function writeU32(view, offset, value) { view.setUint32(offset, value >>> 0, true); }

  const crcTable = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  function dosDateTime(date = new Date()) {
    const year = Math.max(1980, date.getFullYear());
    const time = (date.getHours() << 11) | (date.getMinutes() << 5) | (date.getSeconds() >> 1);
    const day = ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
    return {time, day};
  }

  function makeZip(files) {
    const encoder = new TextEncoder();
    const localParts = [];
    const centralParts = [];
    let offset = 0;
    const stamp = dosDateTime();

    for (const file of files) {
      const name = encoder.encode(file.name);
      const data = file.data instanceof Uint8Array ? file.data : new Uint8Array(file.data);
      const crc = crc32(data);
      const local = new Uint8Array(30 + name.length + data.length);
      const lv = new DataView(local.buffer);
      writeU32(lv, 0, 0x04034b50);
      writeU16(lv, 4, 20);
      writeU16(lv, 6, 0x0800);
      writeU16(lv, 8, 0);
      writeU16(lv, 10, stamp.time);
      writeU16(lv, 12, stamp.day);
      writeU32(lv, 14, crc);
      writeU32(lv, 18, data.length);
      writeU32(lv, 22, data.length);
      writeU16(lv, 26, name.length);
      writeU16(lv, 28, 0);
      local.set(name, 30);
      local.set(data, 30 + name.length);
      localParts.push(local);

      const central = new Uint8Array(46 + name.length);
      const cv = new DataView(central.buffer);
      writeU32(cv, 0, 0x02014b50);
      writeU16(cv, 4, 20);
      writeU16(cv, 6, 20);
      writeU16(cv, 8, 0x0800);
      writeU16(cv, 10, 0);
      writeU16(cv, 12, stamp.time);
      writeU16(cv, 14, stamp.day);
      writeU32(cv, 16, crc);
      writeU32(cv, 20, data.length);
      writeU32(cv, 24, data.length);
      writeU16(cv, 28, name.length);
      writeU16(cv, 30, 0);
      writeU16(cv, 32, 0);
      writeU16(cv, 34, 0);
      writeU16(cv, 36, 0);
      writeU32(cv, 38, 0);
      writeU32(cv, 42, offset);
      central.set(name, 46);
      centralParts.push(central);
      offset += local.length;
    }

    const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
    const end = new Uint8Array(22);
    const ev = new DataView(end.buffer);
    writeU32(ev, 0, 0x06054b50);
    writeU16(ev, 4, 0);
    writeU16(ev, 6, 0);
    writeU16(ev, 8, files.length);
    writeU16(ev, 10, files.length);
    writeU32(ev, 12, centralSize);
    writeU32(ev, 16, offset);
    writeU16(ev, 20, 0);

    return new Blob([...localParts, ...centralParts, end], {type: 'application/zip'});
  }

  function uniqueMarkdownNames(items) {
    const used = new Map();
    return items.map(item => {
      const base = safeFilename(item.title);
      const count = (used.get(base) || 0) + 1;
      used.set(base, count);
      return {...item, filename: `${base}${count > 1 ? ` (${count})` : ''}.md`};
    });
  }

  function zipFilename() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `ALT-markdown-export-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.zip`;
  }

  async function batchExport() {
    if (!selected.size) return notify(t('noSelection'));
    const rows = [...document.querySelectorAll('#sessionList .session')].filter(row => selected.has(row.dataset.id));
    const items = uniqueMarkdownNames(rows.map(row => ({
      id: row.dataset.id,
      title: row.querySelector('strong')?.textContent || row.dataset.id
    })));
    if (!items.length) return notify(t('noSelection'));

    const button = document.getElementById('libraryBatchExport');
    if (button) button.disabled = true;
    try {
      const files = await Promise.all(items.map(async item => {
        const blob = await fetchExport(item.id, 'md');
        return {name: item.filename, data: new Uint8Array(await blob.arrayBuffer())};
      }));
      const zip = makeZip(files);
      const saved = await saveBlob(zip, zipFilename(), 'application/zip');
      if (saved) notify(t('exported', files.length));
    } catch (error) {
      console.error(error);
      notify(`${t('exportFailed')}: ${error.message}`);
    } finally {
      updateToolbar();
    }
  }

  async function batchDelete() {
    if (!selected.size) return notify(t('noSelection'));
    const ids = [...selected];
    if (!confirm(t('deleteConfirm', ids.length))) return;
    const button = document.getElementById('libraryBatchDelete');
    if (button) button.disabled = true;
    const results = await Promise.allSettled(ids.map(async id => {
      const response = await fetch(`/api/sessions/${encodeURIComponent(id)}`, {method: 'DELETE'});
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    }));
    const failed = results.filter(r => r.status === 'rejected').length;
    const deleted = ids.length - failed;
    selected.clear();
    if (failed) notify(`${t('deleteFailed')} (${failed})`);
    else notify(t('deleted', deleted));
    document.getElementById('refreshSessionsBtn')?.click();
    updateToolbar();
  }

  function ensureToolbar() {
    const toolbar = document.querySelector('#library .toolbar');
    if (!toolbar || document.getElementById('libraryBatchActions')) return;

    const group = document.createElement('div');
    group.id = 'libraryBatchActions';
    group.className = 'library-batch-actions';
    group.innerHTML = `
      <label class="library-select-all"><input id="librarySelectAll" type="checkbox"><span class="label"></span></label>
      <span id="librarySelectionCount" class="library-selection-count"></span>
      <button id="libraryBatchExport" type="button"></button>
      <button id="libraryBatchDelete" type="button" class="danger"></button>
    `;
    toolbar.appendChild(group);
    group.querySelector('#librarySelectAll').addEventListener('change', event => {
      const rows = [...document.querySelectorAll('#sessionList .session')];
      for (const row of rows) {
        const checkbox = row.querySelector('.session-select');
        if (!checkbox) continue;
        checkbox.checked = event.target.checked;
        if (event.target.checked) selected.add(row.dataset.id); else selected.delete(row.dataset.id);
      }
      updateToolbar();
    });
    group.querySelector('#libraryBatchExport').addEventListener('click', batchExport);
    group.querySelector('#libraryBatchDelete').addEventListener('click', batchDelete);
    updateToolbar();
  }

  function updateToolbar() {
    ensureToolbar();
    const rows = [...document.querySelectorAll('#sessionList .session')];
    const visibleIds = new Set(rows.map(row => row.dataset.id));
    for (const id of [...selected]) if (!visibleIds.has(id)) selected.delete(id);

    const selectAll = document.getElementById('librarySelectAll');
    const count = document.getElementById('librarySelectionCount');
    const exportButton = document.getElementById('libraryBatchExport');
    const deleteButton = document.getElementById('libraryBatchDelete');
    const selectLabel = document.querySelector('.library-select-all .label');
    if (selectLabel) selectLabel.textContent = t('selectAll');
    if (count) count.textContent = t('selected', selected.size);
    if (exportButton) {
      exportButton.textContent = t('batchExport');
      exportButton.disabled = selected.size === 0;
    }
    if (deleteButton) {
      deleteButton.textContent = t('batchDelete');
      deleteButton.disabled = selected.size === 0;
    }
    if (selectAll) {
      const selectedVisible = rows.filter(row => selected.has(row.dataset.id)).length;
      selectAll.checked = rows.length > 0 && selectedVisible === rows.length;
      selectAll.indeterminate = selectedVisible > 0 && selectedVisible < rows.length;
    }
  }

  function exportOptions() {
    return `
      <option value="md">${t('markdown')}</option>
      <option value="txt">${t('txt')}</option>
      <option value="srt">${t('srt')}</option>
      <option value="srt-translation">${t('srtTranslation')}</option>
      <option value="json">${t('json')}</option>
    `;
  }

  function decorateRow(row) {
    const id = row.dataset.id;
    if (!id) return;

    if (!row.querySelector('.session-select')) {
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'session-select';
      checkbox.setAttribute('aria-label', t('selectAll'));
      checkbox.checked = selected.has(id);
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) selected.add(id); else selected.delete(id);
        updateToolbar();
      });
      row.prepend(checkbox);
    }

    let extra = row.querySelector('.library-extra-actions');
    if (!extra) {
      const actions = row.lastElementChild;
      if (!actions) return;
      extra = document.createElement('span');
      extra.className = 'library-extra-actions';
      extra.innerHTML = `<select class="session-export-format" aria-label="${t('exportMenu')}">${exportOptions()}</select><button class="session-export" type="button">${t('export')}</button>`;
      actions.insertBefore(extra, actions.firstChild);
      extra.querySelector('.session-export').addEventListener('click', () => exportOne(row));
    } else {
      const select = extra.querySelector('.session-export-format');
      const current = select?.value || 'md';
      if (select) {
        select.innerHTML = exportOptions();
        select.value = current;
        select.setAttribute('aria-label', t('exportMenu'));
      }
      const button = extra.querySelector('.session-export');
      if (button) button.textContent = t('export');
    }
  }

  function decorateList() {
    if (decorating) return;
    decorating = true;
    try {
      ensureToolbar();
      const rows = [...document.querySelectorAll('#sessionList .session')];
      const visibleIds = new Set(rows.map(row => row.dataset.id));
      for (const id of [...selected]) if (!visibleIds.has(id)) selected.delete(id);
      rows.forEach(decorateRow);
      updateToolbar();
    } finally {
      decorating = false;
    }
  }

  function installStyles() {
    if (document.getElementById('libraryActionsStyles')) return;
    const style = document.createElement('style');
    style.id = 'libraryActionsStyles';
    style.textContent = `
      #library .toolbar{flex-wrap:wrap;gap:10px}
      .library-batch-actions{display:flex;align-items:center;gap:8px;margin-left:auto;flex-wrap:wrap}
      .library-select-all{display:flex;align-items:center;gap:6px;white-space:nowrap}
      .library-selection-count{font-size:13px;opacity:.7;min-width:74px}
      .session-select{flex:0 0 auto;width:17px;height:17px;margin:0 2px 0 0}
      #sessionList .session{gap:12px}
      #sessionList .session>div:last-child{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap}
      .library-extra-actions{display:inline-flex;align-items:center;gap:6px}
      .session-export-format{max-width:165px}
      .library-batch-actions button:disabled{opacity:.45;cursor:not-allowed}
      @media (max-width:800px){
        .library-batch-actions{width:100%;margin-left:0}
        #sessionList .session{align-items:flex-start}
        #sessionList .session>div:last-child{justify-content:flex-start}
      }
    `;
    document.head.appendChild(style);
  }

  function init() {
    installStyles();
    ensureToolbar();
    const list = document.getElementById('sessionList');
    if (list) new MutationObserver(decorateList).observe(list, {childList: true, subtree: true});
    new MutationObserver(() => {
      document.querySelectorAll('.library-extra-actions').forEach(extra => {
        const row = extra.closest('.session');
        if (row) decorateRow(row);
      });
      updateToolbar();
    }).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
    decorateList();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
