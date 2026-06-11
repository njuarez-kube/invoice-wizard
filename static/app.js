/* app.js — handles both index.html and setup.html */

// ── Close Session ─────────────────────────────────────────────────────────────
const closeBtn = document.getElementById('close-app-btn');
if (closeBtn) {
  closeBtn.addEventListener('click', async () => {
    if (!confirm('Stop the Invoice Wizard? You can close this tab afterwards.')) return;
    try { await fetch('/api/shutdown', { method: 'POST' }); } catch { /* already down */ }
    const overlay = document.getElementById('server-stopped-overlay');
    if (overlay) { overlay.style.display = 'flex'; overlay.classList.add('visible'); }
  });
}

const IS_SETUP = document.getElementById('step1') !== null;

// ── Update check (dashboard only) ────────────────────────────────────────────
if (!IS_SETUP) {
  fetch('/api/version').then(r => r.json()).then(v => {
    if (!v.available) return;
    const banner = document.getElementById('update-banner');
    if (!banner) return;
    document.getElementById('update-version').textContent = 'v' + v.latest;
    banner.style.display = 'flex';
  }).catch(() => {});
}

/* ══════════════════════════════════════════════════════════════════════════════
   DASHBOARD (index.html)
══════════════════════════════════════════════════════════════════════════════ */
if (!IS_SETUP) {
  const dropZone    = document.getElementById('drop-zone');
  const fileInput   = document.getElementById('file-input');
  const fileList    = document.getElementById('file-list');
  const extractBtn  = document.getElementById('extract-btn');
  const previewSec  = document.getElementById('preview-section');
  const previewBody = document.getElementById('preview-body');
  const rowCount    = document.getElementById('row-count');
  const writeBtn    = document.getElementById('write-btn');
  const writeResult = document.getElementById('write-result');

  let selectedFiles = [];   // File objects
  let extractedRows = [];   // raw JSON from /api/extract

  // ── Drag & drop ─────────────────────────────────────────────────────────────
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    addFiles([...e.dataTransfer.files].filter(f => f.name.endsWith('.pdf')));
  });
  dropZone.addEventListener('click', e => { if (!e.target.closest('label')) fileInput.click(); });
  fileInput.addEventListener('change', () => {
    addFiles([...fileInput.files]);
    fileInput.value = '';
  });

  function addFiles(files) {
    files.forEach(f => {
      if (!selectedFiles.find(x => x.name === f.name)) selectedFiles.push(f);
    });
    renderFileList();
  }

  function renderFileList() {
    fileList.innerHTML = '';
    selectedFiles.forEach((f, i) => {
      const chip = document.createElement('div');
      chip.className = 'file-chip';
      chip.innerHTML = `<span>${f.name}</span><button title="Remove">×</button>`;
      chip.querySelector('button').onclick = () => { selectedFiles.splice(i, 1); renderFileList(); };
      fileList.appendChild(chip);
    });
    fileList.classList.toggle('hidden', selectedFiles.length === 0);
    extractBtn.classList.toggle('hidden', selectedFiles.length === 0);
  }

  // ── Extract ──────────────────────────────────────────────────────────────────
  extractBtn.addEventListener('click', async () => {
    if (!selectedFiles.length) return;
    extractBtn.disabled = true;
    extractBtn.textContent = 'Extracting…';

    const fd = new FormData();
    selectedFiles.forEach(f => fd.append('files', f));

    try {
      const res = await fetch('/api/extract', { method: 'POST', body: fd });
      const data = await res.json();
      extractedRows = data.rows || [];
      renderTable(extractedRows);
      previewSec.classList.remove('hidden');
      previewSec.scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
      alert('Extraction failed: ' + err.message);
    } finally {
      extractBtn.disabled = false;
      extractBtn.textContent = 'Extract Data';
    }
  });

  // ── Table rendering ──────────────────────────────────────────────────────────
  function statusBadge(row) {
    if (row.duplicate) return `<span class="status status-dup">Duplicate</span>`;
    if (!row.vendor_config) return `<span class="status status-error">No vendor</span>`;
    if (row.warnings && row.warnings.length) return `<span class="status status-warn" title="${row.warnings.join('\n')}">⚠ Partial</span>`;
    return `<span class="status status-ok">✓ OK</span>`;
  }

  function fmt(val, decimals = 2) {
    if (val === null || val === undefined) return '';
    return typeof val === 'number' ? val.toFixed(decimals) : val;
  }

  function renderTable(rows) {
    previewBody.innerHTML = '';
    rows.forEach((row, idx) => {
      const tr = document.createElement('tr');
      if (row.duplicate) tr.classList.add('excluded');
      tr.dataset.idx = idx;

      // editable cell helper
      const cell = (val, field) => {
        const td = document.createElement('td');
        td.contentEditable = 'true';
        td.dataset.field = field;
        td.textContent = val !== null && val !== undefined ? val : '';
        td.addEventListener('input', () => {
          extractedRows[idx][field] = td.textContent.trim() || null;
        });
        return td;
      };

      const checkTd = document.createElement('td');
      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.className = 'row-check';
      chk.checked = !row.duplicate;
      chk.addEventListener('change', () => {
        tr.classList.toggle('excluded', !chk.checked);
        extractedRows[idx]._include = chk.checked;
      });
      extractedRows[idx]._include = !row.duplicate;
      checkTd.appendChild(chk);

      tr.appendChild(checkTd);
      tr.appendChild(cell(row.source_file, 'source_file')).contentEditable = 'false';
      tr.appendChild(cell(row.invoice_number, 'invoice_number'));
      tr.appendChild(cell(row.date, 'date'));
      tr.appendChild(cell(fmt(row.vat_inc),   'vat_inc')).contentEditable = 'false';
      tr.appendChild(cell(fmt(row.vat_amount), 'vat_amount'));
      tr.appendChild(cell(fmt(row.excl_vat),   'excl_vat'));
      tr.appendChild(cell(fmt(row.retention, 2), 'retention'));
      tr.appendChild(cell(row.vendor_name, 'vendor_name'));
      tr.appendChild(cell(row.comments,    'comments'));

      const statusTd = document.createElement('td');
      statusTd.innerHTML = statusBadge(row);
      tr.appendChild(statusTd);

      previewBody.appendChild(tr);
    });

    rowCount.textContent = `${rows.length} invoice${rows.length !== 1 ? 's' : ''}`;

    const selectAll = document.getElementById('select-all');
    if (selectAll) {
      selectAll.checked = true;
      selectAll.onchange = () => {
        document.querySelectorAll('.row-check').forEach(chk => {
          chk.checked = selectAll.checked;
          chk.dispatchEvent(new Event('change'));
        });
      };
    }
  }

  // ── Reset Excel ──────────────────────────────────────────────────────────────
  document.getElementById('reset-btn').addEventListener('click', async () => {
    if (!confirm('This will permanently delete the current gastos.xlsx and start a fresh empty file.\n\nDownload a copy first if you need it.\n\nContinue?')) return;
    try {
      await fetch('/api/excel', { method: 'DELETE' });
      showWriteResult('Excel reset. The next Write will create a new empty file.', true);
    } catch (err) {
      showWriteResult('Reset failed: ' + err.message, false);
    }
  });

  // ── Write to Excel ───────────────────────────────────────────────────────────
  writeBtn.addEventListener('click', async () => {
    const toWrite = extractedRows.filter(r => r._include !== false);
    if (!toWrite.length) { showWriteResult('No rows selected.', false); return; }

    writeBtn.disabled = true;
    writeBtn.textContent = 'Writing…';

    try {
      const res = await fetch('/api/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows: toWrite }),
      });
      const summary = await res.json();
      const msg = `Written: ${summary.written} | Duplicates skipped: ${summary.duplicates} | Errors: ${summary.errors}`;
      showWriteResult(msg, summary.errors === 0);
    } catch (err) {
      showWriteResult('Write failed: ' + err.message, false);
    } finally {
      writeBtn.disabled = false;
      writeBtn.textContent = 'Write to Excel';
    }
  });

  function showWriteResult(msg, ok) {
    writeResult.textContent = msg;
    writeResult.className = 'result-msg ' + (ok ? 'success' : 'error');
    writeResult.classList.remove('hidden');
  }
}


