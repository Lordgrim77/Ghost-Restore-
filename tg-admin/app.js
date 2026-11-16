/* Telegram-Admin Support Case Console Client (Zero Inline JS / Zero innerHTML XSS) */
(function () {
  'use strict';

  const API_BASE = '/api/support';
  const POLL_INTERVAL_MS = 4000;
  const MAX_ATTACH_BYTES = 20 * 1024 * 1024;

  // Ephemeral in-memory session state only (never written to localStorage or URL)
  let sessionToken = '';
  let currentAdmin = null;
  let allCases = [];
  let counts = {};
  let activeFilter = 'ALL';
  let activeSearch = '';
  let selectedCaseCode = null;
  let selectedCaseDetail = null;
  let activeTab = 'chat';
  let pendingFile = null;
  let pollTimer = null;
  let currentPreviewBlobUrl = null;
  let currentEvidenceItem = null;
  const thumbBlobUrls = [];

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  // DOM References
  const gateView = document.getElementById('gateView');
  const consoleView = document.getElementById('consoleView');
  const gateSpinner = document.getElementById('gateSpinner');
  const gateLockBadge = document.getElementById('gateLockBadge');
  const gateTitle = document.getElementById('gateTitle');
  const gateMessage = document.getElementById('gateMessage');
  const gateActions = document.getElementById('gateActions');
  const btnRetryAuth = document.getElementById('btnRetryAuth');

  const btnMobileBack = document.getElementById('btnMobileBack');
  const adminRoleBadge = document.getElementById('adminRoleBadge');
  const adminIdentityLabel = document.getElementById('adminIdentityLabel');
  const btnRefreshAll = document.getElementById('btnRefreshAll');
  const btnThemeToggle = document.getElementById('btnThemeToggle');
  const caseSearchInput = document.getElementById('caseSearchInput');
  const inboxList = document.getElementById('inboxList');

  const detailEmpty = document.getElementById('detailEmpty');
  const detailBody = document.getElementById('detailBody');
  const detailCaseCode = document.getElementById('detailCaseCode');
  const detailStatusPill = document.getElementById('detailStatusPill');
  const detailPriorityPill = document.getElementById('detailPriorityPill');
  const detailClaimBadge = document.getElementById('detailClaimBadge');
  const detailCreatedAt = document.getElementById('detailCreatedAt');
  const detailSubject = document.getElementById('detailSubject');
  const detailCategory = document.getElementById('detailCategory');
  const detailReporter = document.getElementById('detailReporter');
  const detailMember = document.getElementById('detailMember');
  const detailContact = document.getElementById('detailContact');

  const btnClaimCase = document.getElementById('btnClaimCase');
  const btnOpenStatusModal = document.getElementById('btnOpenStatusModal');
  const btnDeleteCase = document.getElementById('btnDeleteCase');

  const chatMessages = document.getElementById('chatMessages');
  const chatPollStatus = document.getElementById('chatPollStatus');
  const adminChatForm = document.getElementById('adminChatForm');
  const adminFileInput = document.getElementById('adminFileInput');
  const btnPickAttach = document.getElementById('btnPickAttach');
  const adminAttachPreview = document.getElementById('adminAttachPreview');
  const adminAttachName = document.getElementById('adminAttachName');
  const btnRemoveAttach = document.getElementById('btnRemoveAttach');
  const adminReplyInput = document.getElementById('adminReplyInput');
  const btnSendReply = document.getElementById('btnSendReply');

  const evidenceGrid = document.getElementById('evidenceGrid');
  const detailDescription = document.getElementById('detailDescription');
  const detailResolutionCard = document.getElementById('detailResolutionCard');
  const detailResolutionNote = document.getElementById('detailResolutionNote');
  const detailAuditList = document.getElementById('detailAuditList');

  const tabBadgeChat = document.getElementById('tabBadgeChat');
  const tabBadgeEvidence = document.getElementById('tabBadgeEvidence');
  const toastBanner = document.getElementById('toastBanner');

  const evidenceDialog = document.getElementById('evidenceDialog');
  const evDialogTitle = document.getElementById('evDialogTitle');
  const evDialogMeta = document.getElementById('evDialogMeta');
  const evDialogStage = document.getElementById('evDialogStage');
  const btnCloseEvDialog = document.getElementById('btnCloseEvDialog');
  const btnEvSendDm = document.getElementById('btnEvSendDm');
  const btnEvDownload = document.getElementById('btnEvDownload');

  const statusDialog = document.getElementById('statusDialog');
  const statusForm = document.getElementById('statusForm');
  const statusSelect = document.getElementById('statusSelect');
  const resolutionNoteInput = document.getElementById('resolutionNoteInput');
  const btnCloseStatusDialog = document.getElementById('btnCloseStatusDialog');
  const btnCancelStatus = document.getElementById('btnCancelStatus');

  const deleteDialog = document.getElementById('deleteDialog');
  const deleteConfirmText = document.getElementById('deleteConfirmText');
  const btnCloseDeleteDialog = document.getElementById('btnCloseDeleteDialog');
  const btnCancelDelete = document.getElementById('btnCancelDelete');
  const btnConfirmDelete = document.getElementById('btnConfirmDelete');

  // ------------------------------------------------------------------
  // Theme Sync (Matches Website Obsidian Dark / Frost-Glass Light)
  // ------------------------------------------------------------------
  function applyTheme(mode) {
    const isLight = mode === 'light';
    const root = document.documentElement;
    root.classList.toggle('light-mode', isLight);
    root.classList.toggle('dark-mode', !isLight);
    root.setAttribute('data-theme', isLight ? 'light' : 'dark');
    if (tg) {
      const bgHex = isLight ? '#f8fafc' : '#090b10';
      try {
        if (typeof tg.setHeaderColor === 'function') tg.setHeaderColor(bgHex);
        if (typeof tg.setBackgroundColor === 'function') tg.setBackgroundColor(bgHex);
      } catch (_) {}
    }
  }

  function initTheme() {
    let initial = 'dark';
    if (tg && tg.colorScheme === 'light') {
      initial = 'light';
    }
    applyTheme(initial);
    if (tg && typeof tg.onEvent === 'function') {
      tg.onEvent('themeChanged', function () {
        applyTheme(tg.colorScheme === 'light' ? 'light' : 'dark');
      });
    }
  }

  btnThemeToggle.addEventListener('click', function () {
    const currentlyLight = document.documentElement.classList.contains('light-mode');
    applyTheme(currentlyLight ? 'dark' : 'light');
  });

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  let toastTimer = null;
  function showToast(msg) {
    toastBanner.textContent = String(msg || '');
    toastBanner.classList.remove('is-hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastBanner.classList.add('is-hidden');
    }, 3000);
  }

  function clearNode(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function formatStatusLabel(st) {
    const s = String(st || 'SUBMITTED').toUpperCase();
    if (s === 'SUBMITTED') return 'New';
    if (s === 'IN_REVIEW') return 'In Progress';
    if (s === 'CLOSED') return 'Resolved';
    if (s === 'REJECTED') return 'Dismissed';
    return s;
  }

  function formatSize(bytes) {
    const n = Number(bytes || 0);
    if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(2) + ' MB';
    return Math.max(1, Math.round(n / 1024)) + ' KB';
  }

  function formatTimestamp(isoStr) {
    if (!isoStr) return '';
    return String(isoStr).slice(0, 16).replace('T', ' ') + ' UTC';
  }

  function setMobileView(view) {
    consoleView.setAttribute('data-mobile-view', view);
    if (tg && tg.BackButton) {
      if (view === 'detail' && window.innerWidth < 860) {
        tg.BackButton.show();
      } else {
        tg.BackButton.hide();
      }
    }
  }

  function showGateError(title, message, allowRetry) {
    sessionToken = '';
    currentAdmin = null;
    stopPolling();
    consoleView.classList.add('is-hidden');
    gateView.classList.remove('is-hidden');
    gateSpinner.classList.add('is-hidden');
    gateLockBadge.classList.remove('is-hidden');
    gateTitle.textContent = title;
    gateMessage.textContent = message;
    if (allowRetry) {
      gateActions.classList.remove('is-hidden');
    } else {
      gateActions.classList.add('is-hidden');
    }
  }

  async function apiFetch(path, options = {}) {
    const hdrs = new Headers(options.headers || {});
    if (sessionToken) {
      hdrs.set('Authorization', 'Bearer ' + sessionToken);
    }
    const res = await fetch(API_BASE + path, {
      ...options,
      headers: hdrs,
      cache: 'no-store',
    });
    if (res.status === 401 || res.status === 403) {
      let errMsg = res.status === 403 ? 'Admin access required or revoked.' : 'Session expired.';
      try {
        const j = await res.clone().json();
        if (j && j.error) errMsg = j.error;
      } catch (_) {}
      if (res.status === 401 && !path.startsWith('/admin/auth')) {
        showGateError('Telegram Session Expired', errMsg, true);
      } else if (res.status === 403 && !path.includes('/delete') && options.method !== 'DELETE' && !path.includes('/claim')) {
        showGateError('Access Denied', errMsg, false);
      }
      throw new Error(errMsg);
    }
    return res;
  }

  function extractTargetCase(startParamFromServer) {
    const urlParams = new URLSearchParams(window.location.search);
    const qCase = (urlParams.get('case') || '').trim().toUpperCase();
    if (qCase && /^[A-Z0-9-]+$/.test(qCase)) return qCase;
    const rawStart = String(startParamFromServer || (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || '').trim();
    if (rawStart.toUpperCase().startsWith('CASE_')) {
      const candidate = rawStart.slice(5).trim().toUpperCase();
      if (/^[A-Z0-9-]+$/.test(candidate)) return candidate;
    }
    return null;
  }

  // ------------------------------------------------------------------
  // Authentication (Telegram WebApp initData -> In-Memory Bearer)
  // ------------------------------------------------------------------
  async function authenticateAdmin() {
    gateView.classList.remove('is-hidden');
    consoleView.classList.add('is-hidden');
    gateSpinner.classList.remove('is-hidden');
    gateLockBadge.classList.add('is-hidden');
    gateActions.classList.add('is-hidden');
    gateTitle.textContent = 'Verifying Admin Session';
    gateMessage.textContent = 'Checking Telegram cryptographic credentials...';

    const initData = tg && typeof tg.initData === 'string' ? tg.initData : '';
    if (!initData) {
      showGateError(
        'Telegram Admin Access Only',
        'This Support Console must be opened inside Telegram from the official Admin Bot. Direct browser access is disabled.',
        false
      );
      return;
    }

    try {
      const res = await fetch(API_BASE + '/admin/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
        cache: 'no-store',
      });
      const data = await res.json();
      if (!res.ok || !data.success || !data.token) {
        const allowRetry = res.status === 401;
        showGateError(
          res.status === 403 ? 'Access Denied' : 'Verification Failed',
          data.error || 'Could not verify Telegram administrator credentials.',
          allowRetry
        );
        return;
      }

      sessionToken = data.token;
      currentAdmin = data.admin;
      gateView.classList.add('is-hidden');
      consoleView.classList.remove('is-hidden');

      adminRoleBadge.textContent = currentAdmin.is_super_admin ? 'Super Admin' : 'Support Admin';
      adminRoleBadge.classList.toggle('is-super', Boolean(currentAdmin.is_super_admin));
      adminIdentityLabel.textContent = currentAdmin.display_name || '';

      const deepCase = extractTargetCase(data.start_param);
      await loadInbox(false);
      if (deepCase) {
        await openCase(deepCase);
      } else if (allCases.length > 0 && window.innerWidth >= 860 && !selectedCaseCode) {
        await openCase(allCases[0].case_code);
      }
      startPolling();
    } catch (err) {
      showGateError('Connection Error', err.message || 'Could not reach Support Hub.', true);
    }
  }

  btnRetryAuth.addEventListener('click', authenticateAdmin);

  // ------------------------------------------------------------------
  // Inbox Rendering
  // ------------------------------------------------------------------
  async function loadInbox(silent = true) {
    try {
      const params = new URLSearchParams();
      if (activeFilter !== 'ALL' && activeFilter !== 'UNREAD') {
        params.set('status', activeFilter);
      }
      if (activeSearch) {
        params.set('q', activeSearch);
      }
      const qStr = params.toString();
      const res = await apiFetch('/admin/cases' + (qStr ? '?' + qStr : ''));
      const data = await res.json();
      if (!data.success) return;
      counts = data.counts || {};
      allCases = data.cases || [];
      if (data.admin) {
        currentAdmin = { ...(currentAdmin || {}), ...data.admin };
        adminRoleBadge.textContent = currentAdmin.is_super_admin ? 'Super Admin' : 'Support Admin';
        adminRoleBadge.classList.toggle('is-super', Boolean(currentAdmin.is_super_admin));
      }
      renderCounts();
      renderInbox();
    } catch (err) {
      if (!silent) showToast('Failed to load cases: ' + err.message);
    }
  }

  function renderCounts() {
    document.getElementById('cntAll').textContent = String(counts.ALL || 0);
    document.getElementById('cntUnread').textContent = String(counts.UNREAD || 0);
    document.getElementById('cntSubmitted').textContent = String(counts.SUBMITTED || 0);
    document.getElementById('cntReview').textContent = String(counts.IN_REVIEW || 0);
    document.getElementById('cntClosed').textContent = String(counts.CLOSED || 0);
    document.getElementById('cntRejected').textContent = String(counts.REJECTED || 0);
  }

  function renderInbox() {
    clearNode(inboxList);
    const items = activeFilter === 'UNREAD'
      ? allCases.filter((c) => Boolean(c.unread))
      : allCases;

    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'gm-chat-empty';
      empty.textContent = 'No cases match the current filter.';
      inboxList.appendChild(empty);
      return;
    }

    for (const c of items) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tga-case-item' + (c.case_code === selectedCaseCode ? ' is-selected' : '');
      btn.setAttribute('role', 'listitem');
      btn.addEventListener('click', function () {
        openCase(c.case_code);
      });

      const top = document.createElement('div');
      top.className = 'tga-case-item-top';

      const badges = document.createElement('div');
      badges.className = 'tga-case-item-badges';

      const codeEl = document.createElement('span');
      codeEl.className = 'gm-case-code-pill';
      codeEl.textContent = '#' + c.case_code;
      badges.appendChild(codeEl);

      const stEl = document.createElement('span');
      const stLower = String(c.status || 'SUBMITTED').toLowerCase();
      stEl.className = 'gm-status-pill status-' + stLower;
      stEl.textContent = formatStatusLabel(c.status);
      badges.appendChild(stEl);

      top.appendChild(badges);

      if (c.unread) {
        const dot = document.createElement('span');
        dot.className = 'tga-unread-badge';
        dot.title = 'Unread update';
        top.appendChild(dot);
      }

      const subj = document.createElement('p');
      subj.className = 'tga-case-item-subject';
      subj.textContent = c.subject || 'No Subject';

      const snip = document.createElement('p');
      snip.className = 'tga-case-item-snippet';
      snip.textContent = c.last_message_preview || c.description_preview || '';

      const foot = document.createElement('div');
      foot.className = 'tga-case-item-foot';

      const leftFoot = document.createElement('span');
      const ownerTag = c.assigned_admin_name ? ' · ' + c.assigned_admin_name : '';
      leftFoot.textContent = `${c.priority || 'STANDARD'} · 📎 ${c.file_count || 0} · 💬 ${c.msg_count || 0}${ownerTag}`;

      const rightFoot = document.createElement('span');
      rightFoot.textContent = formatTimestamp(c.updated_at || c.created_at).slice(0, 10);

      foot.appendChild(leftFoot);
      foot.appendChild(rightFoot);

      btn.appendChild(top);
      btn.appendChild(subj);
      btn.appendChild(snip);
      btn.appendChild(foot);
      inboxList.appendChild(btn);
    }
  }

  // Filter Pills & Search
  document.getElementById('statusFilterBar').addEventListener('click', function (ev) {
    const pill = ev.target.closest('.tga-filter-pill');
    if (!pill) return;
    activeFilter = pill.getAttribute('data-status') || 'ALL';
    document.querySelectorAll('.tga-filter-pill').forEach((el) => {
      const isAct = el === pill;
      el.classList.toggle('active', isAct);
      el.setAttribute('aria-selected', String(isAct));
    });
    loadInbox(true);
  });

  let searchDebounce = null;
  caseSearchInput.addEventListener('input', function () {
    activeSearch = caseSearchInput.value.trim();
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(function () {
      loadInbox(true);
    }, 220);
  });

  btnRefreshAll.addEventListener('click', async function () {
    await loadInbox(false);
    if (selectedCaseCode) await openCase(selectedCaseCode, { preserveTab: true });
    showToast('Synced');
  });

  btnMobileBack.addEventListener('click', function () {
    setMobileView('inbox');
  });

  if (tg && tg.BackButton && typeof tg.BackButton.onClick === 'function') {
    tg.BackButton.onClick(function () {
      if (evidenceDialog.open) {
        closeEvidenceModal();
      } else if (statusDialog.open) {
        statusDialog.close();
      } else if (deleteDialog.open) {
        deleteDialog.close();
      } else {
        setMobileView('inbox');
      }
    });
  }

  // ------------------------------------------------------------------
  // Case Detail Rendering & Chat / Evidence / Audit
  // ------------------------------------------------------------------
  function revokeThumbUrls() {
    while (thumbBlobUrls.length) {
      const u = thumbBlobUrls.pop();
      try {
        URL.revokeObjectURL(u);
      } catch (_) {}
    }
  }

  async function openCase(caseCode, opts = {}) {
    selectedCaseCode = caseCode;
    setMobileView('detail');
    renderInbox();

    try {
      const res = await apiFetch('/admin/cases/' + encodeURIComponent(caseCode));
      const data = await res.json();
      if (!res.ok || !data.success || !data.case) {
        showToast(data.error || 'Case not found');
        return;
      }
      selectedCaseDetail = data.case;
      renderCaseDetail(selectedCaseDetail, opts);
      loadInbox(true);
    } catch (err) {
      showToast('Error loading case: ' + err.message);
    }
  }

  function renderCaseDetail(c, opts = {}) {
    detailEmpty.classList.add('is-hidden');
    detailBody.classList.remove('is-hidden');

    detailCaseCode.textContent = '#' + c.case_code;
    const stLower = String(c.status || 'SUBMITTED').toLowerCase();
    detailStatusPill.className = 'gm-status-pill status-' + stLower;
    detailStatusPill.textContent = formatStatusLabel(c.status);

    const prio = String(c.priority || 'STANDARD').toUpperCase();
    detailPriorityPill.className = 'tga-priority-pill' + (prio === 'CRITICAL' ? ' prio-critical' : prio === 'URGENT' ? ' prio-urgent' : '');
    detailPriorityPill.textContent = prio;

    if (c.assigned_admin_name) {
      detailClaimBadge.textContent = 'Claimed: ' + c.assigned_admin_name;
      detailClaimBadge.classList.remove('is-hidden');
    } else {
      detailClaimBadge.classList.add('is-hidden');
    }

    const isClaimedByMe = currentAdmin && c.assigned_admin_id && Number(c.assigned_admin_id) === Number(currentAdmin.user_id);
    if (!c.assigned_admin_id) {
      btnClaimCase.textContent = 'Claim Case';
      btnClaimCase.disabled = false;
    } else if (isClaimedByMe || (currentAdmin && currentAdmin.is_super_admin)) {
      btnClaimCase.textContent = isClaimedByMe ? 'Release Claim' : 'Take Over / Release';
      btnClaimCase.disabled = false;
    } else {
      btnClaimCase.textContent = 'Claimed by ' + c.assigned_admin_name;
      btnClaimCase.disabled = true;
    }

    btnDeleteCase.classList.toggle('is-hidden', !(currentAdmin && currentAdmin.is_super_admin));

    detailCreatedAt.textContent = formatTimestamp(c.created_at);
    detailSubject.textContent = c.subject || 'No Subject';
    detailCategory.textContent = 'Category: ' + (c.category || 'Support');
    detailReporter.textContent = 'Reporter: ' + (c.reporter_alias || 'Anonymous');

    if (c.member_email) {
      detailMember.textContent = 'Member: ' + c.member_email;
      detailMember.classList.remove('is-hidden');
    } else {
      detailMember.classList.add('is-hidden');
    }

    if (c.reporter_contact) {
      detailContact.textContent = 'Contact: ' + c.reporter_contact;
      detailContact.classList.remove('is-hidden');
    } else {
      detailContact.classList.add('is-hidden');
    }

    const msgs = c.messages || [];
    const files = c.files || [];
    tabBadgeChat.textContent = String(msgs.length);
    tabBadgeEvidence.textContent = String(files.length);

    renderChatMessages(msgs);
    renderEvidenceGrid(c.case_code, files);
    renderDetailsAndAudit(c);

    if (!opts.preserveTab) {
      switchTab(activeTab);
    }
  }

  function renderChatMessages(msgs) {
    const prevAtBottom = (chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight) < 60;
    clearNode(chatMessages);

    if (!msgs.length) {
      const empty = document.createElement('div');
      empty.className = 'gm-chat-empty';
      empty.textContent = 'No chat messages yet. Send the first reply to start conversing with the reporter.';
      chatMessages.appendChild(empty);
      return;
    }

    for (const m of msgs) {
      const isAdmin = m.sender_type === 'admin';
      const bubble = document.createElement('div');
      bubble.className = 'gm-msg-bubble ' + (isAdmin ? 'gm-msg-admin' : 'gm-msg-reporter');

      const senderEl = document.createElement('div');
      senderEl.className = 'gm-msg-sender';
      senderEl.textContent = isAdmin ? (m.sender_name || 'Support') : (m.sender_name || 'Reporter');

      const bodyEl = document.createElement('div');
      bodyEl.textContent = m.message_text || '';

      const metaEl = document.createElement('div');
      metaEl.className = 'gm-msg-meta';
      metaEl.textContent = formatTimestamp(m.created_at);

      bubble.appendChild(senderEl);
      bubble.appendChild(bodyEl);
      bubble.appendChild(metaEl);
      chatMessages.appendChild(bubble);
    }

    if (prevAtBottom || msgs.length <= 4) {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }

  function renderEvidenceGrid(caseCode, files) {
    revokeThumbUrls();
    clearNode(evidenceGrid);

    if (!files.length) {
      const empty = document.createElement('div');
      empty.className = 'tga-glass-card tga-empty-detail';
      empty.textContent = 'No evidence files attached to this case.';
      evidenceGrid.appendChild(empty);
      return;
    }

    for (const f of files) {
      const card = document.createElement('article');
      card.className = 'tga-glass-card tga-evidence-card';

      const thumbWrap = document.createElement('div');
      thumbWrap.className = 'tga-ev-thumb-wrap';
      const lowerName = String(f.name || '').toLowerCase();
      const isImage = /\.(jpg|jpeg|png|webp|gif|bmp)$/.test(lowerName) && f.previewable;
      if (isImage) {
        const placeholder = document.createElement('span');
        placeholder.className = 'tga-ev-thumb-icon';
        placeholder.textContent = '🖼️';
        thumbWrap.appendChild(placeholder);
        loadThumbnailAsync(caseCode, f.id, thumbWrap);
      } else {
        const icon = document.createElement('span');
        icon.className = 'tga-ev-thumb-icon';
        icon.textContent = /\.(mp4|webm|mov)$/.test(lowerName)
          ? '🎬'
          : /\.(mp3|wav|ogg|m4a)$/.test(lowerName)
            ? '🎧'
            : /\.pdf$/.test(lowerName)
              ? '📕'
              : /\.(txt|log|csv|json|eml)$/.test(lowerName)
                ? '📄'
                : '📦';
        thumbWrap.appendChild(icon);
      }

      const nameEl = document.createElement('p');
      nameEl.className = 'tga-ev-name';
      nameEl.textContent = f.name || 'evidence.bin';

      const metaEl = document.createElement('div');
      metaEl.className = 'tga-ev-meta';
      const shaShort = (f.sha256 || '').slice(0, 14);
      const storageTxt = f.storage === 'telegram' ? 'TG Vault' : 'Local';
      metaEl.textContent = `${formatSize(f.size)} · ${storageTxt} · SHA:${shaShort}`;

      const actions = document.createElement('div');
      actions.className = 'tga-ev-actions';

      if (f.previewable) {
        const inspectBtn = document.createElement('button');
        inspectBtn.type = 'button';
        inspectBtn.className = 'tga-btn tga-btn-primary';
        inspectBtn.textContent = 'Inspect';
        inspectBtn.addEventListener('click', function () {
          openEvidenceModal(caseCode, f);
        });
        actions.appendChild(inspectBtn);
      }

      if (f.can_direct_dl) {
        const dlBtn = document.createElement('button');
        dlBtn.type = 'button';
        dlBtn.className = 'tga-btn tga-btn-secondary';
        dlBtn.textContent = 'Download';
        dlBtn.addEventListener('click', function () {
          triggerEvidenceDownload(caseCode, f);
        });
        actions.appendChild(dlBtn);
      }

      const dmBtn = document.createElement('button');
      dmBtn.type = 'button';
      dmBtn.className = 'tga-btn tga-btn-secondary';
      dmBtn.textContent = f.can_direct_dl ? 'Send to DM' : 'Send (>20MB) to DM';
      dmBtn.addEventListener('click', function () {
        sendEvidenceToDm(caseCode, f);
      });
      actions.appendChild(dmBtn);

      card.appendChild(thumbWrap);
      card.appendChild(nameEl);
      card.appendChild(metaEl);
      card.appendChild(actions);
      evidenceGrid.appendChild(card);
    }
  }

  async function loadThumbnailAsync(caseCode, evId, container) {
    try {
      const res = await apiFetch(`/admin/cases/${encodeURIComponent(caseCode)}/evidence/${evId}?preview=1`, {
        headers: { 'X-Preview': '1' },
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      thumbBlobUrls.push(blobUrl);
      const img = document.createElement('img');
      img.className = 'tga-ev-thumb-img';
      img.alt = 'Evidence thumbnail';
      img.src = blobUrl;
      clearNode(container);
      container.appendChild(img);
    } catch (_) {}
  }

  function renderDetailsAndAudit(c) {
    detailDescription.textContent = c.description || '';
    if (c.resolution_note) {
      detailResolutionNote.textContent = c.resolution_note;
      detailResolutionCard.classList.remove('is-hidden');
    } else {
      detailResolutionCard.classList.add('is-hidden');
    }

    clearNode(detailAuditList);
    const logs = c.audit_logs || [];
    if (!logs.length) {
      const li = document.createElement('li');
      li.className = 'tga-audit-row';
      li.textContent = 'No audit events recorded.';
      detailAuditList.appendChild(li);
      return;
    }

    for (const a of logs.slice().reverse()) {
      const li = document.createElement('li');
      li.className = 'tga-audit-row';

      const top = document.createElement('div');
      top.className = 'tga-audit-top';
      const act = document.createElement('span');
      act.textContent = (a.action || '') + ' · ' + (a.actor || '');
      const ts = document.createElement('span');
      ts.className = 'tga-meta-muted';
      ts.textContent = formatTimestamp(a.timestamp);
      top.appendChild(act);
      top.appendChild(ts);

      const det = document.createElement('div');
      det.textContent = a.details || '';

      li.appendChild(top);
      li.appendChild(det);
      detailAuditList.appendChild(li);
    }
  }

  // Detail Tabs Switching
  function switchTab(tabName) {
    activeTab = tabName;
    document.querySelectorAll('.tga-detail-tabs .gm-support-tab').forEach((btn) => {
      const isAct = btn.getAttribute('data-tab') === tabName;
      btn.classList.toggle('active', isAct);
      btn.setAttribute('aria-selected', String(isAct));
    });
    document.getElementById('tabPanelChat').classList.toggle('active', tabName === 'chat');
    document.getElementById('tabPanelEvidence').classList.toggle('active', tabName === 'evidence');
    document.getElementById('tabPanelDetails').classList.toggle('active', tabName === 'details');
  }

  document.querySelector('.tga-detail-tabs').addEventListener('click', function (ev) {
    const tabBtn = ev.target.closest('.gm-support-tab');
    if (!tabBtn) return;
    switchTab(tabBtn.getAttribute('data-tab') || 'chat');
  });

  // ------------------------------------------------------------------
  // Chat Reply & Attachment
  // ------------------------------------------------------------------
  btnPickAttach.addEventListener('click', function () {
    adminFileInput.click();
  });

  adminFileInput.addEventListener('change', function () {
    const file = adminFileInput.files && adminFileInput.files[0];
    if (!file) return;
    if (file.size > MAX_ATTACH_BYTES) {
      showToast('File exceeds 20 MB per-file limit.');
      adminFileInput.value = '';
      return;
    }
    pendingFile = file;
    adminAttachName.textContent = `${file.name} (${formatSize(file.size)})`;
    adminAttachPreview.classList.remove('is-hidden');
  });

  btnRemoveAttach.addEventListener('click', function () {
    pendingFile = null;
    adminFileInput.value = '';
    adminAttachPreview.classList.add('is-hidden');
  });

  let isSendingReply = false;
  adminChatForm.addEventListener('submit', async function (ev) {
    ev.preventDefault();
    if (isSendingReply || !selectedCaseCode) return;
    const text = adminReplyInput.value.trim();
    if (!text && !pendingFile) return;

    isSendingReply = true;
    btnSendReply.disabled = true;
    btnSendReply.textContent = 'Sending...';

    try {
      let res;
      if (pendingFile) {
        const fd = new FormData();
        if (text) fd.append('message', text);
        fd.append('attachment', pendingFile);
        res = await apiFetch(`/admin/cases/${encodeURIComponent(selectedCaseCode)}/messages`, {
          method: 'POST',
          body: fd,
        });
      } else {
        res = await apiFetch(`/admin/cases/${encodeURIComponent(selectedCaseCode)}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text }),
        });
      }
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to send reply.');
      }
      adminReplyInput.value = '';
      pendingFile = null;
      adminFileInput.value = '';
      adminAttachPreview.classList.add('is-hidden');
      await openCase(selectedCaseCode, { preserveTab: true });
      showToast('Reply sent');
    } catch (err) {
      showToast('Send failed: ' + err.message);
    } finally {
      isSendingReply = false;
      btnSendReply.disabled = false;
      btnSendReply.textContent = 'Send';
    }
  });

  // ------------------------------------------------------------------
  // Evidence Inspection Modal, Download & Send to DM
  // ------------------------------------------------------------------
  function closeEvidenceModal() {
    if (currentPreviewBlobUrl) {
      try {
        URL.revokeObjectURL(currentPreviewBlobUrl);
      } catch (_) {}
      currentPreviewBlobUrl = null;
    }
    clearNode(evDialogStage);
    if (evidenceDialog.open) evidenceDialog.close();
  }

  btnCloseEvDialog.addEventListener('click', closeEvidenceModal);
  evidenceDialog.addEventListener('click', function (ev) {
    if (ev.target === evidenceDialog) closeEvidenceModal();
  });
  evidenceDialog.addEventListener('close', function () {
    if (currentPreviewBlobUrl) {
      try {
        URL.revokeObjectURL(currentPreviewBlobUrl);
      } catch (_) {}
      currentPreviewBlobUrl = null;
    }
  });

  async function openEvidenceModal(caseCode, item) {
    currentEvidenceItem = item;
    evDialogTitle.textContent = item.name || 'Evidence Preview';
    evDialogMeta.textContent = `${formatSize(item.size)} · SHA-256: ${item.sha256 || ''}`;
    btnEvDownload.classList.toggle('is-hidden', !item.can_direct_dl);

    clearNode(evDialogStage);
    const loading = document.createElement('div');
    loading.className = 'tga-spinner';
    evDialogStage.appendChild(loading);
    if (typeof evidenceDialog.showModal === 'function' && !evidenceDialog.open) {
      evidenceDialog.showModal();
    }

    try {
      const res = await apiFetch(`/admin/cases/${encodeURIComponent(caseCode)}/evidence/${item.id}?preview=1`, {
        headers: { 'X-Preview': '1' },
      });
      if (!res.ok) {
        let errMsg = `HTTP ${res.status}`;
        try {
          const j = await res.json();
          if (j && j.error) errMsg = j.error;
        } catch (_) {}
        throw new Error(errMsg);
      }
      const lower = String(item.name || '').toLowerCase();
      clearNode(evDialogStage);
      if (/\.(txt|log|csv|json|eml)$/.test(lower)) {
        const textContent = await res.text();
        const pre = document.createElement('pre');
        pre.className = 'tga-ev-stage-pre';
        pre.textContent = textContent;
        evDialogStage.appendChild(pre);
      } else {
        const blob = await res.blob();
        currentPreviewBlobUrl = URL.createObjectURL(blob);
        if (/\.(jpg|jpeg|png|webp|gif|bmp)$/.test(lower)) {
          const img = document.createElement('img');
          img.className = 'tga-ev-stage-img';
          img.alt = item.name || 'Evidence image';
          img.src = currentPreviewBlobUrl;
          evDialogStage.appendChild(img);
        } else if (/\.(mp4|webm|mov)$/.test(lower)) {
          const vid = document.createElement('video');
          vid.className = 'tga-ev-stage-video';
          vid.controls = true;
          vid.src = currentPreviewBlobUrl;
          evDialogStage.appendChild(vid);
        } else if (/\.(mp3|wav|ogg|m4a)$/.test(lower)) {
          const aud = document.createElement('audio');
          aud.controls = true;
          aud.src = currentPreviewBlobUrl;
          evDialogStage.appendChild(aud);
        } else if (/\.pdf$/.test(lower)) {
          const frame = document.createElement('iframe');
          frame.className = 'tga-ev-stage-pdf';
          frame.setAttribute('sandbox', 'allow-same-origin');
          frame.title = item.name || 'PDF Preview';
          frame.src = currentPreviewBlobUrl;
          evDialogStage.appendChild(frame);
        } else {
          const fallback = document.createElement('p');
          fallback.textContent = 'Inline preview unavailable for this file type. Use Download or Send to Bot DM.';
          evDialogStage.appendChild(fallback);
        }
      }
    } catch (err) {
      clearNode(evDialogStage);
      const errP = document.createElement('p');
      errP.textContent = 'Preview error: ' + err.message;
      evDialogStage.appendChild(errP);
    }
  }

  async function triggerEvidenceDownload(caseCode, item) {
    try {
      const tRes = await apiFetch(`/admin/cases/${encodeURIComponent(caseCode)}/evidence/${item.id}/ticket`, {
        method: 'POST',
      });
      const tData = await tRes.json();
      if (!tRes.ok || !tData.url_path) {
        throw new Error(tData.error || 'Could not generate download link');
      }
      const absUrl = window.location.origin + tData.url_path;
      if (tg && typeof tg.downloadFile === 'function') {
        tg.downloadFile({ url: absUrl, file_name: tData.filename || item.name || 'evidence.bin' });
        showToast('Download started');
        return;
      }
      // Browser / older WebView fallback: direct navigation consumes one-time ticket
      const a = document.createElement('a');
      a.href = absUrl;
      a.download = tData.filename || item.name || 'evidence.bin';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      showToast('Download error: ' + err.message);
    }
  }

  async function sendEvidenceToDm(caseCode, item) {
    try {
      const res = await apiFetch(`/admin/cases/${encodeURIComponent(caseCode)}/evidence/${item.id}/send-dm`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to forward to DM');
      }
      showToast('Sent copy to your Bot DM');
    } catch (err) {
      showToast(err.message);
    }
  }

  btnEvDownload.addEventListener('click', function () {
    if (selectedCaseCode && currentEvidenceItem) {
      triggerEvidenceDownload(selectedCaseCode, currentEvidenceItem);
    }
  });

  btnEvSendDm.addEventListener('click', function () {
    if (selectedCaseCode && currentEvidenceItem) {
      sendEvidenceToDm(selectedCaseCode, currentEvidenceItem);
    }
  });

  // ------------------------------------------------------------------
  // Claim / Update Status / Super Admin Delete
  // ------------------------------------------------------------------
  btnClaimCase.addEventListener('click', async function () {
    if (!selectedCaseDetail || !selectedCaseCode) return;
    const isClaimed = Boolean(selectedCaseDetail.assigned_admin_id);
    try {
      const res = await apiFetch(`/admin/cases/${encodeURIComponent(selectedCaseCode)}/claim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: isClaimed ? 'release' : 'claim' }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Action failed');
      await openCase(selectedCaseCode, { preserveTab: true });
      showToast(isClaimed ? 'Claim released' : 'Case claimed');
    } catch (err) {
      showToast(err.message);
    }
  });

  btnOpenStatusModal.addEventListener('click', function () {
    if (!selectedCaseDetail) return;
    statusSelect.value = selectedCaseDetail.status || 'IN_REVIEW';
    resolutionNoteInput.value = selectedCaseDetail.resolution_note || '';
    if (typeof statusDialog.showModal === 'function') statusDialog.showModal();
  });

  btnCloseStatusDialog.addEventListener('click', function () { statusDialog.close(); });
  btnCancelStatus.addEventListener('click', function () { statusDialog.close(); });
  statusDialog.addEventListener('click', function (ev) {
    if (ev.target === statusDialog) statusDialog.close();
  });

  statusForm.addEventListener('submit', async function (ev) {
    ev.preventDefault();
    if (!selectedCaseCode) return;
    try {
      const res = await apiFetch(`/admin/cases/${encodeURIComponent(selectedCaseCode)}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: statusSelect.value,
          resolution_note: resolutionNoteInput.value.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Update failed');
      statusDialog.close();
      await openCase(selectedCaseCode, { preserveTab: true });
      showToast('Status updated to ' + formatStatusLabel(statusSelect.value));
    } catch (err) {
      showToast(err.message);
    }
  });

  btnDeleteCase.addEventListener('click', function () {
    if (!selectedCaseDetail || !(currentAdmin && currentAdmin.is_super_admin)) return;
    deleteConfirmText.textContent =
      `Permanently delete #${selectedCaseDetail.case_code} (${selectedCaseDetail.subject})? ` +
      'This removes all messages, audit records, Telegram Storage Group evidence files, and alert cards.';
    if (typeof deleteDialog.showModal === 'function') deleteDialog.showModal();
  });

  btnCloseDeleteDialog.addEventListener('click', function () { deleteDialog.close(); });
  btnCancelDelete.addEventListener('click', function () { deleteDialog.close(); });
  deleteDialog.addEventListener('click', function (ev) {
    if (ev.target === deleteDialog) deleteDialog.close();
  });

  btnConfirmDelete.addEventListener('click', async function () {
    if (!selectedCaseCode) return;
    btnConfirmDelete.disabled = true;
    try {
      const res = await apiFetch(`/admin/cases/${encodeURIComponent(selectedCaseCode)}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Delete failed');
      deleteDialog.close();
      const deletedCode = selectedCaseCode;
      selectedCaseCode = null;
      selectedCaseDetail = null;
      detailBody.classList.add('is-hidden');
      detailEmpty.classList.remove('is-hidden');
      setMobileView('inbox');
      await loadInbox(true);
      showToast('Deleted #' + deletedCode);
    } catch (err) {
      showToast(err.message);
    } finally {
      btnConfirmDelete.disabled = false;
    }
  });

  // ------------------------------------------------------------------
  // Live Polling (Pauses When Hidden)
  // ------------------------------------------------------------------
  function startPolling() {
    stopPolling();
    pollTimer = setInterval(async function () {
      if (document.hidden || !sessionToken) return;
      await loadInbox(true);
      if (selectedCaseCode) {
        try {
          const res = await apiFetch('/admin/cases/' + encodeURIComponent(selectedCaseCode));
          const data = await res.json();
          if (res.ok && data.success && data.case) {
            const oldCount = (selectedCaseDetail && selectedCaseDetail.messages) ? selectedCaseDetail.messages.length : 0;
            const newCount = (data.case.messages || []).length;
            const oldEv = (selectedCaseDetail && selectedCaseDetail.files) ? selectedCaseDetail.files.length : 0;
            const newEv = (data.case.files || []).length;
            const oldSt = selectedCaseDetail ? selectedCaseDetail.status : '';
            selectedCaseDetail = data.case;
            if (oldCount !== newCount || oldEv !== newEv || oldSt !== data.case.status) {
              renderCaseDetail(selectedCaseDetail, { preserveTab: true });
            }
          }
        } catch (_) {}
      }
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && sessionToken) {
      chatPollStatus.textContent = 'Live sync active';
      loadInbox(true);
    } else if (document.hidden) {
      chatPollStatus.textContent = 'Paused (background)';
    }
  });

  // Bootstrap
  initTheme();
  if (tg) {
    try {
      tg.ready();
      if (typeof tg.expand === 'function') tg.expand();
    } catch (_) {}
  }
  authenticateAdmin();
})();
