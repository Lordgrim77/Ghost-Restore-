/**
 * Ghost Alto Theme - Team Page Engine (Ultra-Premium Redesign)
 * Cyber Intelligence & Forensic Operative Cards
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', initTeamPage);

    function initTeamPage() {
        const grid = document.getElementById('gm-team-grid');
        if (!grid) return;

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

        // 2. Load team configuration
        loadTeamConfig(function(configMembers) {
            renderTeamGrid(grid, configMembers, ghostStaff);
        });
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

        // Step A: Process configured team members
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

                // Prefer explicit member.name if custom-configured, otherwise fall back to staff.name
                const resolvedName = member.name || (staff && staff.name ? staff.name : 'Operative');
                const resolvedBio = member.bio || (staff && staff.bio ? staff.bio : 'Lead Investigator & Security Researcher. Focused on digital forensics, OSINT, and threat actor infrastructure analysis.');
                const resolvedAvatar = (staff && staff.avatar) ? staff.avatar : (member.avatar || '');
                const resolvedLocation = member.location || (staff && staff.location ? staff.location : 'Global Operations');
                const resolvedWebsite = member.website || (staff && staff.website ? staff.website : '');
                const resolvedTwitter = member.twitter || (staff && staff.twitter ? staff.twitter : '');
                const resolvedFacebook = member.facebook || (staff && staff.facebook ? staff.facebook : '');
                const resolvedUrl = (staff && staff.url) ? staff.url : (member.url || (slug ? `/author/${slug}/` : ''));
                const postCount = (staff && typeof staff.postCount === 'number') ? staff.postCount : (typeof member.postCount === 'number' ? member.postCount : 0);

                mergedList.push({
                    order: typeof member.order === 'number' ? member.order : (idx + 1),
                    name: resolvedName,
                    slug: slug || (staff ? staff.slug : 'operative'),
                    title: member.title || (staff && staff.location ? staff.location : 'Lead Investigator & Developer'),
                    badge: member.badge || 'VERIFIED OPERATIVE',
                    specialty: member.specialty || 'Digital Forensics & OSINT',
                    location: resolvedLocation,
                    bio: resolvedBio,
                    avatar: resolvedAvatar,
                    website: resolvedWebsite,
                    twitter: resolvedTwitter,
                    facebook: resolvedFacebook,
                    telegram: member.telegram || 'https://t.me/StopAbuseTeam',
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
                badge: 'FIELD RESEARCHER',
                specialty: 'Intelligence Analysis',
                location: staff.location || 'Distributed',
                bio: staff.bio || 'Investigator & Research Contributor protecting digital frontiers.',
                avatar: staff.avatar,
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

        // Step D: Render ultra-premium cyberpunk profile cards
        const cardsHtml = mergedList.map((member, index) => {
            const authorUrl = member.url;
            const opCode = `OP-${String(member.order || (index + 1)).padStart(2, '0')}`;

            // Social links
            let linksHtml = '';
            if (member.telegram) {
                linksHtml += `
                    <a href="${escapeHtml(member.telegram)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="Telegram" title="Encrypted Telegram Channel">
                        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>
                    </a>`;
            }
            if (member.twitter) {
                linksHtml += `
                    <a href="${escapeHtml(member.twitter)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="Twitter / X" title="X / Twitter">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 3a10.9 10.9 0 0 1-3.14 1.53 4.48 4.48 0 0 0-7.86 3v1A10.66 10.66 0 0 1 3 4s-4 9 5 13a11.64 11.64 0 0 1-7 2c9 5 20 0 20-11.5a4.5 4.5 0 0 0-.08-.83A7.72 7.72 0 0 0 23 3z"/></svg>
                    </a>`;
            }
            if (member.github) {
                linksHtml += `
                    <a href="${escapeHtml(member.github)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="GitHub" title="GitHub">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
                    </a>`;
            }
            if (member.website) {
                linksHtml += `
                    <a href="${escapeHtml(member.website)}" target="_blank" rel="noopener noreferrer" class="gm-team-social-btn" aria-label="Website" title="Personal Portal">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    </a>`;
            }

            // Avatar element
            let avatarMarkup = '';
            if (member.avatar) {
                avatarMarkup = `<img class="gm-team-avatar" src="${escapeHtml(member.avatar)}" alt="${escapeHtml(member.name)}" loading="lazy">`;
            } else {
                const cleanWords = member.name.replace(/[^a-zA-Z0-9 ]/g, ' ').trim().split(/\s+/);
                const first = cleanWords[0] ? cleanWords[0][0] : 'O';
                const last = cleanWords.length > 1 ? cleanWords[cleanWords.length - 1][0] : (cleanWords[0].length > 1 ? cleanWords[0][1] : 'P');
                const finalInitials = (first + last).toUpperCase();
                avatarMarkup = `<div class="gm-team-avatar gm-team-avatar-initials">${finalInitials}</div>`;
            }

            // Primary action button
            let ctaHtml = '';
            if (authorUrl) {
                ctaHtml = `
                    <a href="${escapeHtml(authorUrl)}" class="gm-team-cta-btn">
                        <span>View Dossier &amp; Dispatches</span>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </a>`;
            } else if (member.telegram || member.website) {
                ctaHtml = `
                    <a href="${escapeHtml(member.telegram || member.website)}" target="_blank" rel="noopener noreferrer" class="gm-team-cta-btn">
                        <span>Contact Operative</span>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </a>`;
            }

            return `
                <article class="gm-team-card">
                    <!-- Ambient Glow Behind Avatar -->
                    <div class="gm-team-card-glow"></div>

                    <!-- Top Status Bar & Tactical Metas -->
                    <div class="gm-team-card-topbar">
                        <div class="gm-team-badge-wrap">
                            <span class="gm-team-status-dot"></span>
                            <span class="gm-team-security-badge">${escapeHtml(member.badge)}</span>
                        </div>
                        <span class="gm-team-code-tag">${escapeHtml(opCode)} // SYS_ACTIVE</span>
                    </div>

                    <!-- Hero Identity Row -->
                    <div class="gm-team-hero-row">
                        <div class="gm-team-avatar-wrap">
                            <div class="gm-team-avatar-ring">
                                ${authorUrl ? `<a href="${escapeHtml(authorUrl)}">${avatarMarkup}</a>` : avatarMarkup}
                            </div>
                            <span class="gm-team-verified-check" title="Cryptographically Verified Identity">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                            </span>
                        </div>
                        <div class="gm-team-identity-info">
                            <h2 class="gm-team-name">
                                ${authorUrl ? `<a href="${escapeHtml(authorUrl)}">${escapeHtml(member.name)}</a>` : `<span>${escapeHtml(member.name)}</span>`}
                            </h2>
                            <span class="gm-team-role">${escapeHtml(member.title)}</span>
                            ${member.location ? `
                                <div class="gm-team-location">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                                    <span>${escapeHtml(member.location)}</span>
                                </div>` : ''}
                        </div>
                    </div>

                    <!-- Tactical Chips (Specialty & Dispatches Count) -->
                    <div class="gm-team-chips-row">
                        <span class="gm-team-chip">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                            <span>${escapeHtml(member.specialty)}</span>
                        </span>
                        ${member.postCount > 0 ? `
                        <span class="gm-team-chip gm-team-chip-accent">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                            <span>${member.postCount} Dispatches Published</span>
                        </span>` : ''}
                    </div>

                    <!-- Bio / Mission Briefing -->
                    <p class="gm-team-bio">${escapeHtml(member.bio)}</p>

                    <!-- Bottom Action Row -->
                    <div class="gm-team-card-footer">
                        <div class="gm-team-social-links">
                            ${linksHtml}
                        </div>
                        ${ctaHtml}
                    </div>
                </article>
            `;
        }).join('');

        container.innerHTML = cardsHtml;
        container.setAttribute('data-team-loaded', 'true');
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
