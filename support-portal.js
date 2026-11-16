/* Client-Side Engine for Support Portal (Externalized from page-support.hbs for Strict CSP) */
(function () {
    const memberMeta = document.getElementById('gm-support-member-meta');
    const isLoggedIn = Boolean(memberMeta && memberMeta.getAttribute('data-logged-in') === 'true');
    window.GHOST_MEMBER = isLoggedIn ? {
        loggedIn: true,
        email: memberMeta.getAttribute('data-email') || '',
        name: memberMeta.getAttribute('data-name') || '',
        uuid: memberMeta.getAttribute('data-uuid') || ''
    } : {
        loggedIn: false,
        email: null,
        name: null,
        uuid: null
    };

    const IS_LOCAL_DEV = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') && window.location.port !== '8080';
    let API_BASE = '/api/support';
    let currentCaseCode = null;
    let currentAccessKey = null;
    let selectedFiles = [];
    let pollInterval = null;

    // =============================================================
    // Security Verification Challenge Engine
    // =============================================================
    let activeCaptcha = null;
    let isFetchingCaptcha = false;

    async function fetchCaptcha() {
        if (isFetchingCaptcha) return;
        const visual = document.getElementById('gmCaptchaVisual');
        if (!visual) return;
        isFetchingCaptcha = true;
        visual.innerHTML = '<span class="gm-captcha-loading">Loading challenge...</span>';

        const candidateBases = [
            '/api/support',
            (window.location.origin ? `${window.location.origin}/api/support` : ''),
            ...(IS_LOCAL_DEV ? ['http://127.0.0.1:8080'] : [])
        ];
        const uniqueBases = Array.from(new Set(candidateBases.filter(Boolean)));
        let fetchedData = null;
        let lastError = null;

        for (const base of uniqueBases) {
            try {
                const cleanBase = base.replace(/\/+$/, '');
                const url = `${cleanBase}/captcha?_t=${Date.now()}`;
                const res = await fetch(url, {
                    method: 'GET',
                    headers: { 'Accept': 'application/json' },
                    cache: 'no-store'
                });
                if (res.ok) {
                    fetchedData = await res.json();
                    if (fetchedData && fetchedData.svg && fetchedData.challenge_id) {
                        API_BASE = cleanBase;
                        break;
                    }
                } else {
                    lastError = new Error(`HTTP ${res.status}`);
                }
            } catch (err) {
                lastError = err;
            }
        }

        isFetchingCaptcha = false;

        if (fetchedData && fetchedData.svg) {
            activeCaptcha = fetchedData;
            visual.innerHTML = fetchedData.svg;
            const cid = document.getElementById('gmCaptchaId');
            const cts = document.getElementById('gmCaptchaTimestamp');
            const csig = document.getElementById('gmCaptchaSignature');
            const cnon = document.getElementById('gmCaptchaNonce');
            const csol = document.getElementById('gmCaptchaSolution');
            const input = document.getElementById('gmCaptchaInput');

            if (cid) cid.value = fetchedData.challenge_id;
            if (cts) cts.value = fetchedData.timestamp;
            if (csig) csig.value = fetchedData.signature;
            if (cnon) cnon.value = '';
            if (csol) csol.value = '';
            if (input) {
                input.value = '';
                input.disabled = false;
            }
        } else {
            console.error('[Support Hub] Failed to fetch captcha challenge:', lastError);
            visual.innerHTML = '<span class="gm-captcha-error">Failed to load challenge. <button type="button" class="gm-captcha-retry-btn" data-action="refresh-captcha">Tap refresh</button></span>';
        }
    }

    window.refreshCaptcha = function () {
        activeCaptcha = null;
        fetchCaptcha();
    };

    async function sha256Hex(str) {
        const buf = new TextEncoder().encode(str);
        const digest = await crypto.subtle.digest('SHA-256', buf);
        return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    async function solveProofOfWork(challengeId, difficulty) {
        const prefix = '0'.repeat(difficulty);
        let nonce = 0;
        while (true) {
            const hash = await sha256Hex(`${challengeId}:${nonce}`);
            if (hash.startsWith(prefix)) {
                return { nonce: String(nonce), hash };
            }
            nonce++;
            if (nonce % 500 === 0) {
                await new Promise(r => setTimeout(r, 0));
            }
        }
    }

    // Tab Switching
    window.switchSupportTab = function (tabName) {
        if (tabName === 'mycases' && (!window.GHOST_MEMBER || !window.GHOST_MEMBER.loggedIn)) {
            tabName = 'submit';
        }
        document.querySelectorAll('.gm-support-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.gm-support-panel').forEach(p => p.classList.remove('active'));

        const btnSubmit = document.getElementById('tabBtnSubmit');
        const panelSubmit = document.getElementById('panelSubmit');
        const btnMyCases = document.getElementById('tabBtnMyCases');
        const panelMyCases = document.getElementById('panelMyCases');
        const btnTrack = document.getElementById('tabBtnTrack');
        const panelTrack = document.getElementById('panelTrack');

        if (tabName === 'submit') {
            if (btnSubmit) btnSubmit.classList.add('active');
            if (panelSubmit) panelSubmit.classList.add('active');
            if (!activeCaptcha) fetchCaptcha();
        } else if (tabName === 'mycases') {
            if (btnMyCases) btnMyCases.classList.add('active');
            if (panelMyCases) panelMyCases.classList.add('active');
            fetchMemberCases();
        } else if (tabName === 'track') {
            if (btnTrack) btnTrack.classList.add('active');
            if (panelTrack) panelTrack.classList.add('active');
            checkSavedCase();
        }
    };

    // Anonymity Checkbox Handlers
    window.toggleMemberAnon = function (isAnon) {
        const banner = document.getElementById('memberStatusBanner');
        if (banner) {
            banner.style.opacity = isAnon ? '0.4' : '1';
        }
    };

    window.toggleAnonFields = function (isAnon) {
        const fields = document.getElementById('anonFields');
        if (fields) {
            fields.style.display = isAnon ? 'none' : 'block';
        }
    };

    // File Drag & Drop Handling
    window.handleDragOver = function (e) {
        e.preventDefault();
        document.getElementById('gmDropzone').classList.add('drag-active');
    };

    window.handleDragLeave = function (e) {
        e.preventDefault();
        document.getElementById('gmDropzone').classList.remove('drag-active');
    };

    window.handleFileDrop = function (e) {
        e.preventDefault();
        document.getElementById('gmDropzone').classList.remove('drag-active');
        if (e.dataTransfer && e.dataTransfer.files) {
            addFiles(e.dataTransfer.files);
        }
    };

    window.handleFileSelect = function (e) {
        if (e.target && e.target.files) {
            addFiles(e.target.files);
        }
    };

    const MAX_PER_FILE_BYTES = 20 * 1024 * 1024;

    function addFiles(fileList) {
        for (let i = 0; i < fileList.length; i++) {
            if (fileList[i].size > MAX_PER_FILE_BYTES) {
                alert(`File "${fileList[i].name}" exceeds the 20 MB per-file limit.`);
                continue;
            }
            if (selectedFiles.length >= 10) {
                alert('Maximum 10 attachments allowed per report.');
                break;
            }
            selectedFiles.push(fileList[i]);
        }
        renderSelectedFiles();
    }

    window.removeFile = function (index) {
        selectedFiles.splice(index, 1);
        renderSelectedFiles();
    };

    function renderSelectedFiles() {
        const list = document.getElementById('gmFileList');
        if (!selectedFiles.length) {
            list.style.display = 'none';
            list.innerHTML = '';
            return;
        }
        list.style.display = 'flex';
        list.innerHTML = selectedFiles.map((f, i) => {
            const sizeKb = (f.size / 1024).toFixed(1);
            return `
        <div class="gm-file-item">
            <span>📄 <strong>${escapeHtml(f.name)}</strong> (${sizeKb} KB)</span>
            <button type="button" class="gm-file-remove" data-remove-file="${i}">✕</button>
        </div>
    `;
        }).join('');
    }

    let isSubmittingReport = false;
    const waitDialog = document.getElementById('gmReportWaitingDialog');
    if (waitDialog) {
        waitDialog.addEventListener('cancel', function (ev) {
            if (isSubmittingReport) {
                ev.preventDefault();
            }
        });
    }

    function openWaitingDialog(message) {
        const desc = document.getElementById('gmWaitingDialogDesc');
        if (desc && message) desc.textContent = message;
        if (waitDialog && typeof waitDialog.showModal === 'function' && !waitDialog.open) {
            waitDialog.showModal();
        }
    }

    function updateWaitingDialog(message) {
        const desc = document.getElementById('gmWaitingDialogDesc');
        if (desc && message) desc.textContent = message;
    }

    function closeWaitingDialog() {
        if (waitDialog && waitDialog.open && typeof waitDialog.close === 'function') {
            waitDialog.close();
        }
    }

    // Submit Report Handler
    window.handleCaseSubmit = async function (e) {
        e.preventDefault();
        if (isSubmittingReport) return;

        const alertBox = document.getElementById('caseSubmitAlert');
        const submitBtn = document.getElementById('btnSubmitCase');
        alertBox.style.display = 'none';

        const captchaInput = document.getElementById('gmCaptchaInput');
        const userSolution = captchaInput ? captchaInput.value.trim() : '';
        if (!userSolution) {
            alertBox.className = 'gm-submit-alert error';
            alertBox.textContent = 'Please type the answer for the security check before submitting.';
            alertBox.style.display = 'block';
            if (captchaInput) captchaInput.focus();
            return;
        }

        isSubmittingReport = true;
        submitBtn.disabled = true;
        submitBtn.querySelector('.gm-btn-text').textContent = 'Submitting...';
        openWaitingDialog('Checking your submission...');

        try {
            // Let the waiting dialog paint before CPU-intensive verification work runs
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

            // Solve Proof-of-Work in background
            const diff = (activeCaptcha && activeCaptcha.difficulty) ? activeCaptcha.difficulty : 4;
            const cid = document.getElementById('gmCaptchaId').value;
            const powResult = await solveProofOfWork(cid, diff);

            document.getElementById('gmCaptchaNonce').value = powResult.nonce;
            document.getElementById('gmCaptchaSolution').value = userSolution;

            const uploadMsg = selectedFiles.length > 0
                ? `Uploading your report and ${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'}...`
                : 'Sending your report...';
            updateWaitingDialog(uploadMsg);

            const formData = new FormData(document.getElementById('gmSupportForm'));
            formData.set('captcha_solution', userSolution);
            formData.set('captcha_nonce', powResult.nonce);

            // Attach member identity if logged in and not opting out
            const anonCheck = document.getElementById('anonToggle');
            const isAnon = anonCheck ? anonCheck.checked : false;

            if (window.GHOST_MEMBER && window.GHOST_MEMBER.loggedIn && !isAnon) {
                formData.set('member_email', window.GHOST_MEMBER.email);
                if (window.GHOST_MEMBER.uuid) formData.set('member_uuid', window.GHOST_MEMBER.uuid);
                if (!formData.get('reporter_alias')) {
                    formData.set('reporter_alias', window.GHOST_MEMBER.name || window.GHOST_MEMBER.email.split('@')[0]);
                }
            }

            // Append evidence files
            selectedFiles.forEach(file => {
                formData.append('evidence', file);
            });

            const res = await fetch(`${API_BASE}/cases`, {
                method: 'POST',
                credentials: 'same-origin',
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || `Server responded with status ${res.status}`);
            }

            // Save credentials
            currentCaseCode = data.case_code;
            currentAccessKey = data.access_key;

            // Persist to local storage
            localStorage.setItem('gm_active_case_code', currentCaseCode);
            localStorage.setItem('gm_active_access_key', currentAccessKey);

            saveCaseToLocalCache({
                case_code: currentCaseCode,
                access_key: currentAccessKey,
                subject: document.getElementById('caseSubject').value.trim(),
                category: document.getElementById('caseCategory').value,
                priority: document.getElementById('casePriority').value,
                status: 'SUBMITTED',
                created_at: new Date().toISOString()
            });

            // Display success card
            document.getElementById('gmSupportForm').style.display = 'none';
            document.getElementById('caseSuccessCard').style.display = 'block';
            document.getElementById('resCaseCode').textContent = currentCaseCode;
            document.getElementById('resAccessKey').textContent = currentAccessKey;

            const badge = document.getElementById('activeCaseBadge');
            if (badge) badge.style.display = 'inline-block';

            // Refresh My Reports count
            updateMyCasesCount();

        } catch (err) {
            alertBox.className = 'gm-submit-alert error';
            alertBox.textContent = `Could not submit report: ${err.message}`;
            alertBox.style.display = 'block';
        } finally {
            isSubmittingReport = false;
            closeWaitingDialog();
            submitBtn.disabled = false;
            submitBtn.querySelector('.gm-btn-text').textContent = 'Submit Report';
        }
    };

    // Store in browser cache for "My Cases"
    function saveCaseToLocalCache(c) {
        try {
            const raw = localStorage.getItem('gm_user_cases') || '[]';
            const list = JSON.parse(raw);
            if (!list.some(item => item.case_code === c.case_code)) {
                list.unshift(c);
                localStorage.setItem('gm_user_cases', JSON.stringify(list.slice(0, 50)));
            }
        } catch (e) { }
    }

    function getLocalCachedCases() {
        try {
            const raw = localStorage.getItem('gm_user_cases') || '[]';
            return JSON.parse(raw);
        } catch (e) {
            return [];
        }
    }

    // Fetch and display Member Cases
    window.fetchMemberCases = async function () {
        const loading = document.getElementById('myCasesLoading');
        const empty = document.getElementById('myCasesEmpty');
        const list = document.getElementById('myCasesList');
        const sub = document.getElementById('myCasesSubText');

        loading.style.display = 'flex';
        empty.style.display = 'none';
        list.innerHTML = '';

        let cases = [];
        const localCases = getLocalCachedCases();

        if (window.GHOST_MEMBER && window.GHOST_MEMBER.loggedIn) {
            sub.textContent = `Showing reports submitted under ${window.GHOST_MEMBER.email}`;
            try {
                const res = await fetch(`${API_BASE}/member/cases`, {
                    credentials: 'same-origin'
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.cases) {
                        cases = data.cases;
                    }
                }
            } catch (e) {
                console.warn('Could not sync remote member cases:', e);
            }
        } else {
            sub.textContent = 'Showing reports saved on this device. Sign in to your account to view all your reports.';
        }

        // Preserve locally cached access_key when available and merge unseen local cases
        const localKeyMap = {};
        localCases.forEach(lc => {
            if (lc && lc.case_code && lc.access_key) {
                localKeyMap[lc.case_code] = lc.access_key;
            }
        });
        cases = cases.map(c => Object.assign({}, c, {
            access_key: c.access_key || localKeyMap[c.case_code] || ''
        }));

        const seen = new Set(cases.map(c => c.case_code));
        localCases.forEach(lc => {
            if (!seen.has(lc.case_code)) {
                cases.push(lc);
                seen.add(lc.case_code);
            }
        });

        loading.style.display = 'none';

        if (!cases.length) {
            empty.style.display = 'block';
            updateMyCasesBadge(0);
            return;
        }

        updateMyCasesBadge(cases.length);

        list.innerHTML = cases.map(c => {
            const statusKey = (c.status || 'SUBMITTED').toLowerCase();
            const statusLabel = (c.status === 'IN_REVIEW' ? 'In Review' : (c.status || 'SUBMITTED')).replace('_', ' ');
            const dateStr = (c.created_at || '').substring(0, 10);
            const accessKey = c.access_key || '';
            const code = c.case_code;

            return `
        <div class="gm-case-card-item">
            <div class="gm-case-card-top">
                <div class="gm-case-card-meta">
                    <span class="gm-case-code-pill">#${escapeHtml(code)}</span>
                    <span class="gm-status-pill status-${escapeHtml(statusKey)}">${escapeHtml(statusLabel)}</span>
                    <span class="gm-category-badge">${escapeHtml(c.category || 'Report')}</span>
                </div>
                <span class="gm-case-card-date">${escapeHtml(dateStr)}</span>
            </div>
            <h4 class="gm-case-card-subject">${escapeHtml(c.subject || 'No Subject')}</h4>
            <p class="gm-case-card-desc">${escapeHtml(c.description || '')}</p>
            <div class="gm-case-card-actions">
                <button type="button" class="gm-open-case-btn" data-case-code="${escapeHtml(code)}" data-access-key="${escapeHtml(accessKey)}">
                    <span>Open Report &amp; Messages →</span>
                </button>
            </div>
        </div>
    `;
        }).join('');
    };

    function updateMyCasesBadge(count) {
        const badge = document.getElementById('myCasesBadge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    }

    function updateMyCasesCount() {
        const local = getLocalCachedCases();
        if (local && local.length > 0) {
            updateMyCasesBadge(local.length);
        }
    }

    function canUseMemberSession() {
        return Boolean(window.GHOST_MEMBER && window.GHOST_MEMBER.loggedIn);
    }

    window.openCaseFromList = function (code, key) {
        document.getElementById('lookupCaseCode').value = code || '';
        document.getElementById('lookupAccessKey').value = key || '';
        switchSupportTab('track');
        loadCase(code || '', key || '');
    };

    // Case Lookup & Dashboard
    window.loadCaseFromInputs = function () {
        const code = document.getElementById('lookupCaseCode').value.trim();
        const key = document.getElementById('lookupAccessKey').value.trim();
        if (!code || (!key && !canUseMemberSession())) {
            alert('Please enter both your Report Code and Passcode.');
            return;
        }
        loadCase(code, key);
    };

    window.openActiveCaseDashboard = function () {
        if (!currentCaseCode || (!currentAccessKey && !canUseMemberSession())) return;
        document.getElementById('lookupCaseCode').value = currentCaseCode;
        document.getElementById('lookupAccessKey').value = currentAccessKey || '';
        switchSupportTab('track');
        loadCase(currentCaseCode, currentAccessKey || '');
    };

    async function loadCase(code, key) {
        currentCaseCode = code;
        currentAccessKey = key || '';
        localStorage.setItem('gm_active_case_code', code);
        if (currentAccessKey) {
            localStorage.setItem('gm_active_access_key', currentAccessKey);
        }

        try {
            const reqHeaders = {};
            if (currentAccessKey) {
                reqHeaders['X-Case-Key'] = currentAccessKey;
            }
            const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(code)}`, {
                credentials: 'same-origin',
                headers: reqHeaders
            });
            if (!res.ok) {
                if (res.status === 403) throw new Error('Invalid Passcode.');
                if (res.status === 404) throw new Error('Report not found.');
                throw new Error(`Server returned HTTP ${res.status}`);
            }

            const data = await res.json();
            renderCaseDashboard(data);

            // Start live chat polling
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(pollCaseUpdates, 5000);

        } catch (err) {
            alert(`Could not load report: ${err.message}`);
        }
    }

    function renderCaseDashboard(c) {
        document.getElementById('gmLookupCard').style.display = 'none';
        const dash = document.getElementById('gmCaseDashboard');
        dash.style.display = 'block';

        document.getElementById('dashCaseCode').textContent = `#${c.case_code}`;
        document.getElementById('dashPriority').textContent = c.priority || 'STANDARD';
        document.getElementById('dashSubject').textContent = c.subject;
        document.getElementById('dashDescription').textContent = c.description;

        if (c.created_at) {
            document.getElementById('dashCreatedAt').textContent = `Submitted: ${c.created_at.replace('T', ' ').substring(0, 16)} UTC`;
        }

        // Stepper
        const s1 = document.getElementById('stepSubmitted');
        const s2 = document.getElementById('stepReview');
        const s3 = document.getElementById('stepResolution');
        const l1 = document.getElementById('line1');
        const l2 = document.getElementById('line2');

        s1.className = 'gm-stepper-step active';
        s2.className = 'gm-stepper-step';
        s3.className = 'gm-stepper-step';
        l1.className = 'gm-stepper-line';
        l2.className = 'gm-stepper-line';

        const status = (c.status || 'SUBMITTED').toUpperCase();
        if (status === 'IN_REVIEW') {
            s2.classList.add('active');
            l1.classList.add('active');
        } else if (status === 'CLOSED' || status === 'REJECTED') {
            s2.classList.add('active');
            s3.classList.add('active');
            l1.classList.add('active');
            l2.classList.add('active');
            document.getElementById('stepResolutionLabel').textContent = status === 'CLOSED' ? 'Resolved' : 'Closed';
        }

        // Outcome Note
        const resCard = document.getElementById('dashResolutionCard');
        if (c.resolution_note) {
            resCard.style.display = 'block';
            document.getElementById('dashResolutionNote').textContent = c.resolution_note;
            document.getElementById('dashResolutionTitle').textContent = status === 'REJECTED' ? 'Closing Note' : 'Resolution Note';
            document.getElementById('dashResolutionIcon').textContent = status === 'REJECTED' ? '⚪' : '✅';
        } else {
            resCard.style.display = 'none';
        }

        // Attached Files
        const evSection = document.getElementById('dashEvidenceSection');
        const evList = document.getElementById('dashEvidenceList');
        if (c.files && c.files.length) {
            evSection.style.display = 'block';
            document.getElementById('dashEvidenceCount').textContent = `${c.files.length} file(s)`;
            evList.innerHTML = c.files.map(f => {
                const sizeKb = (f.size / 1024).toFixed(1);
                return `
            <div class="gm-evidence-card gm-evidence-vaulted">
                <div class="gm-evidence-vault-icon">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                    </svg>
                </div>
                <div class="gm-evidence-info">
                    <div class="gm-evidence-name">${escapeHtml(f.name)}</div>
                    <div class="gm-evidence-meta">${sizeKb} KB</div>
                </div>
            </div>
        `;
            }).join('');
        } else {
            evSection.style.display = 'none';
        }

        // Render Chat Messages
        renderMessages(c.messages || []);
    }

    let currentCaseMessages = [];

    function renderMessages(msgs) {
        currentCaseMessages = msgs || [];
        const container = document.getElementById('gmChatMessages');
        if (!currentCaseMessages.length) {
            container.innerHTML = '<div class="gm-chat-empty">💬 No messages yet. Send an update or question below.</div>';
            return;
        }

        container.innerHTML = currentCaseMessages.map(m => {
            const isReporter = m.sender_type === 'reporter';
            const cls = isReporter ? 'gm-msg-reporter' : 'gm-msg-admin';
            const sender = isReporter ? 'You' : (m.sender_name || 'Team');
            let timeStr = '';
            if (m.created_at) {
                try {
                    const d = new Date(m.created_at);
                    timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                } catch (e) {
                    timeStr = (m.created_at || '').substring(11, 16);
                }
            }

            return `
        <div class="gm-msg-bubble ${cls}">
            <div class="gm-msg-text">${escapeHtml(m.message || m.message_text || '')}</div>
            <div class="gm-msg-meta">${escapeHtml(sender)}${timeStr ? ' · ' + timeStr : ''}</div>
        </div>
    `;
        }).join('');

        container.scrollTop = container.scrollHeight;
    }

    window.exportChatTranscript = function () {
        if (!currentCaseCode) {
            alert('No active report loaded.');
            return;
        }
        const subj = document.getElementById('dashSubject') ? document.getElementById('dashSubject').textContent.trim() : '';
        const status = document.getElementById('dashStatusBadge') ? document.getElementById('dashStatusBadge').textContent.trim() : '';

        let transcript = `====================================================\n`;
        transcript += `REPORT MESSAGES\n`;
        transcript += `Report Code: #${currentCaseCode}\n`;
        transcript += `Subject:     ${subj}\n`;
        transcript += `Status:      ${status}\n`;
        transcript += `Exported:    ${new Date().toUTCString()}\n`;
        transcript += `====================================================\n\n`;

        if (!currentCaseMessages || !currentCaseMessages.length) {
            transcript += `(No messages yet)\n`;
        } else {
            currentCaseMessages.forEach(m => {
                const isReporter = m.sender_type === 'reporter';
                const sender = isReporter ? 'You' : (m.sender_name || 'Team');
                const time = m.created_at || '';
                transcript += `[${time}] ${sender}:\n`;
                transcript += `${m.message || m.message_text || ''}\n\n`;
            });
        }

        const blob = new Blob([transcript], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report-${currentCaseCode}-messages.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    async function pollCaseUpdates() {
        if (!currentCaseCode || (!currentAccessKey && !canUseMemberSession())) return;
        try {
            const reqHeaders = {};
            if (currentAccessKey) {
                reqHeaders['X-Case-Key'] = currentAccessKey;
            }
            const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(currentCaseCode)}`, {
                credentials: 'same-origin',
                headers: reqHeaders
            });
            if (res.ok) {
                const data = await res.json();
                renderCaseDashboard(data);
            }
        } catch (e) { }
    }

    // Chat Attachment State
    let selectedChatFile = null;

    window.handleChatFileSelect = function (input) {
        if (input.files && input.files[0]) {
            if (input.files[0].size > MAX_PER_FILE_BYTES) {
                alert('Attachment exceeds the 20 MB per-file limit.');
                input.value = '';
                return;
            }
            selectedChatFile = input.files[0];
            const sizeStr = (selectedChatFile.size / 1024).toFixed(1) + ' KB';
            document.getElementById('chatAttachName').textContent = `${selectedChatFile.name} (${sizeStr})`;
            document.getElementById('chatAttachPreview').style.display = 'flex';
        }
    };

    window.removeChatAttachment = function () {
        selectedChatFile = null;
        const input = document.getElementById('chatFileInput');
        if (input) input.value = '';
        document.getElementById('chatAttachPreview').style.display = 'none';
    };

    window.handleSendMessage = async function (e) {
        e.preventDefault();
        const input = document.getElementById('chatMessageInput');
        const text = input.value.trim();
        if ((!text && !selectedChatFile) || !currentCaseCode || (!currentAccessKey && !canUseMemberSession())) return;

        const btn = document.getElementById('btnSendChat');
        btn.disabled = true;
        try {
            let res;
            const authHeaders = {};
            if (currentAccessKey) {
                authHeaders['X-Case-Key'] = currentAccessKey;
            }
            if (selectedChatFile) {
                const formData = new FormData();
                if (currentAccessKey) formData.append('key', currentAccessKey);
                if (text) formData.append('message', text);
                formData.append('attachment', selectedChatFile);

                res = await fetch(`${API_BASE}/cases/${encodeURIComponent(currentCaseCode)}/messages`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: authHeaders,
                    body: formData
                });
            } else {
                authHeaders['Content-Type'] = 'application/json';
                res = await fetch(`${API_BASE}/cases/${encodeURIComponent(currentCaseCode)}/messages`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: authHeaders,
                    body: JSON.stringify({
                        key: currentAccessKey || '',
                        message: text
                    })
                });
            }

            if (!res.ok) {
                let errText = `HTTP ${res.status}`;
                try {
                    const err = await res.json();
                    if (err && err.error) errText = err.error;
                } catch (_) { }
                throw new Error(errText);
            }

            input.value = '';
            removeChatAttachment();
            pollCaseUpdates();
        } catch (err) {
            alert('Failed to send message: ' + err.message);
        } finally {
            btn.disabled = false;
        }
    };

    function buildShareCaseUrl(code, key) {
        const basePath = (window.location.pathname || '/report/').replace(/\/?$/, '/');
        return `${window.location.origin}${basePath}#case=${encodeURIComponent(code)}&key=${encodeURIComponent(key)}`;
    }

    window.copyCaseDirectLink = function () {
        if (!currentCaseCode || !currentAccessKey) {
            alert('A share link requires the passcode saved when the report was submitted.');
            return;
        }
        const url = buildShareCaseUrl(currentCaseCode, currentAccessKey);
        navigator.clipboard.writeText(url).then(() => {
            const txt = document.getElementById('copyCaseLinkText');
            if (txt) txt.textContent = '✓ Link Copied!';
            setTimeout(() => {
                if (txt) txt.textContent = 'Copy Share Link';
            }, 2500);
        }).catch(() => {
            prompt('Copy share link:', url);
        });
    };

    window.copyDirectCaseLink = function () {
        if (!currentCaseCode || !currentAccessKey) {
            alert('A share link requires the passcode saved when the report was submitted.');
            return;
        }
        const url = buildShareCaseUrl(currentCaseCode, currentAccessKey);
        navigator.clipboard.writeText(url).then(() => {
            const btn = document.getElementById('btnSuccessCopyLink');
            if (btn) btn.innerHTML = '<span>✓ Link Copied!</span>';
            setTimeout(() => {
                if (btn) btn.innerHTML = '<span>🔗 Copy Share Link</span>';
            }, 2500);
        }).catch(() => {
            prompt('Copy share link:', url);
        });
    };

    function parseDirectCaseParams() {
        const rawHash = (window.location.hash || '').replace(/^#/, '');
        if (rawHash && rawHash.includes('case=')) {
            const hashParams = new URLSearchParams(rawHash);
            const hCase = hashParams.get('case');
            const hKey = hashParams.get('key');
            if (hCase && hKey) {
                return { caseCode: hCase, accessKey: hKey };
            }
        }
        const urlParams = new URLSearchParams(window.location.search);
        const qCase = urlParams.get('case');
        const qKey = urlParams.get('key');
        if (qCase && qKey) {
            // Scrub secret access key out of query string into client-only URL hash fragment
            try {
                const cleanHash = `#case=${encodeURIComponent(qCase)}&key=${encodeURIComponent(qKey)}`;
                window.history.replaceState(null, '', window.location.pathname + cleanHash);
            } catch (_) { }
            return { caseCode: qCase, accessKey: qKey };
        }
        return null;
    }

    function checkSavedCase() {
        const direct = parseDirectCaseParams();
        if (direct) {
            document.getElementById('lookupCaseCode').value = direct.caseCode;
            document.getElementById('lookupAccessKey').value = direct.accessKey;
            loadCase(direct.caseCode, direct.accessKey);
            return;
        }

        const savedCode = localStorage.getItem('gm_active_case_code');
        const savedKey = localStorage.getItem('gm_active_access_key');
        if (savedCode && (savedKey || canUseMemberSession())) {
            document.getElementById('lookupCaseCode').value = savedCode;
            document.getElementById('lookupAccessKey').value = savedKey || '';
            const badge = document.getElementById('activeCaseBadge');
            if (badge) badge.style.display = 'inline-block';
        }
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    window.copyText = function (elementId) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const text = el.textContent.trim();
        navigator.clipboard.writeText(text).then(() => {
            alert(`Copied: ${text}`);
        }).catch(() => {
            prompt('Copy text:', text);
        });
    };

    // Bind all DOM event listeners cleanly (zero inline event attributes or script URIs)
    function bindPortalEventListeners() {
        document.querySelectorAll('[data-support-tab]').forEach(btn => {
            btn.addEventListener('click', function () {
                switchSupportTab(this.getAttribute('data-support-tab'));
            });
        });

        const supportForm = document.getElementById('gmSupportForm');
        if (supportForm) supportForm.addEventListener('submit', handleCaseSubmit);

        const chatForm = document.getElementById('gmChatComposer');
        if (chatForm) chatForm.addEventListener('submit', handleSendMessage);

        const dropzone = document.getElementById('gmDropzone');
        const evidenceInput = document.getElementById('evidenceFileInput');
        if (dropzone) {
            dropzone.addEventListener('click', function (e) {
                if (evidenceInput && e.target !== evidenceInput) {
                    evidenceInput.click();
                }
            });
            dropzone.addEventListener('dragover', handleDragOver);
            dropzone.addEventListener('dragleave', handleDragLeave);
            dropzone.addEventListener('drop', handleFileDrop);
        }
        if (evidenceInput) evidenceInput.addEventListener('change', handleFileSelect);

        const anonToggle = document.getElementById('anonToggle');
        if (anonToggle) {
            anonToggle.addEventListener('change', function () {
                if (this.getAttribute('data-anon-mode') === 'member') {
                    toggleMemberAnon(this.checked);
                } else {
                    toggleAnonFields(this.checked);
                }
            });
        }

        const btnRefreshCaptcha = document.getElementById('btnRefreshCaptcha');
        if (btnRefreshCaptcha) btnRefreshCaptcha.addEventListener('click', refreshCaptcha);

        const captchaVisual = document.getElementById('gmCaptchaVisual');
        if (captchaVisual) {
            captchaVisual.addEventListener('click', function (e) {
                const retryBtn = e.target.closest('[data-action="refresh-captcha"]');
                if (retryBtn) refreshCaptcha();
            });
        }

        document.querySelectorAll('[data-copy-target]').forEach(btn => {
            btn.addEventListener('click', function () {
                copyText(this.getAttribute('data-copy-target'));
            });
        });

        const btnSuccessCopyLink = document.getElementById('btnSuccessCopyLink');
        if (btnSuccessCopyLink) btnSuccessCopyLink.addEventListener('click', copyDirectCaseLink);

        const btnOpenActiveCase = document.getElementById('btnOpenActiveCase');
        if (btnOpenActiveCase) btnOpenActiveCase.addEventListener('click', openActiveCaseDashboard);

        const btnRefreshCases = document.getElementById('btnRefreshCases');
        if (btnRefreshCases) btnRefreshCases.addEventListener('click', fetchMemberCases);

        const btnLookupCase = document.getElementById('btnLookupCase');
        if (btnLookupCase) btnLookupCase.addEventListener('click', loadCaseFromInputs);

        const btnCopyCaseLink = document.getElementById('btnCopyCaseLink');
        if (btnCopyCaseLink) btnCopyCaseLink.addEventListener('click', copyCaseDirectLink);

        const btnExportTranscript = document.getElementById('btnExportTranscript');
        if (btnExportTranscript) btnExportTranscript.addEventListener('click', exportChatTranscript);

        const btnRemoveChatAttach = document.getElementById('btnRemoveChatAttach');
        if (btnRemoveChatAttach) btnRemoveChatAttach.addEventListener('click', removeChatAttachment);

        const chatFileInput = document.getElementById('chatFileInput');
        if (chatFileInput) {
            chatFileInput.addEventListener('change', function () {
                handleChatFileSelect(this);
            });
        }

        const gmFileList = document.getElementById('gmFileList');
        if (gmFileList) {
            gmFileList.addEventListener('click', function (e) {
                const rmBtn = e.target.closest('[data-remove-file]');
                if (rmBtn) {
                    const idx = parseInt(rmBtn.getAttribute('data-remove-file'), 10);
                    if (!Number.isNaN(idx)) removeFile(idx);
                }
            });
        }

        const myCasesList = document.getElementById('myCasesList');
        if (myCasesList) {
            myCasesList.addEventListener('click', function (e) {
                const openBtn = e.target.closest('.gm-open-case-btn');
                if (openBtn) {
                    openCaseFromList(
                        openBtn.getAttribute('data-case-code') || '',
                        openBtn.getAttribute('data-access-key') || ''
                    );
                }
            });
        }
    }

    bindPortalEventListeners();

    // Initialize state
    if (window.GHOST_MEMBER && window.GHOST_MEMBER.loggedIn) {
        updateMyCasesCount();
        fetchMemberCases();
    }

    const initialDirect = parseDirectCaseParams();
    if (initialDirect || window.location.hash === '#track') {
        switchSupportTab('track');
    } else if (window.location.hash === '#mycases' && window.GHOST_MEMBER && window.GHOST_MEMBER.loggedIn) {
        switchSupportTab('mycases');
    } else {
        switchSupportTab('submit');
    }
})();
