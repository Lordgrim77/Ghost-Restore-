/**
 * Cyber Liquid Glass Controller (powered by liquidGL)
 * PedoHunters Custom Alto Theme Design System
 * 
 * True Optical Refraction & Crystal Liquid Glass:
 *  1. Sticky Navigation Bar: High-contrast refraction visor (#gh-head)
 *  2. Post & Feed Cards: Tactile 3D Tilting Glass Slabs (.gm-post-card)
 *  3. Team & Staff Identity: Cyber Glass Badges (.gm-team-card)
 *  4. Author Profile: Panoramic Refraction Shield (.author-profile / .gm-author-header)
 *  5. Newsletter Subscription: Crystalline Energy Ribbon (.gm-newsletter-card)
 *  6. RSS Feed: Crystalline Modal Shield (.gm-rss-modal-card)
 *  7. Dynamic Theme Tint & Snapshot Synchronization across all active renderers
 *  8. Background Telemetry Canvas Refraction Registration (#gm-cyber-hex-canvas)
 */
(function() {
  'use strict';
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  var activeLenses = [];
  var isInitialized = false;

  // Ultra-subtle, transparent optical tints for True Refraction (frost = 0)
  function getTints(isLight) {
    if (isLight) {
      return {
        nav: "rgba(255, 255, 255, 0.18)",
        card: "rgba(255, 255, 255, 0.14)",
        team: "rgba(255, 255, 255, 0.15)",
        author: "rgba(255, 255, 255, 0.15)",
        modal: "rgba(255, 255, 255, 0.85)",
        newsletter: "rgba(255, 255, 255, 0.14)"
      };
    } else {
      return {
        nav: "rgba(10, 16, 28, 0.22)",
        card: "rgba(10, 16, 28, 0.18)",
        team: "rgba(8, 12, 22, 0.20)",
        author: "rgba(6, 10, 20, 0.20)",
        modal: "rgba(3, 7, 18, 0.70)",
        newsletter: "rgba(6, 10, 20, 0.18)"
      };
    }
  }

  function getCurrentThemeIsLight() {
    return document.documentElement.classList.contains('light-mode') ||
           document.documentElement.getAttribute('data-theme') === 'light' ||
           document.body.classList.contains('light-mode');
  }

  function syncAllTints() {
    var isLight = getCurrentThemeIsLight();
    var tints = getTints(isLight);
    for (var i = 0; i < activeLenses.length; i++) {
      var item = activeLenses[i];
      if (item && item.lens && typeof item.lens.setTint === 'function') {
        var tintVal = tints[item.category] || (isLight ? "rgba(255, 255, 255, 0.15)" : "rgba(10, 16, 28, 0.20)");
        item.lens.setTint(tintVal);
      }
    }
    // Re-capture snapshot across all active liquidGL renderers
    if (window.__liquidGLRenderers__) {
      window.__liquidGLRenderers__.forEach(function(r) {
        if (r && typeof r.captureSnapshot === 'function') {
          r.captureSnapshot();
        }
      });
    } else if (window.__liquidGLRenderer__ && typeof window.__liquidGLRenderer__.captureSnapshot === 'function') {
      window.__liquidGLRenderer__.captureSnapshot();
    }
  }

  function registerLens(category, lensOrLenses) {
    if (!lensOrLenses) return;
    if (Array.isArray(lensOrLenses)) {
      for (var j = 0; j < lensOrLenses.length; j++) {
        activeLenses.push({ category: category, lens: lensOrLenses[j] });
      }
    } else {
      activeLenses.push({ category: category, lens: lensOrLenses });
    }
  }

  function initCyberLiquid() {
    if (isInitialized) return;
    if (typeof window.liquidGL !== 'function') {
      console.warn("liquidGL library not detected; skipping liquid glass initialization.");
      return;
    }
    isInitialized = true;

    // Signal to CSS that liquidGL is active so native CSS blur & opaque backgrounds are replaced
    document.documentElement.classList.add('liquidgl-active');

    var isLight = getCurrentThemeIsLight();
    var tints = getTints(isLight);

    // 0. Ensure preloader, modals and search overlays are ignored by snapshot
    var splash = document.getElementById('gm-cyber-splash');
    if (splash) splash.setAttribute('data-liquid-ignore', 'true');
    var sodo = document.getElementById('sodo-search-root');
    if (sodo) sodo.setAttribute('data-liquid-ignore', 'true');

    // 1. Sticky Navigation Bar: True Refraction Prism Visor (frost = 0, magnify = 1.08)
    var navEl = document.querySelector('#gh-head');
    if (navEl) {
      try {
        var navLens = window.liquidGL({
          target: '#gh-head',
          snapshot: 'body',
          zIndex: 100,
          resolution: 2.0,
          refraction: 0.065,
          bevelDepth: 0.08,
          bevelWidth: 0.25,
          frost: 0,
          magnify: 1.08,
          aberration: 0.035,
          specular: true,
          shadow: true,
          tint: tints.nav
        });
        registerLens('nav', navLens);
      } catch(e) {
        console.warn("liquidGL Nav Init:", e);
      }
    }

    // 2. Feed Post Cards: Tactile 3D Refracting Glass Slabs (frost = 0, refraction = 0.075, magnify = 1.12)
    var postCards = document.querySelectorAll('.gm-post-card');
    if (postCards && postCards.length > 0) {
      try {
        var cardLenses = window.liquidGL({
          target: '.gm-post-card',
          snapshot: 'body',
          zIndex: 2,
          resolution: 2.0,
          refraction: 0.075,
          bevelDepth: 0.09,
          bevelWidth: 0.30,
          frost: 0,
          magnify: 1.12,
          aberration: 0.040,
          specular: true,
          shadow: true,
          tilt: true,
          tiltFactor: 6,
          tiltEase: 350,
          tint: tints.card
        });
        registerLens('card', cardLenses);
      } catch(e) {
        console.warn("liquidGL Cards Init:", e);
      }
    }

    // 3. Team Member Cards: Cyber ID Badges (frost = 0, refraction = 0.075, magnify = 1.12)
    var teamCards = document.querySelectorAll('.gm-team-card');
    if (teamCards && teamCards.length > 0) {
      try {
        var teamLenses = window.liquidGL({
          target: '.gm-team-card',
          snapshot: 'body',
          zIndex: 2,
          resolution: 2.0,
          refraction: 0.075,
          bevelDepth: 0.09,
          bevelWidth: 0.30,
          frost: 0,
          magnify: 1.12,
          aberration: 0.040,
          specular: true,
          shadow: true,
          tilt: true,
          tiltFactor: 5,
          tiltEase: 300,
          tint: tints.team
        });
        registerLens('team', teamLenses);
      } catch(e) {
        console.warn("liquidGL Team Init:", e);
      }
    }

    // 4. Author Showcase Banner: Panoramic Glass Shield (frost = 0, refraction = 0.060, magnify = 1.08)
    var authorHeader = document.querySelector('.gm-author-header, .author-profile');
    if (authorHeader) {
      try {
        var authorLens = window.liquidGL({
          target: authorHeader.classList.contains('gm-author-header') ? '.gm-author-header' : '.author-profile',
          snapshot: 'body',
          zIndex: 2,
          resolution: 2.0,
          refraction: 0.060,
          bevelDepth: 0.07,
          bevelWidth: 0.24,
          frost: 0,
          magnify: 1.08,
          aberration: 0.030,
          specular: true,
          shadow: true,
          tint: tints.author
        });
        registerLens('author', authorLens);
      } catch(e) {
        console.warn("liquidGL Author Init:", e);
      }
    }

    // 5. Newsletter Subscription Card: Crystalline Energy Ribbon (frost = 0, refraction = 0.065, magnify = 1.10)
    var newsletterCard = document.querySelector('.gm-newsletter-card');
    if (newsletterCard) {
      try {
        var newsLens = window.liquidGL({
          target: '.gm-newsletter-card',
          snapshot: 'body',
          zIndex: 2,
          resolution: 2.0,
          refraction: 0.065,
          bevelDepth: 0.08,
          bevelWidth: 0.26,
          frost: 0,
          magnify: 1.10,
          aberration: 0.035,
          specular: true,
          shadow: true,
          tint: tints.newsletter
        });
        registerLens('newsletter', newsLens);
      } catch(e) {
        console.warn("liquidGL Newsletter Init:", e);
      }
    }

    // 6. RSS Feed Modal Card
    var rssModal = document.querySelector('.gm-rss-modal-card');
    if (rssModal) {
      try {
        var modalLens = window.liquidGL({
          target: '.gm-rss-modal-card',
          snapshot: 'body',
          zIndex: 1000,
          resolution: 2.0,
          refraction: 0.080,
          bevelDepth: 0.12,
          bevelWidth: 0.24,
          frost: 0,
          magnify: 1.10,
          aberration: 0.050,
          specular: true,
          reveal: "fade",
          tint: tints.modal
        });
        registerLens('modal', modalLens);
      } catch(e) {
        console.warn("liquidGL Modal Init:", e);
      }
    }

    // 7. Register Dynamic Background Telemetry Canvas
    var hexCanvas = document.getElementById('gm-cyber-hex-canvas');
    if (hexCanvas && typeof window.liquidGL.registerDynamic === 'function') {
      window.liquidGL.registerDynamic(hexCanvas);
    }

    // 8. Sync with smooth scrolling
    if (typeof window.liquidGL.syncWith === 'function') {
      window.liquidGL.syncWith();
    }

    // 9. Observer for theme changes to dynamically sync tint & refresh snapshot
    var themeTimer = null;
    var observer = new MutationObserver(function(mutations) {
      for (var m = 0; m < mutations.length; m++) {
        if (mutations[m].attributeName === 'class' || mutations[m].attributeName === 'data-theme') {
          clearTimeout(themeTimer);
          themeTimer = setTimeout(syncAllTints, 80);
          break;
        }
      }
    });
    observer.observe(document.documentElement, { attributes: true });

    document.querySelectorAll('.gm-theme-toggle').forEach(function(btn) {
      btn.addEventListener('click', function() {
        clearTimeout(themeTimer);
        themeTimer = setTimeout(syncAllTints, 80);
      });
    });
  }

  // Delay initial snapshot until preloader splash is hidden
  function startWhenReady() {
    var splash = document.getElementById('gm-cyber-splash');
    if (splash && getComputedStyle(splash).display !== 'none' && getComputedStyle(splash).opacity !== '0') {
      var checkInterval = setInterval(function() {
        if (!splash || getComputedStyle(splash).display === 'none' || getComputedStyle(splash).opacity === '0') {
          clearInterval(checkInterval);
          setTimeout(initCyberLiquid, 150);
        }
      }, 100);
      setTimeout(function() {
        clearInterval(checkInterval);
        initCyberLiquid();
      }, 1500);
    } else {
      setTimeout(initCyberLiquid, 100);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startWhenReady);
  } else {
    startWhenReady();
  }
})();
