/**
 * Professional Cybernetic Site Preloader Controller
 * Runs on every page load and article load with dynamic titles and fast smooth transitions.
 */
(function() {
  'use strict';
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  var splash = document.getElementById('gm-cyber-splash');
  var isDismissed = false;
  var hasStarted = false;

  function getSiteTitle() {
    var metaSite = document.querySelector('meta[property="og:site_name"]');
    if (metaSite && metaSite.content) return metaSite.content.trim();
    var brand = document.querySelector('.gh-head-logo, .gm-splash-fallback-title');
    if (brand && brand.textContent) return brand.textContent.trim();
    return document.title ? document.title.split(' - ')[0].trim() : 'Site';
  }

  function getPageLabel() {
    var labelEl = document.getElementById('gm-splash-label-text');
    if (labelEl && labelEl.textContent.trim()) {
      return labelEl.textContent.trim();
    }
    var title = document.title ? document.title.trim() : '';
    if (location.pathname === '/' || location.pathname === '') {
      return 'Loading ' + getSiteTitle();
    }
    var h1 = document.querySelector('h1.article-title, h1.post-full-title, h1.gh-article-title, h1');
    if (h1 && h1.textContent.trim()) {
      return 'Loading ' + h1.textContent.trim();
    }
    if (title) {
      return 'Loading ' + title.split(' - ')[0].trim();
    }
    return 'Loading ' + getSiteTitle();
  }

  function updateLabel(text) {
    var labelEl = document.getElementById('gm-splash-label-text') || document.querySelector('.gm-splash-label');
    if (labelEl && text) {
      labelEl.textContent = text;
    }
  }

  function dismissSplash() {
    if (isDismissed) return;
    isDismissed = true;
    splash = splash || document.getElementById('gm-cyber-splash');
    if (!splash) return;

    var bar = splash.querySelector('.gm-splash-progress-bar');
    if (bar) bar.style.width = '100%';

    setTimeout(function() {
      if (splash) {
        splash.classList.add('gm-splash-hidden');
      }
    }, 120);

    setTimeout(function() {
      if (splash) {
        splash.style.display = 'none';
      }
    }, 380);
  }

  function startFastPreloader() {
    if (hasStarted) return;
    hasStarted = true;
    splash = splash || document.getElementById('gm-cyber-splash');
    if (!splash) return;

    var bar = splash.querySelector('.gm-splash-progress-bar');
    updateLabel(getPageLabel());

    var progress = 12;
    if (bar) bar.style.width = '12%';

    var timer = setInterval(function() {
      if (isDismissed) {
        clearInterval(timer);
        return;
      }
      if (document.readyState === 'complete') {
        progress = 100;
        if (bar) bar.style.width = '100%';
        clearInterval(timer);
        dismissSplash();
        return;
      }
      if (document.readyState === 'interactive') {
        progress = Math.min(progress + 18, 92);
      } else {
        progress = Math.min(progress + 10, 78);
      }
      if (bar) bar.style.width = progress + '%';
    }, 30);

    if (document.readyState === 'complete') {
      dismissSplash();
    } else {
      window.addEventListener('load', dismissSplash, { once: true });
      document.addEventListener('DOMContentLoaded', function() {
        setTimeout(dismissSplash, 160);
      }, { once: true });
    }

    // Maximum failsafe dismiss after 950ms so user is never stuck
    setTimeout(dismissSplash, 950);
  }

  window.addEventListener('pageshow', function(e) {
    if (e.persisted) {
      if (splash) {
        splash.classList.add('gm-splash-hidden');
        splash.style.display = 'none';
      }
      isDismissed = true;
    }
  });

  if (splash) {
    splash.addEventListener('click', dismissSplash);
  }
  window.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') dismissSplash();
  });

  // Intercept internal link clicks for seamless pre-navigation display
  document.addEventListener('click', function(e) {
    var link = e.target && e.target.closest('a[href]');
    if (!link) return;
    var href = link.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
    if (link.target === '_blank' || link.hasAttribute('download') || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;

    var linkUrl;
    try {
      linkUrl = new URL(link.href, location.origin);
    } catch(err) {
      return;
    }
    if (linkUrl.origin !== location.origin) return;
    if (linkUrl.pathname === location.pathname && linkUrl.search === location.search && linkUrl.hash) return;

    var targetTitle = '';
    var postCard = link.closest('.gm-post-card, article');
    if (postCard) {
      var cardTitle = postCard.querySelector('.gm-post-card-title, .post-card-title, h2, h3');
      if (cardTitle && cardTitle.textContent.trim()) {
        targetTitle = cardTitle.textContent.trim();
      }
    }
    if (!targetTitle) {
      targetTitle = link.getAttribute('data-title') || link.title || link.textContent.trim();
    }
    if (!targetTitle || linkUrl.pathname === '/' || linkUrl.pathname === '') {
      targetTitle = getSiteTitle();
    }

    splash = splash || document.getElementById('gm-cyber-splash');
    if (splash) {
      isDismissed = false;
      splash.style.display = 'flex';
      splash.classList.remove('gm-splash-hidden');
      updateLabel('Loading ' + targetTitle);
      var bar = splash.querySelector('.gm-splash-progress-bar');
      if (bar) {
        bar.style.width = '0%';
        setTimeout(function() {
          if (bar) bar.style.width = '65%';
        }, 15);
      }
    }
  }, true);

  startFastPreloader();
})();
