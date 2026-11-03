/**
 * Ghost Alto Theme - Executive Operatives Directory Engine (Obsidian Telemetry)
 * Synchronizes with Google Stitch UI layout specifications:
 * - Live UTC Telemetry clock
 * - Automatic import of bio, avatar, location, and social links from Ghost Staff profiles
 * - Configurable manual sequence ordering, code badges, operational domains, and PGP fingerprints
 * - Responsive 3-col / 2-col / 1-col tactical grid with instant department filtering
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', initTeamPage);

    function initTeamPage() {
        const grid = document.getElementById('gm-team-grid');
        if (!grid) return;

        startLiveClock();

        // 1. Scrape all Ghost Staff profiles rendered in SSR fallback
        const ghostStaff = {};
        const ssrCards = grid.querySelectorAll('.gm-team-card-ssr');
        ssrCards.forEach(card => {
            const rawSlug = card.getAttribute('data-slug') || '';
            const slug = rawSlug.toLowerCase().trim();
            const name = (card.getAttribute('data-name') || '').trim();
            const postCount = parseInt(card.getAttribute('data-posts') || '0', 10);
            const authorUrl = card.getAttribute('data-url') || (slug ? `/author/${slug}/` : '');

            const avatarEl = card.querySelector('[data-field="avatar"]');
            const locationEl = card.querySelector('[data-field="location"]');
            const bioEl = card.querySelector('[data-field="bio"]');
            const websiteEl = card.querySelector('[data-field="website"]');
            const twitterEl = card.querySelector('[data-field="twitter"]');
            const facebookEl = card.querySelector('[data-field="facebook"]');

            const staffObj = {
                slug: slug,
                rawSlug: rawSlug,
                name: name,
                avatar: avatarEl ? avatarEl.textContent.trim() : '',
                location: locationEl ? locationEl.textContent.trim() : '',
                bio: bioEl ? bioEl.textContent.trim() : '',
                website: websiteEl ? websiteEl.textContent.trim() : '',
                twitter: twitterEl ? twitterEl.textContent.trim() : '',
                facebook: facebookEl ? facebookEl.textContent.trim() : '',
                url: authorUrl,
                postCount: postCount,
                matched: false
            };

            if (slug) ghostStaff[slug] = staffObj;
            if (name) ghostStaff[name.toLowerCase()] = staffObj;
        });

        // 2. Load manual operative configuration (order, custom titles, specialties, PGP keys)
        loadTeamConfig(function(configMembers) {
            renderTeamGrid(grid, configMembers, ghostStaff);
            setupFilters();
        });
    }

    function startLiveClock() {
        const clockEl = document.getElementById('gm-live-utc-clock');
        if (!clockEl) return;

        function updateClock() {
            const now = new Date();
            const year = now.getUTCFullYear();
            const month = String(now.getUTCMonth() + 1).padStart(2, '0');
            const day = String(now.getUTCDate()).padStart(2, '0');
            const hours = String(now.getUTCHours()).padStart(2, '0');
            const minutes = String(now.getUTCMinutes()).padStart(2, '0');
            const seconds = String(now.getUTCSeconds()).padStart(2, '0');
            clockEl.textContent = `UTC: ${year}-${month}-${day} // ${hours}:${minutes}:${seconds}`;
        }
        updateClock();
        setInterval(updateClock, 1000);
    }

    function loadTeamConfig(callback) {
        const jsonUrl = '/assets/data/team.json?v=' + Date.now();
        fetch(jsonUrl)
            .then(res => {
                if (!res.ok) throw new Error('Status ' + res.status);
                return res.json();
            })
            .then(data => {
                if (Array.isArray(data) && data.length > 0) {
                    callback(data);
                } else {
                    fallbackToInline();
                }
            })
            .catch(() => {
                fallbackToInline();
            });

        function fallbackToInline() {
            try {
                const inlineTag = document.getElementById('gm-team-default-data');
                if (inlineTag && inlineTag.textContent) {
                    const parsed = JSON.parse(inlineTag.textContent);
                    if (Array.isArray(parsed) && parsed.length > 0) {
                        callback(parsed);
                        return;
                    }
                }
            } catch (err) {
                console.warn('[GM Team] Failed to parse inline team data:', err);
            }
            callback([]);
        }
    }

    function renderTeamGrid(container, configMembers, ghostStaff) {
        const mergedList = [];
        const processedSlugs = new Set();

        // Step A: Process configured operatives
        if (Array.isArray(configMembers)) {
            configMembers.forEach((member, idx) => {
                const slug = (member.slug || '').toLowerCase().trim();
                const altSlug = (member.alt_slug || '').toLowerCase().trim();
                const nameKey = (member.name || '').toLowerCase().trim();

                const staff = ghostStaff[slug] || ghostStaff[altSlug] || ghostStaff[nameKey] || null;

                if (staff) {
                    staff.matched = true;
                    if (staff.slug) processedSlugs.add(staff.slug);
                }
                if (slug) processedSlugs.add(slug);
                if (altSlug) processedSlugs.add(altSlug);

                // Auto-import details from Ghost staff if available
                const resolvedName = (staff && staff.name) ? staff.name : (member.name || 'Operative');
                const resolvedBio = (staff && staff.bio) ? staff.bio : (member.bio || 'Intelligence and cyber forensics specialist conducting non-attributable investigations.');
                const resolvedAvatar = (staff && staff.avatar) ? staff.avatar : (member.avatar || '');
                const resolvedLocation = (staff && staff.location) ? staff.location : (member.location || 'Global Operations');
                const resolvedWebsite = (staff && staff.website) ? staff.website : (member.website || '');
                const resolvedTwitter = (staff && staff.twitter) ? staff.twitter : (member.twitter || '');
                const resolvedFacebook = (staff && staff.facebook) ? staff.facebook : (member.facebook || '');
                const resolvedUrl = (staff && staff.url) ? staff.url : (member.url || (slug ? `/author/${slug}/` : ''));
                const postCount = (staff && typeof staff.postCount === 'number') ? staff.postCount : (typeof member.postCount === 'number' ? member.postCount : 0);

                mergedList.push({
                    order: typeof member.order === 'number' ? member.order : (idx + 1),
                    name: resolvedName,
                    slug: slug || (staff ? staff.slug : ''),
                    title: member.title || (staff && staff.location ? staff.location : 'Staff Investigator'),
                    code: member.code || `OP-${700 + idx * 37} // LEVEL-4`,
                    badge: member.badge || 'VERIFIED',
                    division: member.division || 'Special Operations',
                    department: member.department || 'Operations',
                    location: resolvedLocation,
                    bio: resolvedBio,
                    specialties: Array.isArray(member.specialties) ? member.specialties : ['Cyber Intelligence', 'Digital Forensics', 'Incident Response'],
                    pgp: member.pgp || '9B44...F12E',
                    avatar: resolvedAvatar,
                    status: member.status === 'standby' ? 'standby' : 'active',
                    website: resolvedWebsite,
                    twitter: resolvedTwitter,
                    facebook: resolvedFacebook,
                    telegram: member.telegram || '',
                    github: member.github || '',
                    email: member.email || '',
                    url: resolvedUrl,
                    postCount: postCount
                });
            });
        }

        // Step B: Automatically append any unlisted Ghost Staff authors
        const seenStaff = new Set();
        Object.keys(ghostStaff).forEach(k => {
            const staff = ghostStaff[k];
            if (!staff || staff.matched || seenStaff.has(staff.slug)) return;
            seenStaff.add(staff.slug);

            const opIdx = mergedList.length + 1;
            mergedList.push({
                order: 100 + opIdx,
                name: staff.name,
                slug: staff.slug,
                title: staff.location || 'Staff Contributor',
                code: `OP-${800 + opIdx * 19} // LEVEL-4`,
                badge: 'VERIFIED',
                division: 'Field Operations',
                department: 'Operations',
                location: staff.location || 'Global Operations',
                bio: staff.bio || 'Investigator & Research Contributor protecting digital frontiers.',
                specialties: ['Digital Forensics', 'OSINT Intelligence', 'Adversary Tracking'],
                pgp: '8A20...B41C',
                avatar: staff.avatar,
                status: 'active',
                website: staff.website,
                twitter: staff.twitter,
                facebook: staff.facebook,
                telegram: '',
                github: '',
                email: '',
                url: staff.url,
                postCount: staff.postCount
            });
        });

        // Step C: Sort strictly by manual order
        mergedList.sort((a, b) => a.order - b.order);

        // Step D: Update dynamic HUD and filter counts
        const activeCountEl = document.getElementById('gm-hud-active-count');
        if (activeCountEl) activeCountEl.textContent = mergedList.length;

        const totalFilterCountEl = document.getElementById('gm-filter-total-count');
        if (totalFilterCountEl) totalFilterCountEl.textContent = `(${mergedList.length})`;

        // Step E: Render Stitch cards HTML
        const cardsHtml = mergedList.map(member => {
            const authorUrl = member.url;
            const statusClass = member.status === 'standby' ? 'standby' : 'active';
            const statusTitle = statusClass === 'active' ? 'Live Secure Node' : 'Standby Unit';

            // Social & comms links
            let linksHtml = '';
            if (member.telegram) {
                linksHtml += `
                    <a href="${escapeHtml(member.telegram)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="Telegram" title="Telegram">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>
                    </a>`;
            }
            if (member.twitter) {
                linksHtml += `
                    <a href="${escapeHtml(member.twitter)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="Twitter / X" title="Twitter / X">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 3a10.9 10.9 0 0 1-3.14 1.53 4.48 4.48 0 0 0-7.86 3v1A10.66 10.66 0 0 1 3 4s-4 9 5 13a11.64 11.64 0 0 1-7 2c9 5 20 0 20-11.5a4.5 4.5 0 0 0-.08-.83A7.72 7.72 0 0 0 23 3z"/></svg>
                    </a>`;
            }
            if (member.github) {
                linksHtml += `
                    <a href="${escapeHtml(member.github)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="GitHub" title="GitHub">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
                    </a>`;
            }
            if (member.website) {
                linksHtml += `
                    <a href="${escapeHtml(member.website)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="Website" title="Website">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    </a>`;
            }
            if (member.email) {
                linksHtml += `
                    <a href="mailto:${escapeHtml(member.email)}" class="gm-team-social-btn" aria-label="Encrypted Email" title="Encrypted Email">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                    </a>`;
            }

            // Specialties pills
            const specialtiesHtml = member.specialties.map(spec => {
                return `<span class="gm-domain-pill">${escapeHtml(spec)}</span>`;
            }).join('');

            // Avatar element
            let avatarMarkup = '';
            if (member.avatar) {
                avatarMarkup = `<img class="gm-team-card-avatar" src="${escapeHtml(member.avatar)}" alt="${escapeHtml(member.name)}" loading="lazy">`;
            } else {
                const cleanWords = member.name.replace(/[^a-zA-Z0-9 ]/g, ' ').trim().split(/\s+/);
                const first = cleanWords[0] ? cleanWords[0][0] : 'O';
                const last = cleanWords.length > 1 ? cleanWords[cleanWords.length - 1][0] : (cleanWords[0].length > 1 ? cleanWords[0][1] : 'P');
                const finalInitials = (first + last).toUpperCase();
                avatarMarkup = `<div class="gm-team-card-avatar gm-team-avatar-initials">${finalInitials}</div>`;
            }

            // Primary action button
            let ctaHtml = '';
            if (authorUrl) {
                ctaHtml = `
                    <a href="${escapeHtml(authorUrl)}" class="gm-team-card-cta">
                        <span>VIEW DOSSIER &amp; INTEL BRIEFINGS</span>
                        ${member.postCount > 0 ? `<span class="gm-team-post-count-badge">(${member.postCount})</span>` : ''}
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </a>`;
            } else if (member.telegram || member.website) {
                ctaHtml = `
                    <a href="${escapeHtml(member.telegram || member.website)}" target="_blank" rel="noopener noreferrer" class="gm-team-card-cta">
                        <span>CONTACT OPERATIVE ENCLAVE</span>
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                    </a>`;
            } else {
                ctaHtml = `
                    <span class="gm-team-card-cta gm-team-cta-disabled">
                        <span>CLASSIFIED DOSSIER</span>
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    </span>`;
            }

            return `
                <article class="gm-team-card hud-brackets specular-rim" data-department="${escapeHtml(member.department)}" data-order="${member.order}">
                    <div class="gm-team-card-top-wrap">
                        <!-- Header Banner & Operative Identification -->
                        <div class="gm-team-card-header">
                            <div class="gm-team-avatar-container">
                                ${avatarMarkup}
                                <span class="gm-team-status-ping ${statusClass}" title="${statusTitle}"></span>
                            </div>
                            <div class="gm-team-id-group">
                                <div class="gm-team-code-row">
                                    <span class="gm-team-code-tag">${escapeHtml(member.code)}</span>
                                    <span class="gm-team-verified-pill">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                                        <span>${escapeHtml(member.badge)}</span>
                                    </span>
                                </div>
                                <h3 class="gm-team-card-name">
                                    ${authorUrl ? `<a href="${escapeHtml(authorUrl)}">${escapeHtml(member.name)}</a>` : `<span>${escapeHtml(member.name)}</span>`}
                                </h3>
                                <p class="gm-team-card-title">${escapeHtml(member.title)}</p>
                            </div>
                        </div>

                        <!-- Tactical Telemetry Meta -->
                        <div class="gm-team-card-meta-bar">
                            <div class="gm-team-meta-unit">
                                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
                                <span>${escapeHtml(member.division)}</span>
                            </div>
                            ${member.location ? `
                            <div class="gm-team-meta-zone">
                                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                                <span>${escapeHtml(member.location)}</span>
                            </div>` : ''}
                        </div>

                        <!-- Dossier Bio & Domains -->
                        <div class="gm-team-card-body">
                            <p class="gm-team-dossier-bio">${escapeHtml(member.bio)}</p>

                            <div class="gm-team-domains-wrap">
                                <div class="gm-team-domains-label">OPERATIONAL DOMAINS</div>
                                <div class="gm-team-domains-pills">
                                    ${specialtiesHtml}
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Footer / Contact & Verification Key Row -->
                    <div class="gm-team-card-footer">
                        <div class="gm-team-footer-verification">
                            ${member.pgp ? `
                            <span class="gm-team-pgp-tag" title="PGP Key Fingerprint">
                                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/></svg>
                                <span>${escapeHtml(member.pgp)}</span>
                            </span>` : ''}
                            <div class="gm-team-social-icons">
                                ${linksHtml}
                            </div>
                        </div>
                        ${ctaHtml}
                    </div>
                </article>
            `;
        }).join('');

        container.innerHTML = cardsHtml;
        container.setAttribute('data-team-loaded', 'true');
    }

    function setupFilters() {
        const filterBar = document.getElementById('gm-team-filters');
        const grid = document.getElementById('gm-team-grid');
        if (!filterBar || !grid) return;

        const buttons = filterBar.querySelectorAll('.gm-team-filter-btn');
        buttons.forEach(btn => {
            btn.addEventListener('click', function() {
                buttons.forEach(b => b.classList.remove('is-active'));
                this.classList.add('is-active');

                const filter = (this.getAttribute('data-filter') || 'all').toLowerCase();
                const cards = grid.querySelectorAll('.gm-team-card');

                cards.forEach(card => {
                    const dept = (card.getAttribute('data-department') || '').toLowerCase();
                    let match = false;

                    if (filter === 'all') {
                        match = true;
                    } else if (filter === 'leadership' && dept.includes('leadership')) {
                        match = true;
                    } else if (filter === 'digital forensics' && (dept.includes('forensics') || dept.includes('digital'))) {
                        match = true;
                    } else if (filter === 'intelligence' && (dept.includes('intel') || dept.includes('osint'))) {
                        match = true;
                    } else if (filter === 'adversary tracking' && (dept.includes('adversary') || dept.includes('tracking') || dept.includes('crimes'))) {
                        match = true;
                    } else if (filter === 'advisory & legal' && (dept.includes('legal') || dept.includes('advisory'))) {
                        match = true;
                    } else if (dept.includes(filter)) {
                        match = true;
                    }

                    if (match) {
                        card.classList.remove('is-hidden');
                    } else {
                        card.classList.add('is-hidden');
                    }
                });
            });
        });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
})();