/* ══════════════════════════════════════════════════════════════════════════════
   VENDOR SETUP (setup.html)
══════════════════════════════════════════════════════════════════════════════ */
if (IS_SETUP) {
  const sampleDrop    = document.getElementById('sample-drop-zone');
  const sampleInput   = document.getElementById('sample-input');
  const sampleStatus  = document.getElementById('sample-status');
  const step2         = document.getElementById('step2');
  const step3         = document.getElementById('step3');
  const step4         = document.getElementById('step4');
  const vendorName    = document.getElementById('vendor-name');
  const vendorKws     = document.getElementById('vendor-keywords');
  const textDisplay   = document.getElementById('sample-text-display');
  const pageTabs      = document.getElementById('page-tabs');
  const textViewer    = document.getElementById('text-viewer');
  const pickBanner    = document.getElementById('pick-banner');
  const configPreview = document.getElementById('config-preview');
  const saveBtn       = document.getElementById('save-btn');
  const saveResult    = document.getElementById('save-result');

  let pagesData = [];   // [{page, text}]
  let currentPage = 0;
  let pickTarget  = null;  // field-block currently waiting for a pick

  // ── Google Drive sync ────────────────────────────────────────────────────────
  const driveChip    = document.getElementById('drive-status-chip');
  const drivePullBtn = document.getElementById('drive-pull-btn');
  const drivePushBtn = document.getElementById('drive-push-btn');
  const driveResult  = document.getElementById('drive-result');

  function setDriveButtons(enabled) {
    drivePullBtn.disabled = !enabled;
    drivePushBtn.disabled = !enabled;
  }

  fetch('/api/drive/status')
    .then(r => r.json())
    .then(data => {
      if (data.connected) {
        driveChip.textContent = 'Connected';
        driveChip.className   = 'drive-chip connected';
        setDriveButtons(true);
      } else {
        driveChip.textContent = 'Not connected';
        driveChip.className   = 'drive-chip disconnected';
        driveResult.textContent = data.message || '';
      }
    })
    .catch(() => {
      driveChip.textContent = 'Not connected';
      driveChip.className   = 'drive-chip disconnected';
    });

  drivePullBtn.addEventListener('click', async () => {
    setDriveButtons(false);
    driveResult.textContent = 'Syncing…';
    try {
      const res  = await fetch('/api/drive/pull', { method: 'POST' });
      const data = await res.json();
      if (data.error) {
        driveResult.textContent = 'Error: ' + data.error;
      } else {
        driveResult.textContent = `Updated ${data.updated}, Created ${data.created}` +
          (data.errors.length ? ` — ${data.errors.join('; ')}` : '');
        loadVendorDropdown();
      }
    } catch (err) {
      driveResult.textContent = 'Pull failed: ' + err.message;
    } finally {
      setDriveButtons(true);
    }
  });

  drivePushBtn.addEventListener('click', async () => {
    setDriveButtons(false);
    driveResult.textContent = 'Uploading…';
    try {
      const res  = await fetch('/api/drive/push', { method: 'POST' });
      const data = await res.json();
      if (data.error) {
        driveResult.textContent = 'Error: ' + data.error;
      } else {
        driveResult.textContent = `Updated ${data.updated}, Created ${data.created}` +
          (data.errors.length ? ` — ${data.errors.join('; ')}` : '');
      }
    } catch (err) {
      driveResult.textContent = 'Push failed: ' + err.message;
    } finally {
      setDriveButtons(true);
    }
  });

  // ── Sample upload ────────────────────────────────────────────────────────────
  sampleDrop.addEventListener('dragover', e => { e.preventDefault(); sampleDrop.classList.add('dragover'); });
  sampleDrop.addEventListener('dragleave', () => sampleDrop.classList.remove('dragover'));
  sampleDrop.addEventListener('drop', e => {
    e.preventDefault();
    sampleDrop.classList.remove('dragover');
    const f = [...e.dataTransfer.files].find(f => f.name.endsWith('.pdf'));
    if (f) uploadSample(f);
  });
  sampleDrop.addEventListener('click', e => { if (!e.target.closest('label')) sampleInput.click(); });
  sampleInput.addEventListener('change', () => {
    if (sampleInput.files[0]) uploadSample(sampleInput.files[0]);
  });

  async function uploadSample(file) {
    sampleStatus.textContent = 'Extracting text…';
    sampleStatus.className = '';
    sampleStatus.classList.remove('hidden');

    const fd = new FormData();
    fd.append('file', file);

    try {
      const res = await fetch('/api/vendors/sample-text', { method: 'POST', body: fd });
      const data = await res.json();
      pagesData = data.pages || [];
      sampleStatus.textContent = `✓ Text extracted from ${pagesData.length} page(s)`;
      buildPageTabs();
      step2.classList.remove('hidden');
      step3.classList.remove('hidden');
    } catch (err) {
      sampleStatus.textContent = 'Error: ' + err.message;
    }
  }

  function buildPageTabs() {
    pageTabs.innerHTML = '';
    pagesData.forEach((p, i) => {
      const tab = document.createElement('button');
      tab.className = 'page-tab' + (i === 0 ? ' active' : '');
      tab.textContent = `Page ${p.page}`;
      tab.onclick = () => {
        currentPage = i;
        pageTabs.querySelectorAll('.page-tab').forEach((t, j) => t.classList.toggle('active', j === i));
        textDisplay.textContent = pagesData[i].text;
      };
      pageTabs.appendChild(tab);
    });
    if (pagesData.length) textDisplay.textContent = pagesData[0].text;
  }

  // ── Radio toggles (auto/skip hide the label-section, label shows it) ─────────
  document.querySelectorAll('.field-block').forEach(block => {
    block.querySelectorAll('input[type=radio]').forEach(radio => {
      radio.addEventListener('change', () => {
        const section = block.querySelector('.label-section');
        if (section) section.classList.toggle('hidden', (radio.value === 'auto' || radio.value === 'skip') && radio.checked);
      });
    });

  });

  // ── Regex builders ────────────────────────────────────────────────────────────
  function escLabel(label) {
    return label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ +/g, '\\s+');
  }
  function buildRegex(label, type, nextLine, lastToken) {
    const e = escLabel(label);
    if (nextLine) {
      if (lastToken) {
        if (type === 'amount') return e + '[^\\n]*\\n(?:[^\\n]+[ \\t])?([\\d.,]+)';
        return e + '[^\\n]*\\n(?:[^\\n]+[ \\t])?(\\S+)';
      }
      const sep = '[^\\n]*\\n[^\\n]*?';
      if (type === 'amount') return e + sep + '([\\d.,]+)';
      return e + sep + '(\\S+)';
    }
    if (lastToken) {
      if (type === 'amount') return e + '[^\\n]*[ \\t]([\\d.,]+)[ \\t]*(?=\\n|$)';
      return e + '[^\\n]*[ \\t](\\S+)[ \\t]*(?=\\n|$)';
    }
    if (type === 'amount') return e + '[^\\d\\n]+([\\d.,]+)';
    return e + '\\s*(\\S+)';
  }
  function buildDateRegex(label, fmt, nextLine, lastToken) {
    const e = escLabel(label);
    const sep = nextLine
      ? (lastToken ? '[^\\n]*\\n[^\\n]*[ \\t]' : '[^\\n]*\\n[^\\n]*?')
      : (lastToken ? '[^\\n]*[ \\t]' : '\\s*');
    if (fmt === 'date_slash') return e + sep + '(\\d{1,2})[/\\-](\\w+)\\.?[/\\-](\\d{4})';
    if (fmt === 'date_num')   return e + sep + '(\\d{1,2})[/\\-](\\d{2})[/\\-](\\d{4})';
    if (fmt === 'date_mdy')   return e + sep + '(\\w+)\\s+(\\d{1,2}),?\\s+(\\d{4})';
    return e + sep + '(\\d{1,2})\\s+(\\w+)\\s+(\\d{4})';
  }
  function fieldConfig(block) {
    const fname = block.dataset.field;
    const labelInput    = block.querySelector('.label-input');
    const valueType     = block.querySelector('.value-type');
    const nextLineCheck = block.querySelector('.next-line-check');
    const label          = labelInput?.value.trim() || '';
    const fmt            = valueType?.value || '';
    const nextLine       = nextLineCheck?.checked || false;
    const lastTokenCheck = block.querySelector('.last-token-check');
    const lastToken      = lastTokenCheck?.checked || false;
    const occInput       = block.querySelector('.occurrence-input');
    const occurrence     = Math.max(1, parseInt(occInput?.value) || 1);

    if (fname === 'vendor_name') return { static: label };

    const meta = label ? { _label: label, _fmt: fmt, _next_line: nextLine, _last_token: lastToken } : {};

    if (fname === 'excl_vat') {
      return { ...meta, regex: buildRegex(label, 'amount', nextLine, lastToken), group: 1, occurrence };
    }

    if (fname === 'vat_amount') {
      if (!label) return { static: 0 };
      return { ...meta, regex: buildRegex(label, 'amount', nextLine, lastToken), group: 1, occurrence };
    }

    if (fname === 'date') {
      const type = fmt === 'date_mdy' ? 'english_mdy' : 'spanish_dmy';
      return { ...meta, type, regex: buildDateRegex(label, fmt, nextLine, lastToken), occurrence };
    }

    if (fname === 'vat_inc') {
      if (!label) return { skip: true };
      return { ...meta, regex: buildRegex(label, 'amount', nextLine, lastToken), group: 1, occurrence };
    }

    if (fname === 'retention') {
      const radio = block.querySelector('input[type=radio]:checked');
      if (!radio || radio.value === 'skip') return { skip: true };
      return { ...meta, regex: buildRegex(label, 'amount', nextLine, lastToken), group: 1, occurrence };
    }

    if (fname === 'comments') {
      const radio = block.querySelector('input[type=radio]:checked');
      if (!radio || radio.value === 'skip') return { skip: true };
      const e = escLabel(label);
      const regex = nextLine ? e + '[^\\n]*\\n([^\\n]+)' : e + '\\s*([^\\n]+)';
      return { ...meta, regex, group: 1, occurrence };
    }

    // invoice_number
    return { ...meta, regex: buildRegex(label, fmt, nextLine, lastToken), group: 1, occurrence };
  }

  // ── Test buttons ─────────────────────────────────────────────────────────────
  function showResult(el, ok, msg) {
    el.textContent = msg;
    el.className = 'test-result ' + (ok ? 'hit' : 'miss');
    el.classList.remove('hidden');
  }

  document.querySelectorAll('.test-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const block  = btn.closest('.field-block');
      const fname  = block.dataset.field;
      const result = block.querySelector('.test-result');
      const text   = pagesData[currentPage]?.text || '';
      const cfg    = fieldConfig(block);

      if ('static' in cfg) {
        if (fname === 'vat_amount' && cfg.static === 0) {
          showResult(result, true, '✓ VAT Returnable = 0 — no VAT for this vendor.');
        } else {
          showResult(result, !!cfg.static, cfg.static ? `✓ Will write: "${cfg.static}"` : 'Enter a vendor name.');
        }
        return;
      }
      if (cfg.skip) {
        const skipMsg = fname === 'comments'
          ? '✓ Comments skipped for this vendor — column will be left blank.'
          : '✓ Optional field left blank — will be skipped for this vendor.';
        showResult(result, true, skipMsg);
        return;
      }
      if (cfg.type && cfg.type.startsWith('vat_table')) {
        showResult(result, true, '✓ Auto-detect — will be tested when you upload a real invoice.');
        return;
      }
      if (!text) { showResult(result, false, 'Upload a sample PDF first.'); return; }

      const regex = cfg.regex || '';
      const group = (cfg.type === 'spanish_dmy' || cfg.type === 'english_mdy') ? 1 : (cfg.group || 1);

      try {
        const res  = await fetch('/api/vendors/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ regex, text, group, occurrence: cfg.occurrence || 1 }),
        });
        const data = await res.json();
        if (data.error)       showResult(result, false, 'Pattern error: ' + data.error);
        else if (data.match)  showResult(result, true,  `✓ Captured: "${data.captured}"`);
        else                  showResult(result, false, '✗ Not found — check the text below and copy the label exactly.');
      } catch (err) {
        showResult(result, false, 'Test failed: ' + err.message);
      }
    });
  });

  // ── Build config & show step 4 ───────────────────────────────────────────────
  const vendorCurrency = document.getElementById('vendor-currency');

  function buildConfig() {
    const name     = vendorName.value.trim();
    const kws      = vendorKws.value.split(',').map(s => s.trim()).filter(Boolean);
    const currency = vendorCurrency.value || 'EUR';
    const fields   = { vendor_name: { static: name } };
    document.querySelectorAll('.field-block').forEach(block => {
      const cfg = fieldConfig(block);
      if (!cfg.skip) fields[block.dataset.field] = cfg;
    });
    return { name, detect_keywords: kws, currency, fields };
  }

  vendorName.addEventListener('input', maybeShowStep4);
  vendorKws.addEventListener('input', maybeShowStep4);
  vendorCurrency.addEventListener('change', maybeShowStep4);

  // ── Pick-from-text mode ───────────────────────────────────────────────────────
  function enterPickMode(block) {
    pickTarget = block;
    const fieldName = block.querySelector('h3').textContent.trim().replace(/\s*\(.*/, '');
    pickBanner.textContent = `Selecting for: ${fieldName} — drag to highlight the value in the text above, then release.`;
    pickBanner.classList.add('visible');
    textViewer.classList.add('pick-active');
    textViewer.open = true;
    textViewer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function exitPickMode() {
    pickTarget = null;
    pickBanner.classList.remove('visible');
    textViewer.classList.remove('pick-active');
  }

  document.addEventListener('keydown', e => { if (e.key === 'Escape' && pickTarget) exitPickMode(); });

  document.querySelectorAll('.pick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const block = btn.closest('.field-block');
      if (pickTarget === block) { exitPickMode(); return; }
      enterPickMode(block);
    });
  });

  textDisplay.addEventListener('mouseup', () => {
    if (!pickTarget) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    const range = sel.getRangeAt(0);
    if (!textDisplay.contains(range.commonAncestorContainer)) return;

    // Compute character offset of selection start within the pre element
    const preRange = document.createRange();
    preRange.setStart(textDisplay, 0);
    preRange.setEnd(range.startContainer, range.startOffset);
    const selStart = preRange.toString().length;

    const { label, nextLine } = labelFromSelection(textDisplay.textContent, selStart);
    applyPickResult(pickTarget, label, nextLine);
    exitPickMode();
    sel.removeAllRanges();
  });

  function labelFromSelection(fullText, selStart) {
    const lineStart = fullText.lastIndexOf('\n', selStart - 1) + 1;
    const rawPrefix = fullText.slice(lineStart, selStart).trim();
    if (rawPrefix) {
      const words = rawPrefix.split(/\s+/);
      return { label: words.slice(-4).join(' '), nextLine: false };
    }
    // value at start of line — use the previous line as the label
    const prevLineEnd = lineStart - 1;
    const prevLineStart = fullText.lastIndexOf('\n', prevLineEnd - 1) + 1;
    const prevLine = fullText.slice(prevLineStart, prevLineEnd).trim();
    const words = prevLine.split(/\s+/);
    return { label: words.slice(-4).join(' '), nextLine: true };
  }

  function applyPickResult(block, label, nextLine) {
    const labelInput = block.querySelector('.label-input');
    if (labelInput) labelInput.value = label;

    const nextLineCheck = block.querySelector('.next-line-check');
    if (nextLineCheck) nextLineCheck.checked = nextLine;

    // Switch auto/skip radios to label mode so the label input takes effect
    const labelRadio = block.querySelector('input[value="label"]');
    if (labelRadio && !labelRadio.checked) {
      labelRadio.checked = true;
      labelRadio.dispatchEvent(new Event('change'));
    }

    block.querySelector('.test-btn')?.click();
    maybeShowStep4();
  }

  function maybeShowStep4() {
    const kws = vendorKws.value.split(',').map(s => s.trim()).filter(Boolean);
    const kwsError = document.getElementById('kws-error');
    if (kwsError) kwsError.style.display = kws.length === 0 ? '' : 'none';
    if (!vendorName.value.trim() || kws.length === 0) return;
    configPreview.textContent = JSON.stringify(buildConfig(), null, 2);
    step4.classList.remove('hidden');
  }

  // ── Load existing vendor ──────────────────────────────────────────────────────
  function loadVendorDropdown() {
    fetch('/api/vendors')
      .then(r => r.json())
      .then(data => {
        const sel = document.getElementById('load-vendor-select');
        sel.innerHTML = '<option value="">— Select a saved vendor to edit —</option>';
        (data.vendors || []).forEach(v => {
          const opt = document.createElement('option');
          opt.value = JSON.stringify(v);
          opt.textContent = v.name;
          sel.appendChild(opt);
        });
        if (!data.vendors || data.vendors.length === 0) {
          const opt = document.createElement('option');
          opt.disabled = true;
          opt.textContent = '(no saved vendors yet)';
          sel.appendChild(opt);
        }
      })
      .catch(err => console.error('Could not load vendors:', err));
  }

  loadVendorDropdown();

  document.getElementById('load-vendor-btn').addEventListener('click', () => {
    const loadSel = document.getElementById('load-vendor-select');
    if (!loadSel.value) return;
    const cfg = JSON.parse(loadSel.value);

    vendorName.value     = cfg.name || '';
    vendorKws.value      = (cfg.detect_keywords || []).join(', ');
    vendorCurrency.value = cfg.currency || 'EUR';

    const fieldCfgs = cfg.fields || {};
    document.querySelectorAll('.field-block').forEach(block => {
      const fname          = block.dataset.field;
      const fcfg           = fieldCfgs[fname] || {};
      const labelInput     = block.querySelector('.label-input');
      const valueType      = block.querySelector('.value-type');
      const nextLineCheck  = block.querySelector('.next-line-check');
      const lastTokenCheck = block.querySelector('.last-token-check');
      const lastTokenRow   = block.querySelector('.last-token-row');
      const occInput       = block.querySelector('.occurrence-input');

      if (labelInput     && fcfg._label !== undefined) labelInput.value = fcfg._label;
      if (valueType      && fcfg._fmt)                 valueType.value  = fcfg._fmt;
      if (nextLineCheck) {
        nextLineCheck.checked = !!fcfg._next_line;
        if (lastTokenRow) lastTokenRow.style.display = nextLineCheck.checked ? '' : 'none';
      }
      if (lastTokenCheck) lastTokenCheck.checked = !!fcfg._last_token;
      if (occInput && fcfg.occurrence) occInput.value = fcfg.occurrence;

      if (fname === 'retention' || fname === 'comments') {
        const isSkip     = !!(fcfg.skip || !fcfg.regex);
        const skipRadio  = block.querySelector('input[value="skip"]');
        const labelRadio = block.querySelector('input[value="label"]');
        const section    = block.querySelector('.label-section');
        if (isSkip) {
          if (skipRadio)  skipRadio.checked  = true;
          if (section)    section.classList.add('hidden');
        } else {
          if (labelRadio) labelRadio.checked = true;
          if (section)    section.classList.remove('hidden');
        }
      }
    });

    step2.classList.remove('hidden');
    step3.classList.remove('hidden');
    maybeShowStep4();
  });

  // ── Save ─────────────────────────────────────────────────────────────────────
  saveBtn.addEventListener('click', async () => {
    const cfg = buildConfig();
    if (!cfg.name) { alert('Vendor name is required'); return; }
    if (!cfg.detect_keywords.length) { alert('At least one detection keyword is required'); return; }

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';

    try {
      const res = await fetch('/api/vendors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      const data = await res.json();
      saveResult.textContent = `✓ Saved as vendors/${data.slug}.json — vendor is now active.`;
      saveResult.className = 'result-msg success';
      saveResult.classList.remove('hidden');
    } catch (err) {
      saveResult.textContent = 'Save failed: ' + err.message;
      saveResult.className = 'result-msg error';
      saveResult.classList.remove('hidden');
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Vendor';
    }
  });
}
