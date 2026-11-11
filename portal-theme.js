/**
 * Ghost Portal Glassmorphism Styler (v8 - Zero FOUC, Universal Button Architecture)
 * - Intercepts portal iframes immediately and sets data-styled="true" to eliminate FOUC
 * - Universal button redesign: unified .gh-portal-btn-list, .gh-portal-list-action, primary, secondary & footers
 * - Eradicates all pink from toggle switches (.input-toggle-component) with Monochrome Pure White #ffffff
 * - Overrides Ghost's internal --brandcolor variable to #ffffff in Dark Mode (#000000 in Light Mode)
 * - Complete responsive layouts for "Email preferences", "Your account", and "Sign in"
 */
(function() {
  function seedGhostAccent() {
    try {
      const ghostScript = document.querySelector('script[data-ghost]');
      if (ghostScript && ghostScript.dataset.accentColor !== '#ffffff') {
        ghostScript.setAttribute('data-accent-color', '#ffffff');
        ghostScript.dataset.accentColor = '#ffffff';
      }
    } catch(e) {}
  }
  seedGhostAccent();

  const darkCSS = `
    /* Force Obsidian/Cyan palette across the entire iframe */
    :root, html, body {
      --brandcolor: #ffffff !important;
      --ghost-accent-color: #ffffff !important;
      accent-color: #ffffff !important;
      box-sizing: border-box !important;
    }

    html, body {
      background: transparent !important;
      margin: 0 !important;
      padding: 0 !important;
      width: 100% !important;
      height: 100% !important;
      overflow-x: hidden !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif !important;
      -webkit-font-smoothing: antialiased !important;
    }

    /* Fullscreen Backdrop Blur & Refined Contrast */
    .gh-portal-popup-background {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      background: radial-gradient(circle at 50% 40%, rgba(10, 15, 24, 0.72) 0%, rgba(3, 5, 8, 0.88) 100%) !important;
      backdrop-filter: blur(28px) saturate(190%) !important;
      -webkit-backdrop-filter: blur(28px) saturate(190%) !important;
      z-index: 10 !important;
      animation: gmPortalFade 0.22s ease forwards !important;
    }

    /* Flexbox Modal Wrapper */
    .gh-portal-popup-wrapper {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      display: flex !important;
      align-items: flex-start !important;
      justify-content: center !important;
      background: transparent !important;
      padding: 40px 16px 48px 16px !important;
      box-sizing: border-box !important;
      z-index: 20 !important;
      overflow-y: auto !important;
      -webkit-overflow-scrolling: touch !important;
    }

    /* Monochromatic Obsidian Glass Portal Container (Refined Contrast, Shadows & Blur) */
    .gh-portal-popup-container {
      margin: auto !important;
      width: 100% !important;
      max-width: 480px !important;
      min-height: auto !important;
      position: relative !important;
      box-sizing: border-box !important;
      padding: 38px 34px !important;
      border-radius: 24px !important;
      background: linear-gradient(180deg, rgba(22, 27, 38, 0.88) 0%, rgba(12, 16, 24, 0.94) 100%) !important;
      backdrop-filter: blur(40px) saturate(200%) !important;
      -webkit-backdrop-filter: blur(40px) saturate(200%) !important;
      border: 1px solid rgba(255, 255, 255, 0.16) !important;
      box-shadow: 0 32px 72px -12px rgba(0, 0, 0, 0.95), 
                  0 12px 30px rgba(0, 0, 0, 0.75), 
                  0 0 0 1px rgba(255, 255, 255, 0.08), 
                  inset 0 1px 0 rgba(255, 255, 255, 0.22),
                  inset 0 -1px 0 rgba(0, 0, 0, 0.4) !important;
      color: #f8fafc !important;
      animation: gmPortalFadeIn 0.28s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    }

    .gh-portal-popup-container.account,
    .gh-portal-popup-container:has(.gh-portal-email-preferences-header),
    .gh-portal-popup-container:has(.gh-portal-account-header),
    .gh-portal-popup-container:has(.gh-portal-list-toggle-wrapper) {
      max-width: 520px !important;
      padding: 38px 34px !important;
    }

    /* Refined Input Fields for Dark Mode */
    .gh-portal-input {
      background: rgba(255, 255, 255, 0.05) !important;
      border: 1px solid rgba(255, 255, 255, 0.16) !important;
      border-radius: 12px !important;
      color: #ffffff !important;
      font-size: 15px !important;
      height: 48px !important;
      padding: 0 16px !important;
      outline: none !important;
      transition: all 0.2s ease !important;
      box-sizing: border-box !important;
      width: 100% !important;
      box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3) !important;
    }

    .gh-portal-input:focus {
      border-color: #ffffff !important;
      background: rgba(255, 255, 255, 0.09) !important;
      box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.22), inset 0 2px 4px rgba(0, 0, 0, 0.3) !important;
    }

    .gh-portal-input-label {
      color: #cbd5e1 !important;
      font-size: 11.5px !important;
      font-weight: 700 !important;
      text-transform: uppercase !important;
      letter-spacing: 0.07em !important;
      margin-bottom: 7px !important;
    }

    .gh-portal-closeicon-container {
      cursor: pointer !important;
      top: 18px !important;
      right: 18px !important;
      position: absolute !important;
      width: 34px !important;
      height: 34px !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      z-index: 50 !important;
      border-radius: 50% !important;
      background: rgba(255, 255, 255, 0.08) !important;
      border: 1px solid rgba(255, 255, 255, 0.16) !important;
      transition: all 0.2s ease !important;
    }

    .gh-portal-closeicon-container:hover {
      background: rgba(255, 255, 255, 0.18) !important;
      border-color: rgba(255, 255, 255, 0.3) !important;
      transform: scale(1.05) !important;
    }

    .gh-portal-closeicon {
      color: #cbd5e1 !important;
      transition: color 0.2s ease !important;
    }

    .gh-portal-closeicon:hover {
      color: #ffffff !important;
    }


    @keyframes gmPortalFade {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    @keyframes gmPortalFadeIn {
      from { opacity: 0; transform: scale(0.96) translateY(8px); }
      to { opacity: 1; transform: scale(1) translateY(0); }
    }

    /* ========================================================================
       TYPOGRAPHY & HEADERS
       ======================================================================== */
    .gh-portal-main-title,
    .gh-portal-detail-header h3,
    .gh-portal-account-header h2 {
      color: #ffffff !important;
      font-weight: 800 !important;
      font-size: 22px !important;
      letter-spacing: -0.03em !important;
      margin: 0 !important;
      text-align: center !important;
    }

    .gh-portal-email-preferences-header,
    .gh-portal-detail-header {
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      position: relative !important;
      width: 100% !important;
      margin-bottom: 24px !important;
      min-height: 36px !important;
    }

    .gh-portal-detail-header .gh-portal-btn-back {
      position: absolute !important;
      left: 0 !important;
      top: 50% !important;
      transform: translateY(-50%) !important;
      width: 36px !important;
      height: 36px !important;
      border-radius: 50% !important;
      background: rgba(255, 255, 255, 0.06) !important;
      border: 1px solid rgba(255, 255, 255, 0.12) !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      cursor: pointer !important;
      padding: 0 !important;
      color: #94a3b8 !important;
      transition: all 0.2s ease !important;
    }

    .gh-portal-detail-header .gh-portal-btn-back:hover {
      background: rgba(255, 255, 255, 0.12) !important;
      color: #ffffff !important;
      border-color: rgba(255, 255, 255, 0.4) !important;
    }

    .gh-portal-closeicon-container {
      cursor: pointer !important;
      top: 18px !important;
      right: 18px !important;
      position: absolute !important;
      width: 34px !important;
      height: 34px !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      z-index: 50 !important;
      border-radius: 50% !important;
      background: rgba(255, 255, 255, 0.05) !important;
      border: 1px solid rgba(255, 255, 255, 0.1) !important;
      transition: all 0.2s ease !important;
    }

    .gh-portal-closeicon-container:hover {
      background: rgba(255, 255, 255, 0.12) !important;
      border-color: rgba(255, 255, 255, 0.2) !important;
    }

    .gh-portal-closeicon {
      color: #94a3b8 !important;
      transition: color 0.2s ease !important;
    }

    .gh-portal-closeicon:hover {
      color: #ffffff !important;
    }

    /* ========================================================================
       UNIVERSAL BUTTON ARCHITECTURE (Zero Pink, Obsidian/Cyan Cohesion)
       ======================================================================== */
    /* 1. Primary Action Buttons (Sign In, Sign Up, Save, Submit, Continue) */
    .gh-portal-btn-primary,
    .gh-portal-btn-main,
    .gh-portal-btn-branded,
    button[type="submit"].gh-portal-btn,
    .gh-portal-btn[type="submit"],
    button.gh-portal-btn-main {
      background: #ffffff !important;
      background-color: #ffffff !important;
      color: #040609 !important;
      border-radius: 999px !important;
      font-weight: 700 !important;
      font-size: 15px !important;
      height: 48px !important;
      width: 100% !important;
      border: 1px solid #ffffff !important;
      box-shadow: 0 4px 14px rgba(255, 255, 255, 0.35) !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
      margin-top: 12px !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      letter-spacing: -0.01em !important;
    }

    .gh-portal-btn-primary:hover,
    .gh-portal-btn-main:hover,
    .gh-portal-btn-branded:hover,
    button[type="submit"].gh-portal-btn:hover,
    button.gh-portal-btn-main:hover {
      background: #f1f5f9 !important;
      background-color: #f1f5f9 !important;
      color: #040609 !important;
      border-color: #f1f5f9 !important;
      transform: translateY(-1px) !important;
      box-shadow: 0 6px 20px rgba(255, 255, 255, 0.5) !important;
    }

    /* Primary / Submit Button Disabled & Loading State (Dark Mode) */
    .gh-portal-btn-primary[disabled],
    .gh-portal-btn-main[disabled],
    .gh-portal-btn-branded[disabled],
    button[type="submit"].gh-portal-btn[disabled],
    .gh-portal-btn[type="submit"][disabled],
    button.gh-portal-btn-main[disabled],
    .gh-portal-btn[disabled] {
      background: #ffffff !important;
      background-color: #ffffff !important;
      border-color: #ffffff !important;
      opacity: 0.88 !important;
      cursor: not-allowed !important;
      position: relative !important;
    }

    /* Loading Spinner in Dark Mode -> on WHITE button, spinner is Solid Pitch Black */
    .gh-portal-loadingicon,
    .gh-portal-loadingicon.dark,
    svg#loader-1.gh-portal-loadingicon {
      position: absolute !important;
      left: 50% !important;
      top: 50% !important;
      transform: translate(-50%, -50%) !important;
      margin: 0 !important;
      margin-inline-start: 0 !important;
      height: 28px !important;
      width: 28px !important;
      display: block !important;
      z-index: 10 !important;
    }

    .gh-portal-loadingicon path,
    .gh-portal-loadingicon rect,
    .gh-portal-loadingicon.dark path,
    .gh-portal-loadingicon.dark rect,
    svg#loader-1.gh-portal-loadingicon path,
    svg#loader-1.gh-portal-loadingicon rect {
      fill: #040609 !important;
      stroke: none !important;
    }

    /* When submit/primary button is loading, hide text so it doesn't collide with spinner */
    button[disabled]:has(.gh-portal-loadingicon),
    button[disabled]:has(svg#loader-1) {
      color: transparent !important;
    }

    button:has(.gh-portal-loadingicon) > span:not(.gh-portal-loadingicon *),
    button:has(svg#loader-1) > span:not(svg#loader-1 *) {
      opacity: 0 !important;
      visibility: hidden !important;
    }

    /* 2. Secondary / Cancel Buttons */
    .gh-portal-btn-secondary,
    .gh-portal-btn-cancel,
    button.gh-portal-btn-secondary,
    button.gh-portal-btn-cancel {
      background: rgba(255, 255, 255, 0.08) !important;
      border: 1px solid rgba(255, 255, 255, 0.16) !important;
      color: #cbd5e1 !important;
      border-radius: 999px !important;
      font-size: 14px !important;
      font-weight: 600 !important;
      height: 46px !important;
      padding: 0 24px !important;
      cursor: pointer !important;
      transition: all 0.2s ease !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
    }

    .gh-portal-btn-secondary:hover,
    .gh-portal-btn-cancel:hover,
    button.gh-portal-btn-secondary:hover,
    button.gh-portal-btn-cancel:hover {
      background: rgba(255, 255, 255, 0.15) !important;
      color: #ffffff !important;
      border-color: rgba(255, 255, 255, 0.25) !important;
    }

    /* 3. Unified Row Action Buttons (Edit, Change, Continue in Lists) */
    .gh-portal-list-action,
    .gh-portal-btn-list,
    button.gh-portal-btn-list,
    button[data-test-button="change-plan"],
    span[data-test-button="edit-profile"],
    span[data-test-button="edit-newsletters"] {
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      padding: 6px 16px !important;
      border-radius: 999px !important;
      background: rgba(255, 255, 255, 0.1) !important;
      border: 1px solid rgba(255, 255, 255, 0.3) !important;
      color: #ffffff !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
      flex-shrink: 0 !important;
      line-height: 1.4 !important;
      height: auto !important;
      min-width: unset !important;
      text-decoration: none !important;
    }

    .gh-portal-list-action:hover,
    .gh-portal-btn-list:hover,
    button.gh-portal-btn-list:hover,
    button[data-test-button="change-plan"]:hover,
    span[data-test-button="edit-profile"]:hover,
    span[data-test-button="edit-newsletters"]:hover {
      background: #ffffff !important;
      color: #040609 !important;
      border-color: #ffffff !important;
      box-shadow: 0 0 14px rgba(255, 255, 255, 0.45) !important;
      transform: translateY(-1px) !important;
    }

    /* 4. Action Footer in Sub-Pages (Edit Profile / Save Changes) */
    .gh-portal-action-footer {
      display: flex !important;
      align-items: center !important;
      justify-content: flex-end !important;
      gap: 12px !important;
      margin-top: 28px !important;
      width: 100% !important;
      box-sizing: border-box !important;
    }

    .gh-portal-action-footer .gh-portal-btn {
      width: auto !important;
      min-width: 110px !important;
      height: 46px !important;
      padding: 0 24px !important;
      margin-top: 0 !important;
    }

    /* 5. Account Popup Footer ("Sign out" & "Contact support") */
    footer.gh-portal-account-footer {
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      margin-top: 24px !important;
      width: 100% !important;
      padding: 0 !important;
    }

    .gh-portal-account-footermenu,
    .gh-portal-account-footerright {
      display: flex !important;
      align-items: center !important;
      list-style: none !important;
      padding: 0 !important;
      margin: 0 !important;
    }

    .gh-portal-account-footermenu li {
      list-style: none !important;
      margin: 0 !important;
      padding: 0 !important;
    }

    .gh-portal-account-footer button.gh-portal-btn,
    button[data-test-button="footer-signout"] {
      background: rgba(255, 255, 255, 0.08) !important;
      border: 1px solid rgba(255, 255, 255, 0.16) !important;
      color: #cbd5e1 !important;
      border-radius: 999px !important;
      padding: 10px 20px !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      transition: all 0.2s ease !important;
      height: 40px !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
    }

    .gh-portal-account-footer button.gh-portal-btn:hover,
    button[data-test-button="footer-signout"]:hover {
      background: rgba(255, 255, 255, 0.16) !important;
      color: #ffffff !important;
      border-color: rgba(255, 255, 255, 0.25) !important;
    }

    a[data-test-link="footer-support"],
    .gh-portal-account-footerright a.gh-portal-btn {
      background: rgba(255, 255, 255, 0.12) !important;
      border: 1px solid rgba(255, 255, 255, 0.35) !important;
      color: #ffffff !important;
      border-radius: 999px !important;
      padding: 10px 20px !important;
      font-size: 13px !important;
      font-weight: 700 !important;
      text-decoration: none !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      cursor: pointer !important;
      transition: all 0.2s ease !important;
      height: 40px !important;
      box-sizing: border-box !important;
    }

    a[data-test-link="footer-support"]:hover,
    .gh-portal-account-footerright a.gh-portal-btn:hover {
      background: #ffffff !important;
      color: #040609 !important;
      border-color: #ffffff !important;
      box-shadow: 0 0 16px rgba(255, 255, 255, 0.45) !important;
      transform: translateY(-1px) !important;
    }

    /* ========================================================================
       TOGGLE SWITCHES (.input-toggle-component) - PURE Monochrome Pure White
       ======================================================================== */
    .gh-portal-for-switch {
      position: relative !important;
      display: inline-flex !important;
      align-items: center !important;
      flex-shrink: 0 !important;
      margin: 0 !important;
    }

    .gh-portal-for-switch .switch {
      position: relative !important;
      display: inline-block !important;
      width: 46px !important;
      height: 26px !important;
      margin: 0 !important;
      cursor: pointer !important;
    }

    .gh-portal-for-switch input[type="checkbox"] {
      position: absolute !important;
      opacity: 0 !important;
      width: 0 !important;
      height: 0 !important;
      pointer-events: none !important;
    }

    .gh-portal-for-switch .input-toggle-component,
    .input-toggle-component {
      position: absolute !important;
      inset: 0 !important;
      background: rgba(255, 255, 255, 0.16) !important;
      border: 1px solid rgba(255, 255, 255, 0.18) !important;
      border-radius: 999px !important;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
      cursor: pointer !important;
      width: 46px !important;
      height: 26px !important;
      box-sizing: border-box !important;
    }

    .gh-portal-for-switch .input-toggle-component:before,
    .input-toggle-component:before {
      position: absolute !important;
      content: "" !important;
      height: 18px !important;
      width: 18px !important;
      left: 3px !important;
      bottom: 3px !important;
      background: #ffffff !important;
      border-radius: 50% !important;
      transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
      box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4) !important;
    }

    .gh-portal-for-switch input:checked + .input-toggle-component,
    input[type="checkbox"]:checked + .input-toggle-component,
    .input-toggle-component.checked,
    [style*="rgb(240, 37, 116)"],
    [style*="#ff0077"],
    [style*="rgb(255, 0, 119)"] {
      background: #ffffff !important;
      background-color: #ffffff !important;
      border-color: #ffffff !important;
      box-shadow: 0 0 16px rgba(255, 255, 255, 0.5) !important;
    }

    .gh-portal-for-switch input:checked + .input-toggle-component:before,
    input[type="checkbox"]:checked + .input-toggle-component:before {
      transform: translateX(20px) !important;
      background: #ffffff !important;
    }

    /* ========================================================================
       LIST CARDS & CONTENT
       ======================================================================== */
    .gh-portal-list {
      display: flex !important;
      flex-direction: column !important;
      gap: 12px !important;
      width: 100% !important;
      background: transparent !important;
      border: none !important;
      padding: 0 !important;
      margin: 0 !important;
      box-shadow: none !important;
    }

    .gh-portal-section.flex {
      display: block !important;
      width: 100% !important;
      margin: 0 !important;
      padding: 0 !important;
    }

    .gh-portal-list-toggle-wrapper,
    .gh-portal-list-clickable,
    .gh-portal-list > section {
      display: flex !important;
      flex-direction: row !important;
      align-items: center !important;
      justify-content: space-between !important;
      background: rgba(255, 255, 255, 0.04) !important;
      border: 1px solid rgba(255, 255, 255, 0.09) !important;
      border-radius: 16px !important;
      padding: 18px 20px !important;
      margin: 0 !important;
      width: 100% !important;
      box-sizing: border-box !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
      cursor: pointer !important;
      text-align: left !important;
    }

    .gh-portal-list-toggle-wrapper:hover,
    .gh-portal-list-clickable:hover,
    .gh-portal-list > section:hover {
      background: rgba(255, 255, 255, 0.07) !important;
      border-color: rgba(255, 255, 255, 0.35) !important;
      transform: translateY(-1px) !important;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35) !important;
    }

    .gh-portal-list-detail {
      flex: 1 1 auto !important;
      min-width: 0 !important;
      padding: 0 !important;
      margin-right: 16px !important;
      text-align: left !important;
    }

    .gh-portal-list-detail h3 {
      color: #ffffff !important;
      font-size: 15px !important;
      font-weight: 700 !important;
      margin: 0 0 3px 0 !important;
      letter-spacing: -0.01em !important;
      line-height: 1.3 !important;
    }

    .gh-portal-list-detail p {
      color: #94a3b8 !important;
      font-size: 13px !important;
      margin: 0 !important;
      line-height: 1.45 !important;
      word-break: break-word !important;
    }

    .gh-portal-list-help {
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      padding: 14px 18px !important;
      background: rgba(255, 255, 255, 0.02) !important;
      border: 1px dashed rgba(255, 255, 255, 0.12) !important;
      border-radius: 14px !important;
      margin-top: 8px !important;
      box-sizing: border-box !important;
      width: 100% !important;
    }

    .gh-portal-list-help-label {
      color: #94a3b8 !important;
      font-size: 13px !important;
      font-weight: 500 !important;
    }

    .gh-portal-btn-text.gh-email-faq-page-button {
      color: #ffffff !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      background: none !important;
      border: none !important;
      cursor: pointer !important;
      display: inline-flex !important;
      align-items: center !important;
      gap: 4px !important;
      padding: 0 !important;
      transition: color 0.2s ease !important;
    }

    .gh-portal-btn-text.gh-email-faq-page-button:hover {
      color: #f1f5f9 !important;
      text-decoration: underline !important;
    }

    .gh-portal-btn-unsubscribe {
      margin-top: 24px !important;
      width: 100% !important;
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
    }

    .gh-portal-btn-unsubscribe button,
    .gh-portal-btn-unsubscribe .gh-portal-btn {
      width: 100% !important;
      height: 44px !important;
      border-radius: 999px !important;
      background: rgba(239, 68, 68, 0.08) !important;
      border: 1px solid rgba(239, 68, 68, 0.25) !important;
      color: #f87171 !important;
      font-size: 14px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      transition: all 0.2s ease !important;
    }

    .gh-portal-btn-unsubscribe button:hover,
    .gh-portal-btn-unsubscribe .gh-portal-btn:hover {
      background: rgba(239, 68, 68, 0.18) !important;
      border-color: #ef4444 !important;
      color: #ffffff !important;
      box-shadow: 0 0 16px rgba(239, 68, 68, 0.25) !important;
    }

    .gh-portal-btn-unsubscribe-note {
      color: #64748b !important;
      font-size: 12px !important;
      text-align: center !important;
      margin-top: 10px !important;
      line-height: 1.4 !important;
    }

    /* Account Header */
    .gh-portal-account-header {
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
      margin-bottom: 24px !important;
      text-align: center !important;
      width: 100% !important;
    }

    .gh-portal-account-header .gh-portal-avatar {
      width: 60px !important;
      height: 60px !important;
      border-radius: 50% !important;
      margin: 0 auto 12px auto !important;
      border: 2px solid rgba(255, 255, 255, 0.4) !important;
      box-shadow: 0 0 16px rgba(255, 255, 255, 0.2) !important;
      overflow: hidden !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      background: #090d16 !important;
    }

    .gh-portal-account-header .gh-portal-avatar svg {
      width: 36px !important;
      height: 36px !important;
      color: #ffffff !important;
    }

    /* Input Fields (Sign In / Sign Up / Edit Profile) */
    .gh-portal-input {
      background: rgba(255, 255, 255, 0.06) !important;
      border: 1px solid rgba(255, 255, 255, 0.14) !important;
      border-radius: 12px !important;
      color: #ffffff !important;
      font-size: 15px !important;
      height: 48px !important;
      padding: 0 16px !important;
      outline: none !important;
      transition: all 0.2s ease !important;
      box-sizing: border-box !important;
      width: 100% !important;
    }

    .gh-portal-input:focus {
      border-color: #ffffff !important;
      background: rgba(255, 255, 255, 0.1) !important;
      box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.2) !important;
    }

    .gh-portal-input-label {
      color: #94a3b8 !important;
      font-size: 11px !important;
      font-weight: 700 !important;
      text-transform: uppercase !important;
      letter-spacing: 0.06em !important;
      margin-bottom: 6px !important;
    }

    /* Sign in / Sign up Bottom Message & Switch Link (Dark Mode) */
    .gh-portal-signup-message {
      display: flex !important;
      flex-wrap: wrap !important;
      align-items: center !important;
      justify-content: center !important;
      gap: 6px !important;
      margin: 20px 0 0 0 !important;
      color: rgba(255, 255, 255, 0.7) !important;
      font-size: 14px !important;
    }

    .gh-portal-signup-message div,
    .gh-portal-signup-message p,
    .gh-portal-signup-message span {
      color: rgba(255, 255, 255, 0.7) !important;
      font-size: 14px !important;
    }

    .gh-portal-signup-message .gh-portal-btn-link,
    .gh-portal-btn.gh-portal-btn-link,
    button[data-test-button="signup-switch"],
    button[data-test-button="signin-switch"],
    button[data-testid="signin-switch"],
    button[data-test-button="gift-switch"],
    button.gh-portal-btn-link {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
      font-weight: 700 !important;
      font-size: 14px !important;
      text-decoration: underline !important;
      text-underline-offset: 3px !important;
      background: transparent !important;
      border: none !important;
      box-shadow: none !important;
      padding: 0 !important;
      margin: 0 !important;
      height: auto !important;
      width: auto !important;
      cursor: pointer !important;
      display: inline-flex !important;
      transition: opacity 0.2s ease !important;
    }

    .gh-portal-signup-message .gh-portal-btn-link span,
    button[data-test-button="signup-switch"] span,
    button[data-test-button="signin-switch"] span {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
      font-weight: 700 !important;
    }

    .gh-portal-signup-message .gh-portal-btn-link:hover,
    button[data-test-button="signup-switch"]:hover,
    button[data-test-button="signin-switch"]:hover {
      opacity: 0.8 !important;
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }

    /* Back Button in Site Title Header (Dark Mode) */
    .gh-portal-btn-site-title-back,
    button.gh-portal-btn-site-title-back {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
      background: transparent !important;
      border: none !important;
      font-size: 14px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      display: inline-flex !important;
      align-items: center !important;
      gap: 6px !important;
      padding: 0 !important;
      margin-bottom: 12px !important;
      transition: transform 0.2s ease, opacity 0.2s ease !important;
    }

    .gh-portal-btn-site-title-back:hover {
      opacity: 0.8 !important;
      transform: translateX(-2px) !important;
    }

    .gh-portal-btn-site-title-back span {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }

    .gh-portal-powered,
    #ghost-portal-root .gh-portal-powered {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
    }

    /* ========================================================================
       MOBILE VIEW FIXES (iPhone, Android < 640px)
       ======================================================================== */
    @media (max-width: 640px) {
      .gh-portal-popup-wrapper {
        padding: 16px 12px 36px 12px !important;
        align-items: flex-start !important;
      }

      .gh-portal-popup-container {
        padding: 24px 16px !important;
        border-radius: 20px !important;
        max-width: 100% !important;
        width: 100% !important;
        margin: 8px auto 24px auto !important;
      }

      .gh-portal-list-toggle-wrapper,
      .gh-portal-list-clickable,
      .gh-portal-list > section {
        padding: 14px 16px !important;
        border-radius: 14px !important;
      }

      .gh-portal-list-detail h3 {
        font-size: 14px !important;
      }

      .gh-portal-list-detail p {
        font-size: 12px !important;
      }

      footer.gh-portal-account-footer {
        flex-direction: column !important;
        gap: 10px !important;
        width: 100% !important;
      }

      .gh-portal-account-footermenu,
      .gh-portal-account-footerright {
        width: 100% !important;
      }

      .gh-portal-account-footermenu li {
        width: 100% !important;
      }

      .gh-portal-account-footer button.gh-portal-btn,
      button[data-test-button="footer-signout"],
      a[data-test-link="footer-support"],
      .gh-portal-account-footerright a.gh-portal-btn {
        width: 100% !important;
        height: 44px !important;
        justify-content: center !important;
        display: inline-flex !important;
        align-items: center !important;
      }

      .gh-portal-action-footer {
        flex-direction: column !important;
        gap: 10px !important;
        width: 100% !important;
      }

      .gh-portal-action-footer .gh-portal-btn {
        width: 100% !important;
        height: 44px !important;
      }
    }

    /* Forgot Password & Reset View (Dark Mode) */
    .gm-forgot-password-row {
      text-align: center !important;
      margin: 14px 0 6px 0 !important;
    }

    .gm-forgot-password-btn {
      background: none !important;
      border: none !important;
      padding: 4px 8px !important;
      font-family: inherit !important;
      font-size: 13px !important;
      font-weight: 500 !important;
      color: rgba(255, 255, 255, 0.72) !important;
      cursor: pointer !important;
      text-decoration: underline !important;
      text-underline-offset: 3px !important;
      transition: color 0.15s ease !important;
      outline: none !important;
    }

    .gm-forgot-password-btn:hover {
      color: #ffffff !important;
    }

    .gm-portal-reset-view {
      animation: gmPortalFadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    }

    .gm-portal-reset-desc {
      font-family: inherit !important;
      font-size: 14px !important;
      line-height: 1.6 !important;
      color: rgba(255, 255, 255, 0.75) !important;
      margin: 0 0 20px 0 !important;
      text-align: center !important;
    }

    .gm-reset-feedback {
      margin-top: 16px !important;
      padding: 14px 16px !important;
      border-radius: 12px !important;
      font-size: 13px !important;
      text-align: center !important;
      line-height: 1.5 !important;
      background: rgba(255, 255, 255, 0.04) !important;
      border: 1px solid rgba(255, 255, 255, 0.12) !important;
      color: #ffffff !important;
    }

    .gm-back-to-signin-btn {
      background: none !important;
      border: none !important;
      font-family: inherit !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      color: rgba(255, 255, 255, 0.72) !important;
      cursor: pointer !important;
      text-decoration: underline !important;
      text-underline-offset: 3px !important;
      transition: color 0.15s ease !important;
    }

    .gm-back-to-signin-btn:hover {
      color: #ffffff !important;
    }

    /* ========================================================================
       SHARE POST MODAL (DARK MODE - OBSIDIAN MONOCHROME)
       ======================================================================== */
    .gh-portal-popup-container.share,
    .gh-portal-popup-container:has(.gh-portal-share),
    .gh-portal-popup-container:has(.gh-portal-share-actions),
    .gh-portal-popup-container:has(.gh-portal-share-preview) {
      max-width: 560px !important;
      width: 100% !important;
      padding: 34px 30px !important;
      border-radius: 24px !important;
      background: linear-gradient(180deg, rgba(22, 27, 38, 0.94) 0%, rgba(12, 16, 24, 0.97) 100%) !important;
      backdrop-filter: blur(40px) saturate(200%) !important;
      -webkit-backdrop-filter: blur(40px) saturate(200%) !important;
      border: 1px solid rgba(255, 255, 255, 0.16) !important;
      box-shadow: 0 32px 72px -12px rgba(0, 0, 0, 0.95), 0 12px 30px rgba(0, 0, 0, 0.75) !important;
    }

    .gh-portal-share-header {
      margin-bottom: 22px !important;
    }
    .gh-portal-share-header .gh-portal-main-title {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
      font-size: 22px !important;
      font-weight: 700 !important;
      letter-spacing: -0.02em !important;
      text-align: left !important;
    }

    .gh-portal-share-preview {
      background-color: rgba(255, 255, 255, 0.04) !important;
      border: 1px solid rgba(255, 255, 255, 0.12) !important;
      border-radius: 16px !important;
      overflow: hidden !important;
      transition: border-color 0.2s ease, background-color 0.2s ease !important;
    }
    .gh-portal-share-preview:hover {
      background-color: rgba(255, 255, 255, 0.06) !important;
      border-color: rgba(255, 255, 255, 0.2) !important;
    }
    .gh-portal-share-preview-image {
      border-radius: 15px 15px 0 0 !important;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    .gh-portal-share-preview-content {
      padding: 18px 20px !important;
      gap: 12px !important;
    }
    .gh-portal-share-preview-title {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
      font-size: 18px !important;
      font-weight: 700 !important;
      line-height: 1.35 !important;
      letter-spacing: -0.015em !important;
    }
    .gh-portal-share-preview-excerpt {
      color: rgba(255, 255, 255, 0.72) !important;
      -webkit-text-fill-color: rgba(255, 255, 255, 0.72) !important;
      font-size: 14px !important;
      line-height: 1.5 !important;
    }
    .gh-portal-share-preview-footer {
      margin-top: 2px !important;
    }
    .gh-portal-share-preview-site {
      color: rgba(255, 255, 255, 0.7) !important;
      font-size: 13px !important;
      font-weight: 600 !important;
    }
    .gh-portal-share-preview-author {
      color: rgba(255, 255, 255, 0.5) !important;
      font-size: 13px !important;
    }
    .gh-portal-share-preview-separator {
      color: rgba(255, 255, 255, 0.3) !important;
    }

    .gh-portal-share-actions {
      display: flex !important;
      align-items: center !important;
      gap: 12px !important;
      margin-top: 22px !important;
    }

    /* Primary Copy Link Button */
    .gh-portal-share-action.copy {
      background-color: #ffffff !important;
      background: #ffffff !important;
      color: #000000 !important;
      -webkit-text-fill-color: #000000 !important;
      border: 1px solid rgba(255, 255, 255, 0.95) !important;
      border-radius: 12px !important;
      height: 46px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
      box-shadow: 0 4px 14px rgba(255, 255, 255, 0.15) !important;
    }
    .gh-portal-share-action.copy:hover {
      background-color: #f1f5f9 !important;
      background: #f1f5f9 !important;
      border-color: #f1f5f9 !important;
      transform: translateY(-1px) !important;
      box-shadow: 0 6px 20px rgba(255, 255, 255, 0.25) !important;
    }
    .gh-portal-share-action.copy .gh-portal-share-label {
      color: #000000 !important;
      -webkit-text-fill-color: #000000 !important;
      font-size: 14px !important;
      font-weight: 600 !important;
    }
    .gh-portal-share-action.copy .gh-portal-share-icon svg {
      stroke: #000000 !important;
      color: #000000 !important;
      fill: none !important;
    }

    /* Secondary Social Actions */
    .gh-portal-share-action:not(.copy) {
      background-color: rgba(255, 255, 255, 0.08) !important;
      border: 1px solid rgba(255, 255, 255, 0.16) !important;
      border-radius: 12px !important;
      height: 46px !important;
      color: #ffffff !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }
    .gh-portal-share-action:not(.copy):hover {
      background-color: rgba(255, 255, 255, 0.16) !important;
      border-color: rgba(255, 255, 255, 0.3) !important;
      transform: translateY(-1px) !important;
    }
    .gh-portal-share-action.twitter svg,
    .gh-portal-share-action .x svg {
      fill: #ffffff !important;
    }
    .gh-portal-share-action.email svg,
    .gh-portal-share-action.more svg {
      stroke: #ffffff !important;
      color: #ffffff !important;
    }

    /* Dropdown More Menu */
    .gh-portal-share-more-menu {
      background: linear-gradient(180deg, #18202c 0%, #0f141c 100%) !important;
      border: 1px solid rgba(255, 255, 255, 0.18) !important;
      border-radius: 14px !important;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.06) !important;
      padding: 8px !important;
    }
    .gh-portal-share-more-item {
      color: #e2e8f0 !important;
      border-radius: 8px !important;
      padding: 8px 12px !important;
      transition: all 0.15s ease !important;
    }
    .gh-portal-share-more-item:hover {
      background: rgba(255, 255, 255, 0.08) !important;
      color: #ffffff !important;
    }
    .gh-portal-share-more-item svg {
      color: #ffffff !important;
      stroke: currentColor !important;
    }

    /* Responsive Mobile Layout */
    @media (max-width: 580px) {
      .gh-portal-popup-container.share,
      .gh-portal-popup-container:has(.gh-portal-share) {
        padding: 24px 18px !important;
        margin: 16px auto !important;
        width: calc(100% - 24px) !important;
      }
      .gh-portal-share-actions {
        flex-wrap: wrap !important;
        gap: 10px !important;
      }
      .gh-portal-share-action.copy {
        min-width: 100% !important;
        order: 1 !important;
      }
      .gh-portal-share-action:not(.copy) {
        flex: 1 1 auto !important;
        max-width: none !important;
        order: 2 !important;
      }
      .gh-portal-share-more {
        order: 2 !important;
        flex: 1 1 auto !important;
      }
      .gh-portal-share-action.more {
        width: 100% !important;
        max-width: none !important;
      }
    }
  `;

  const lightCSS = `
    :root, html, body {
      --brandcolor: #000000 !important;
      --ghost-accent-color: #000000 !important;
      accent-color: #000000 !important;
      box-sizing: border-box !important;
    }

    html, body {
      background: transparent !important;
      margin: 0 !important;
      padding: 0 !important;
      width: 100% !important;
      height: 100% !important;
      overflow-x: hidden !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif !important;
    }

    /* Fullscreen Backdrop Blur & Refined Contrast (Light Mode) */
    .gh-portal-popup-background {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      background: radial-gradient(circle at 50% 40%, rgba(241, 245, 249, 0.72) 0%, rgba(15, 23, 42, 0.45) 100%) !important;
      backdrop-filter: blur(24px) saturate(180%) !important;
      -webkit-backdrop-filter: blur(24px) saturate(180%) !important;
      z-index: 10 !important;
      animation: gmPortalFade 0.22s ease forwards !important;
    }

    .gh-portal-popup-wrapper {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      display: flex !important;
      align-items: flex-start !important;
      justify-content: center !important;
      background: transparent !important;
      padding: 40px 16px 48px 16px !important;
      box-sizing: border-box !important;
      z-index: 20 !important;
      overflow-y: auto !important;
      -webkit-overflow-scrolling: touch !important;
    }

    .gh-portal-popup-container {
      margin: auto !important;
      width: 100% !important;
      max-width: 480px !important;
      position: relative !important;
      box-sizing: border-box !important;
      padding: 38px 34px !important;
      border-radius: 24px !important;
      background: rgba(255, 255, 255, 0.94) !important;
      backdrop-filter: blur(36px) saturate(190%) !important;
      -webkit-backdrop-filter: blur(36px) saturate(190%) !important;
      border: 1px solid rgba(0, 0, 0, 0.12) !important;
      box-shadow: 0 32px 72px -12px rgba(15, 23, 42, 0.25), 
                  0 12px 28px rgba(15, 23, 42, 0.12), 
                  0 0 0 1px rgba(0, 0, 0, 0.05),
                  inset 0 1px 0 rgba(255, 255, 255, 1) !important;
      color: #0f172a !important;
      animation: gmPortalFadeIn 0.28s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    }

    .gh-portal-popup-container.account,
    .gh-portal-popup-container:has(.gh-portal-email-preferences-header),
    .gh-portal-popup-container:has(.gh-portal-account-header),
    .gh-portal-popup-container:has(.gh-portal-list-toggle-wrapper) {
      max-width: 520px !important;
      padding: 38px 34px !important;
    }

    .gh-portal-closeicon-container {
      cursor: pointer !important;
      top: 18px !important;
      right: 18px !important;
      position: absolute !important;
      width: 34px !important;
      height: 34px !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      z-index: 50 !important;
      border-radius: 50% !important;
      background: rgba(0, 0, 0, 0.05) !important;
      border: 1px solid rgba(0, 0, 0, 0.1) !important;
      transition: all 0.2s ease !important;
    }

    .gh-portal-closeicon-container:hover {
      background: rgba(0, 0, 0, 0.1) !important;
      border-color: rgba(0, 0, 0, 0.2) !important;
      transform: scale(1.05) !important;
    }

    .gh-portal-closeicon {
      color: #475569 !important;
      transition: color 0.2s ease !important;
    }

    .gh-portal-closeicon:hover {
      color: #0f172a !important;
    }

    .gh-portal-input {
      background: rgba(0, 0, 0, 0.03) !important;
      border: 1px solid rgba(0, 0, 0, 0.16) !important;
      border-radius: 12px !important;
      color: #0f172a !important;
      font-size: 15px !important;
      height: 48px !important;
      padding: 0 16px !important;
      outline: none !important;
      transition: all 0.2s ease !important;
      box-sizing: border-box !important;
      width: 100% !important;
      box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.04) !important;
    }

    .gh-portal-input:focus {
      border-color: #000000 !important;
      background: #ffffff !important;
      box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.15), inset 0 2px 4px rgba(0, 0, 0, 0.04) !important;
    }

    .gh-portal-input-label {
      color: #475569 !important;
      font-size: 11.5px !important;
      font-weight: 700 !important;
      text-transform: uppercase !important;
      letter-spacing: 0.07em !important;
      margin-bottom: 7px !important;
    }


    .gh-portal-main-title,
    .gh-portal-detail-header h3,
    .gh-portal-account-header h2 {
      color: #0f172a !important;
      font-weight: 800 !important;
      font-size: 22px !important;
      letter-spacing: -0.03em !important;
      margin: 0 !important;
      text-align: center !important;
    }

    .gh-portal-email-preferences-header,
    .gh-portal-detail-header {
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      position: relative !important;
      width: 100% !important;
      margin-bottom: 24px !important;
      min-height: 36px !important;
    }

    .gh-portal-detail-header .gh-portal-btn-back {
      position: absolute !important;
      left: 0 !important;
      top: 50% !important;
      transform: translateY(-50%) !important;
      width: 36px !important;
      height: 36px !important;
      border-radius: 50% !important;
      background: rgba(0, 0, 0, 0.05) !important;
      border: 1px solid rgba(0, 0, 0, 0.1) !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      cursor: pointer !important;
      padding: 0 !important;
      color: #64748b !important;
      transition: all 0.2s ease !important;
    }

    .gh-portal-detail-header .gh-portal-btn-back:hover {
      background: rgba(0, 0, 0, 0.1) !important;
      color: #0f172a !important;
    }

    /* Buttons Light Mode */
    .gh-portal-btn-primary,
    .gh-portal-btn-main,
    .gh-portal-btn-branded,
    button[type="submit"].gh-portal-btn,
    .gh-portal-btn[type="submit"],
    button.gh-portal-btn-main {
      background: #000000 !important;
      color: #ffffff !important;
      border-radius: 999px !important;
      font-weight: 700 !important;
      font-size: 15px !important;
      height: 48px !important;
      width: 100% !important;
      border: 1px solid #000000 !important;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3) !important;
      cursor: pointer !important;
      transition: all 0.2s ease !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
    }

    .gh-portal-btn-primary:hover,
    .gh-portal-btn-main:hover,
    .gh-portal-btn-branded:hover,
    button[type="submit"].gh-portal-btn:hover,
    button.gh-portal-btn-main:hover {
      background: #262626 !important;
      background-color: #262626 !important;
      color: #ffffff !important;
      border-color: #262626 !important;
      transform: translateY(-1px) !important;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4) !important;
    }

    /* Primary / Submit Button Disabled & Loading State (Light Mode) */
    .gh-portal-btn-primary[disabled],
    .gh-portal-btn-main[disabled],
    .gh-portal-btn-branded[disabled],
    button[type="submit"].gh-portal-btn[disabled],
    .gh-portal-btn[type="submit"][disabled],
    button.gh-portal-btn-main[disabled],
    .gh-portal-btn[disabled] {
      background: #000000 !important;
      background-color: #000000 !important;
      border-color: #000000 !important;
      opacity: 0.88 !important;
      cursor: not-allowed !important;
      position: relative !important;
    }

    /* Loading Spinner in Light Mode -> on BLACK button, spinner is Solid Pure White */
    .gh-portal-loadingicon,
    .gh-portal-loadingicon.dark,
    svg#loader-1.gh-portal-loadingicon {
      position: absolute !important;
      left: 50% !important;
      top: 50% !important;
      transform: translate(-50%, -50%) !important;
      margin: 0 !important;
      margin-inline-start: 0 !important;
      height: 28px !important;
      width: 28px !important;
      display: block !important;
      z-index: 10 !important;
    }

    .gh-portal-loadingicon path,
    .gh-portal-loadingicon rect,
    .gh-portal-loadingicon.dark path,
    .gh-portal-loadingicon.dark rect,
    svg#loader-1.gh-portal-loadingicon path,
    svg#loader-1.gh-portal-loadingicon rect {
      fill: #ffffff !important;
      stroke: none !important;
    }

    /* When submit/primary button is loading, hide text so it doesn't collide with spinner */
    button[disabled]:has(.gh-portal-loadingicon),
    button[disabled]:has(svg#loader-1) {
      color: transparent !important;
    }

    button:has(.gh-portal-loadingicon) > span:not(.gh-portal-loadingicon *),
    button:has(svg#loader-1) > span:not(svg#loader-1 *) {
      opacity: 0 !important;
      visibility: hidden !important;
    }

    .gh-portal-btn-secondary,
    .gh-portal-btn-cancel,
    button.gh-portal-btn-secondary,
    button.gh-portal-btn-cancel {
      background: rgba(0, 0, 0, 0.05) !important;
      border: 1px solid rgba(0, 0, 0, 0.12) !important;
      color: #475569 !important;
      border-radius: 999px !important;
      font-size: 14px !important;
      font-weight: 600 !important;
      height: 46px !important;
      padding: 0 24px !important;
    }

    .gh-portal-list-action,
    .gh-portal-btn-list,
    button.gh-portal-btn-list,
    button[data-test-button="change-plan"],
    span[data-test-button="edit-profile"],
    span[data-test-button="edit-newsletters"] {
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      padding: 6px 16px !important;
      border-radius: 999px !important;
      background: rgba(0, 0, 0, 0.08) !important;
      border: 1px solid rgba(0, 0, 0, 0.25) !important;
      color: #000000 !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      text-decoration: none !important;
    }

    .gh-portal-list-action:hover,
    .gh-portal-btn-list:hover,
    button.gh-portal-btn-list:hover {
      background: #000000 !important;
      color: #ffffff !important;
    }

    /* Switches (Light Mode -> Lunar Blue #000000) */
    .gh-portal-for-switch {
      position: relative !important;
      display: inline-flex !important;
      align-items: center !important;
      flex-shrink: 0 !important;
      margin: 0 !important;
    }

    .gh-portal-for-switch .switch {
      position: relative !important;
      display: inline-block !important;
      width: 46px !important;
      height: 26px !important;
      margin: 0 !important;
      cursor: pointer !important;
    }

    .gh-portal-for-switch input[type="checkbox"] {
      position: absolute !important;
      opacity: 0 !important;
      width: 0 !important;
      height: 0 !important;
    }

    .gh-portal-for-switch .input-toggle-component,
    .input-toggle-component {
      position: absolute !important;
      inset: 0 !important;
      background: rgba(0, 0, 0, 0.14) !important;
      border: 1px solid rgba(0, 0, 0, 0.12) !important;
      border-radius: 999px !important;
      transition: all 0.25s ease !important;
      cursor: pointer !important;
      width: 46px !important;
      height: 26px !important;
    }

    .gh-portal-for-switch .input-toggle-component:before,
    .input-toggle-component:before {
      position: absolute !important;
      content: "" !important;
      height: 18px !important;
      width: 18px !important;
      left: 3px !important;
      bottom: 3px !important;
      background: #ffffff !important;
      border-radius: 50% !important;
      transition: transform 0.25s ease !important;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2) !important;
    }

    .gh-portal-for-switch input:checked + .input-toggle-component,
    input[type="checkbox"]:checked + .input-toggle-component,
    .input-toggle-component.checked,
    [style*="rgb(240, 37, 116)"],
    [style*="#ff0077"],
    [style*="rgb(255, 0, 119)"] {
      background: #000000 !important;
      background-color: #000000 !important;
      border-color: #000000 !important;
      box-shadow: 0 0 14px rgba(0, 0, 0, 0.35) !important;
    }

    .gh-portal-for-switch input:checked + .input-toggle-component:before,
    input[type="checkbox"]:checked + .input-toggle-component:before {
      transform: translateX(20px) !important;
      background: #ffffff !important;
    }

    /* List Cards Light Mode */
    .gh-portal-list {
      display: flex !important;
      flex-direction: column !important;
      gap: 12px !important;
      width: 100% !important;
      background: transparent !important;
      border: none !important;
      padding: 0 !important;
      margin: 0 !important;
    }

    .gh-portal-section.flex {
      display: block !important;
      width: 100% !important;
      margin: 0 !important;
      padding: 0 !important;
    }

    .gh-portal-list-toggle-wrapper,
    .gh-portal-list-clickable,
    .gh-portal-list > section {
      display: flex !important;
      flex-direction: row !important;
      align-items: center !important;
      justify-content: space-between !important;
      background: rgba(0, 0, 0, 0.03) !important;
      border: 1px solid rgba(0, 0, 0, 0.08) !important;
      border-radius: 16px !important;
      padding: 18px 20px !important;
      margin: 0 !important;
      width: 100% !important;
      box-sizing: border-box !important;
      transition: all 0.2s ease !important;
      cursor: pointer !important;
      text-align: left !important;
    }

    .gh-portal-list-toggle-wrapper:hover,
    .gh-portal-list-clickable:hover,
    .gh-portal-list > section:hover {
      background: rgba(0, 0, 0, 0.06) !important;
      border-color: rgba(0, 0, 0, 0.3) !important;
      transform: translateY(-1px) !important;
    }

    .gh-portal-list-detail h3 {
      color: #0f172a !important;
      font-size: 15px !important;
      font-weight: 700 !important;
      margin: 0 0 3px 0 !important;
    }

    .gh-portal-list-detail p {
      color: #64748b !important;
      font-size: 13px !important;
      margin: 0 !important;
      line-height: 1.45 !important;
    }

    .gh-portal-list-help {
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      padding: 14px 18px !important;
      background: rgba(0, 0, 0, 0.02) !important;
      border: 1px dashed rgba(0, 0, 0, 0.15) !important;
      border-radius: 14px !important;
      margin-top: 8px !important;
    }

    .gh-portal-list-help-label {
      color: #64748b !important;
      font-size: 13px !important;
    }

    .gh-portal-btn-text.gh-email-faq-page-button {
      color: #000000 !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      background: none !important;
      border: none !important;
    }

    .gh-portal-btn-unsubscribe button {
      width: 100% !important;
      height: 44px !important;
      border-radius: 999px !important;
      background: rgba(239, 68, 68, 0.08) !important;
      border: 1px solid rgba(239, 68, 68, 0.25) !important;
      color: #dc2626 !important;
      font-size: 14px !important;
      font-weight: 600 !important;
    }

    footer.gh-portal-account-footer {
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      margin-top: 24px !important;
      width: 100% !important;
    }

    .gh-portal-account-footer button.gh-portal-btn {
      background: rgba(0, 0, 0, 0.06) !important;
      border: 1px solid rgba(0, 0, 0, 0.12) !important;
      color: #334155 !important;
      border-radius: 999px !important;
      padding: 8px 18px !important;
      font-size: 13px !important;
    }

    a[data-test-link="footer-support"] {
      background: rgba(0, 0, 0, 0.1) !important;
      border: 1px solid rgba(0, 0, 0, 0.3) !important;
      color: #000000 !important;
      border-radius: 999px !important;
      padding: 8px 18px !important;
      font-size: 13px !important;
      font-weight: 700 !important;
      text-decoration: none !important;
    }

    /* Input Fields (Sign In / Sign Up / Edit Profile) Light Mode */
    .gh-portal-input {
      background: rgba(0, 0, 0, 0.04) !important;
      border: 1px solid rgba(0, 0, 0, 0.14) !important;
      border-radius: 12px !important;
      color: #0f172a !important;
      font-size: 15px !important;
      height: 48px !important;
      padding: 0 16px !important;
      outline: none !important;
      transition: all 0.2s ease !important;
      box-sizing: border-box !important;
      width: 100% !important;
    }

    .gh-portal-input:focus {
      border-color: #000000 !important;
      background: rgba(0, 0, 0, 0.06) !important;
      box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.15) !important;
    }

    .gh-portal-input-label {
      color: #64748b !important;
      font-size: 11px !important;
      font-weight: 700 !important;
      text-transform: uppercase !important;
      letter-spacing: 0.06em !important;
      margin-bottom: 6px !important;
    }

    /* Sign in / Sign up Bottom Message & Switch Link (Light Mode) */
    .gh-portal-signup-message {
      display: flex !important;
      flex-wrap: wrap !important;
      align-items: center !important;
      justify-content: center !important;
      gap: 6px !important;
      margin: 20px 0 0 0 !important;
      color: rgba(0, 0, 0, 0.7) !important;
      font-size: 14px !important;
    }

    .gh-portal-signup-message div,
    .gh-portal-signup-message p,
    .gh-portal-signup-message span {
      color: rgba(0, 0, 0, 0.7) !important;
      font-size: 14px !important;
    }

    .gh-portal-signup-message .gh-portal-btn-link,
    .gh-portal-btn.gh-portal-btn-link,
    button[data-test-button="signup-switch"],
    button[data-test-button="signin-switch"],
    button[data-testid="signin-switch"],
    button[data-test-button="gift-switch"],
    button.gh-portal-btn-link {
      color: #000000 !important;
      -webkit-text-fill-color: #000000 !important;
      font-weight: 700 !important;
      font-size: 14px !important;
      text-decoration: underline !important;
      text-underline-offset: 3px !important;
      background: transparent !important;
      border: none !important;
      box-shadow: none !important;
      padding: 0 !important;
      margin: 0 !important;
      height: auto !important;
      width: auto !important;
      cursor: pointer !important;
      display: inline-flex !important;
      transition: opacity 0.2s ease !important;
    }

    .gh-portal-signup-message .gh-portal-btn-link span,
    button[data-test-button="signup-switch"] span,
    button[data-test-button="signin-switch"] span {
      color: #000000 !important;
      -webkit-text-fill-color: #000000 !important;
      font-weight: 700 !important;
    }

    .gh-portal-signup-message .gh-portal-btn-link:hover,
    button[data-test-button="signup-switch"]:hover,
    button[data-test-button="signin-switch"]:hover {
      opacity: 0.7 !important;
      color: #000000 !important;
      -webkit-text-fill-color: #000000 !important;
    }

    /* Back Button in Site Title Header (Light Mode) */
    .gh-portal-btn-site-title-back,
    button.gh-portal-btn-site-title-back {
      color: #000000 !important;
      -webkit-text-fill-color: #000000 !important;
      background: transparent !important;
      border: none !important;
      font-size: 14px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      display: inline-flex !important;
      align-items: center !important;
      gap: 6px !important;
      padding: 0 !important;
      margin-bottom: 12px !important;
      transition: transform 0.2s ease, opacity 0.2s ease !important;
    }

    .gh-portal-btn-site-title-back:hover {
      opacity: 0.7 !important;
      transform: translateX(-2px) !important;
    }

    .gh-portal-btn-site-title-back span {
      color: #000000 !important;
      -webkit-text-fill-color: #000000 !important;
    }

    .gh-portal-powered,
    #ghost-portal-root .gh-portal-powered {
      display: none !important;
    }

    @media (max-width: 640px) {
      .gh-portal-popup-wrapper {
        padding: 16px 12px 36px 12px !important;
      }
      .gh-portal-popup-container {
        padding: 24px 16px !important;
        border-radius: 20px !important;
        max-width: 100% !important;
        width: 100% !important;
      }
      footer.gh-portal-account-footer {
        flex-direction: column !important;
        gap: 10px !important;
      }
      .gh-portal-account-footermenu,
      .gh-portal-account-footerright {
        width: 100% !important;
      }
      .gh-portal-account-footer button.gh-portal-btn,
      a[data-test-link="footer-support"] {
        width: 100% !important;
        height: 44px !important;
        justify-content: center !important;
        display: inline-flex !important;
        align-items: center !important;
      }
    }

    /* Forgot Password & Reset View (Light Mode) */
    .gm-forgot-password-row {
      text-align: center !important;
      margin: 14px 0 6px 0 !important;
    }

    .gm-forgot-password-btn {
      background: none !important;
      border: none !important;
      padding: 4px 8px !important;
      font-family: inherit !important;
      font-size: 13px !important;
      font-weight: 500 !important;
      color: rgba(0, 0, 0, 0.65) !important;
      cursor: pointer !important;
      text-decoration: underline !important;
      text-underline-offset: 3px !important;
      transition: color 0.15s ease !important;
      outline: none !important;
    }

    .gm-forgot-password-btn:hover {
      color: #000000 !important;
    }

    .gm-portal-reset-view {
      animation: gmPortalFadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    }

    .gm-portal-reset-desc {
      font-family: inherit !important;
      font-size: 14px !important;
      line-height: 1.6 !important;
      color: rgba(0, 0, 0, 0.75) !important;
      margin: 0 0 20px 0 !important;
      text-align: center !important;
    }

    .gm-reset-feedback {
      margin-top: 16px !important;
      padding: 14px 16px !important;
      border-radius: 12px !important;
      font-size: 13px !important;
      text-align: center !important;
      line-height: 1.5 !important;
      background: rgba(0, 0, 0, 0.03) !important;
      border: 1px solid rgba(0, 0, 0, 0.12) !important;
      color: #000000 !important;
    }

    .gm-back-to-signin-btn {
      background: none !important;
      border: none !important;
      font-family: inherit !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      color: rgba(0, 0, 0, 0.65) !important;
      cursor: pointer !important;
      text-decoration: underline !important;
      text-underline-offset: 3px !important;
      transition: color 0.15s ease !important;
    }

    .gm-back-to-signin-btn:hover {
      color: #000000 !important;
    }

    /* ========================================================================
       SHARE POST MODAL (LIGHT MODE - OBSIDIAN MONOCHROME)
       ======================================================================== */
    .gh-portal-popup-container.share,
    .gh-portal-popup-container:has(.gh-portal-share),
    .gh-portal-popup-container:has(.gh-portal-share-actions),
    .gh-portal-popup-container:has(.gh-portal-share-preview) {
      max-width: 560px !important;
      width: 100% !important;
      padding: 34px 30px !important;
      border-radius: 24px !important;
      background: rgba(255, 255, 255, 0.96) !important;
      backdrop-filter: blur(36px) saturate(190%) !important;
      -webkit-backdrop-filter: blur(36px) saturate(190%) !important;
      border: 1px solid rgba(0, 0, 0, 0.12) !important;
      box-shadow: 0 32px 72px -12px rgba(15, 23, 42, 0.25), 0 12px 28px rgba(15, 23, 42, 0.12) !important;
    }

    .gh-portal-share-header {
      margin-bottom: 22px !important;
    }
    .gh-portal-share-header .gh-portal-main-title {
      color: #0f172a !important;
      -webkit-text-fill-color: #0f172a !important;
      font-size: 22px !important;
      font-weight: 700 !important;
      letter-spacing: -0.02em !important;
      text-align: left !important;
    }

    .gh-portal-share-preview {
      background-color: #f8fafc !important;
      border: 1px solid rgba(0, 0, 0, 0.1) !important;
      border-radius: 16px !important;
      overflow: hidden !important;
      transition: border-color 0.2s ease, background-color 0.2s ease !important;
    }
    .gh-portal-share-preview:hover {
      background-color: #f1f5f9 !important;
      border-color: rgba(0, 0, 0, 0.18) !important;
    }
    .gh-portal-share-preview-image {
      border-radius: 15px 15px 0 0 !important;
      border-bottom: 1px solid rgba(0, 0, 0, 0.08) !important;
    }
    .gh-portal-share-preview-content {
      padding: 18px 20px !important;
      gap: 12px !important;
    }
    .gh-portal-share-preview-title {
      color: #0f172a !important;
      -webkit-text-fill-color: #0f172a !important;
      font-size: 18px !important;
      font-weight: 700 !important;
      line-height: 1.35 !important;
      letter-spacing: -0.015em !important;
    }
    .gh-portal-share-preview-excerpt {
      color: #475569 !important;
      -webkit-text-fill-color: #475569 !important;
      font-size: 14px !important;
      line-height: 1.5 !important;
    }
    .gh-portal-share-preview-footer {
      margin-top: 2px !important;
    }
    .gh-portal-share-preview-site {
      color: #334155 !important;
      font-size: 13px !important;
      font-weight: 600 !important;
    }
    .gh-portal-share-preview-author {
      color: #64748b !important;
      font-size: 13px !important;
    }
    .gh-portal-share-preview-separator {
      color: #cbd5e1 !important;
    }

    .gh-portal-share-actions {
      display: flex !important;
      align-items: center !important;
      gap: 12px !important;
      margin-top: 22px !important;
    }

    /* Primary Copy Link Button */
    .gh-portal-share-action.copy {
      background-color: #0f172a !important;
      background: #0f172a !important;
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
      border: 1px solid #0f172a !important;
      border-radius: 12px !important;
      height: 46px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
      box-shadow: 0 4px 14px rgba(15, 23, 42, 0.15) !important;
    }
    .gh-portal-share-action.copy:hover {
      background-color: #1e293b !important;
      background: #1e293b !important;
      border-color: #1e293b !important;
      transform: translateY(-1px) !important;
      box-shadow: 0 6px 20px rgba(15, 23, 42, 0.25) !important;
    }
    .gh-portal-share-action.copy .gh-portal-share-label {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
      font-size: 14px !important;
      font-weight: 600 !important;
    }
    .gh-portal-share-action.copy .gh-portal-share-icon svg {
      stroke: #ffffff !important;
      color: #ffffff !important;
      fill: none !important;
    }

    /* Secondary Social Actions */
    .gh-portal-share-action:not(.copy) {
      background-color: #f1f5f9 !important;
      border: 1px solid rgba(0, 0, 0, 0.1) !important;
      border-radius: 12px !important;
      height: 46px !important;
      color: #0f172a !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }
    .gh-portal-share-action:not(.copy):hover {
      background-color: #e2e8f0 !important;
      border-color: rgba(0, 0, 0, 0.18) !important;
      transform: translateY(-1px) !important;
    }
    .gh-portal-share-action.twitter svg,
    .gh-portal-share-action .x svg {
      fill: #0f172a !important;
    }
    .gh-portal-share-action.email svg,
    .gh-portal-share-action.more svg {
      stroke: #0f172a !important;
      color: #0f172a !important;
    }

    /* Dropdown More Menu */
    .gh-portal-share-more-menu {
      background: #ffffff !important;
      border: 1px solid rgba(0, 0, 0, 0.12) !important;
      border-radius: 14px !important;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.15) !important;
      padding: 8px !important;
    }
    .gh-portal-share-more-item {
      color: #1e293b !important;
      border-radius: 8px !important;
      padding: 8px 12px !important;
      transition: all 0.15s ease !important;
    }
    .gh-portal-share-more-item:hover {
      background: #f1f5f9 !important;
      color: #0f172a !important;
    }
    .gh-portal-share-more-item svg {
      color: #0f172a !important;
      stroke: currentColor !important;
    }

    /* Responsive Mobile Layout */
    @media (max-width: 580px) {
      .gh-portal-popup-container.share,
      .gh-portal-popup-container:has(.gh-portal-share) {
        padding: 24px 18px !important;
        margin: 16px auto !important;
        width: calc(100% - 24px) !important;
      }
      .gh-portal-share-actions {
        flex-wrap: wrap !important;
        gap: 10px !important;
      }
      .gh-portal-share-action.copy {
        min-width: 100% !important;
        order: 1 !important;
      }
      .gh-portal-share-action:not(.copy) {
        flex: 1 1 auto !important;
        max-width: none !important;
        order: 2 !important;
      }
      .gh-portal-share-more {
        order: 2 !important;
        flex: 1 1 auto !important;
      }
      .gh-portal-share-action.more {
        width: 100% !important;
        max-width: none !important;
      }
    }
  `;

  function getIsDark() {
    const root = document.documentElement;
    if (!root) return true;
    if (root.classList.contains('light-mode') || root.getAttribute('data-theme') === 'light') {
      return false;
    }
    if (root.classList.contains('dark-mode') || root.getAttribute('data-theme') === 'dark') {
      return true;
    }
    return true;
  }

  function cleanPinkDOM(doc) {
    if (!doc) return;
    const isDark = getIsDark();
    const accent = isDark ? '#ffffff' : '#000000';
    const spinnerFill = isDark ? '#040609' : '#ffffff';
    const msgColor = isDark ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.7)';

    try {
      // 1. Sanitize any pink/accent inline backgrounds and borders
      const allEls = doc.querySelectorAll('*');
      for (let i = 0; i < allEls.length; i++) {
        const el = allEls[i];
        const s = el.getAttribute('style');
        if (s && (s.includes('240, 37, 116') || s.includes('ff0077') || s.includes('255, 0, 119'))) {
          el.style.setProperty('background-color', accent, 'important');
          el.style.setProperty('border-color', accent, 'important');
        }
      }

      // 2. Fix switch buttons (signup-switch, signin-switch, gh-portal-btn-link)
      const linkBtns = doc.querySelectorAll('.gh-portal-btn-link, [data-test-button="signup-switch"], [data-test-button="signin-switch"], [data-testid="signin-switch"], [data-test-button="gift-switch"]');
      for (let i = 0; i < linkBtns.length; i++) {
        linkBtns[i].style.setProperty('color', accent, 'important');
        linkBtns[i].style.setProperty('-webkit-text-fill-color', accent, 'important');
        const spans = linkBtns[i].querySelectorAll('span');
        for (let j = 0; j < spans.length; j++) {
          spans[j].style.setProperty('color', accent, 'important');
          spans[j].style.setProperty('-webkit-text-fill-color', accent, 'important');
        }
      }

      // 3. Fix signup message text color
      const msgs = doc.querySelectorAll('.gh-portal-signup-message');
      for (let i = 0; i < msgs.length; i++) {
        msgs[i].style.setProperty('color', msgColor, 'important');
        const children = msgs[i].querySelectorAll('div, p');
        for (let j = 0; j < children.length; j++) {
          children[j].style.setProperty('color', msgColor, 'important');
        }
      }

      // 4. Fix loading icons (ensure maximum contrast against button background)
      const loadingIcons = doc.querySelectorAll('.gh-portal-loadingicon, svg#loader-1');
      for (let i = 0; i < loadingIcons.length; i++) {
        const paths = loadingIcons[i].querySelectorAll('path, rect');
        for (let j = 0; j < paths.length; j++) {
          paths[j].setAttribute('fill', spinnerFill);
          paths[j].style.setProperty('fill', spinnerFill, 'important');
        }
      }

      // 5. Fix Back button
      const backBtns = doc.querySelectorAll('.gh-portal-btn-site-title-back');
      for (let i = 0; i < backBtns.length; i++) {
        backBtns[i].style.setProperty('color', accent, 'important');
        backBtns[i].style.setProperty('-webkit-text-fill-color', accent, 'important');
        backBtns[i].style.setProperty('background', 'transparent', 'important');
        const spans = backBtns[i].querySelectorAll('span');
        for (let j = 0; j < spans.length; j++) {
          spans[j].style.setProperty('color', accent, 'important');
          spans[j].style.setProperty('-webkit-text-fill-color', accent, 'important');
        }
      }

      // 6. Enforce Share Modal Copy Button High-Contrast Color Scheme
      const shareCopyBtns = doc.querySelectorAll('.gh-portal-share-action.copy');
      for (let i = 0; i < shareCopyBtns.length; i++) {
        const copyBtn = shareCopyBtns[i];
        const copyLabel = copyBtn.querySelector('.gh-portal-share-label');
        const copyIconSvg = copyBtn.querySelector('svg');
        if (isDark) {
          copyBtn.style.setProperty('background-color', '#ffffff', 'important');
          copyBtn.style.setProperty('color', '#000000', 'important');
          if (copyLabel) copyLabel.style.setProperty('color', '#000000', 'important');
          if (copyIconSvg) copyIconSvg.style.setProperty('stroke', '#000000', 'important');
        } else {
          copyBtn.style.setProperty('background-color', '#0f172a', 'important');
          copyBtn.style.setProperty('color', '#ffffff', 'important');
          if (copyLabel) copyLabel.style.setProperty('color', '#ffffff', 'important');
          if (copyIconSvg) copyIconSvg.style.setProperty('stroke', '#ffffff', 'important');
        }
      }

      // 7. Ensure Forgot Password button and reset flow on Sign-in view
      ensureForgotPassword(doc);
    } catch (e) {}
  }


  function ensureForgotPassword(doc) {
    try {
      const signinContent = doc.querySelector('.gh-portal-content.signin');
      if (!signinContent) return;

      const signinFooter = signinContent.querySelector('.gh-portal-signin-footer');
      if (!signinFooter) return;

      let forgotRow = signinFooter.querySelector('.gm-forgot-password-row');
      if (!forgotRow) {
        forgotRow = doc.createElement('div');
        forgotRow.className = 'gm-forgot-password-row';

        const forgotBtn = doc.createElement('button');
        forgotBtn.type = 'button';
        forgotBtn.className = 'gm-forgot-password-btn';
        forgotBtn.textContent = 'Forgot password?';
        forgotRow.appendChild(forgotBtn);

        forgotBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();

          const origSection = signinContent.querySelector(':scope > section');
          if (origSection) origSection.style.display = 'none';

          const mainTitle = signinContent.querySelector('.gh-portal-main-title');
          const origTitle = mainTitle ? mainTitle.textContent : 'Sign in';
          if (mainTitle) mainTitle.textContent = 'Reset password';

          const origInput = signinContent.querySelector('#input-email');
          const existingEmail = String((origInput && origInput.value) || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');

          const oldResetView = signinContent.querySelector('.gm-portal-reset-view');
          if (oldResetView) oldResetView.remove();

          const resetView = doc.createElement('div');
          resetView.className = 'gm-portal-reset-view';

          resetView.innerHTML = `
            <div class="gh-portal-section">
              <p class="gm-portal-reset-desc">
                Enter your email address below to receive your password reset and account recovery link.
              </p>
              <section class="gh-portal-input-section">
                <div class="gh-portal-input-labelcontainer">
                  <label for="input-reset-email" class="gh-portal-input-label">Email</label>
                </div>
                <input id="input-reset-email" class="gh-portal-input" type="email" placeholder="jamie@example.com" value="${existingEmail}" autocomplete="email">
              </section>
            </div>
            <footer class="gh-portal-signin-footer" style="margin-top: 20px;">
              <button type="button" class="gh-portal-btn gh-portal-btn-main gh-portal-btn-primary gm-send-reset-btn">
                Send Reset Link
              </button>
              <div class="gm-reset-feedback" style="display: none;"></div>
              <div style="text-align: center; margin-top: 18px;">
                <button type="button" class="gm-back-to-signin-btn">
                  &larr; Back to Sign in
                </button>
              </div>
              <div class="gh-portal-signup-message gm-injected-signup-row" style="margin-top: 18px; text-align: center;">
                <span>Don't have an account?</span>
                <button type="button" class="gh-portal-btn gh-portal-btn-link gm-reset-to-signup-btn" data-test-button="signup-switch">
                  <span>Sign up</span>
                </button>
              </div>
            </footer>
          `;

          signinContent.appendChild(resetView);

          const sendBtn = resetView.querySelector('.gm-send-reset-btn');
          const resetEmailInput = resetView.querySelector('#input-reset-email');
          const feedback = resetView.querySelector('.gm-reset-feedback');
          const backBtn = resetView.querySelector('.gm-back-to-signin-btn');
          const resetSignupBtn = resetView.querySelector('.gm-reset-to-signup-btn');
          const desc = resetView.querySelector('.gm-portal-reset-desc');

          if (resetSignupBtn) {
            resetSignupBtn.addEventListener('click', (ev) => {
              ev.preventDefault();
              try {
                if (window.top) {
                  window.top.location.hash = '#/portal/signup';
                  const topDoc = window.top.document;
                  const headSignup = topDoc.querySelector('.gm-head-signup-btn, a[href*="signup"], a[href="#/portal/signup"]');
                  if (headSignup) headSignup.click();
                }
              } catch (err) {}
            });
          }
          const inputSection = resetView.querySelector('.gh-portal-input-section');

          if (resetEmailInput) {
            resetEmailInput.focus();
            resetEmailInput.addEventListener('keydown', (ke) => {
              if (ke.key === 'Enter') {
                ke.preventDefault();
                sendBtn.click();
              }
            });
          }

          backBtn.addEventListener('click', (ev) => {
            ev.preventDefault();
            resetView.remove();
            if (mainTitle) mainTitle.textContent = origTitle;
            if (origSection) origSection.style.display = '';
            if (origInput) origInput.focus();
          });

          sendBtn.addEventListener('click', async (ev) => {
            ev.preventDefault();
            const emailVal = resetEmailInput ? resetEmailInput.value.trim() : '';
            if (!emailVal || !/^[^\s@<>"]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(emailVal)) {
              feedback.style.display = 'block';
              feedback.style.borderColor = '#e11d48';
              feedback.style.color = '#f43f5e';
              feedback.textContent = 'Please enter a valid email address.';
              return;
            }

            sendBtn.disabled = true;
            sendBtn.style.opacity = '0.7';
            sendBtn.textContent = 'Sending...';

            try {
              await Promise.allSettled([
                fetch('/ghost/api/admin/authentication/password_reset/', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ password_reset: [{ email: emailVal }] })
                }),
                fetch('/members/api/send-magic-link/', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ email: emailVal, emailType: 'signin' })
                })
              ]);
            } catch (err) {}

            sendBtn.style.display = 'none';
            if (inputSection) inputSection.style.display = 'none';
            if (desc) desc.style.display = 'none';

            feedback.style.display = 'block';
            feedback.style.borderColor = '';
            feedback.style.color = '';
            feedback.textContent = '';

            const titleDiv = doc.createElement('div');
            titleDiv.style.cssText = 'font-size: 15px; font-weight: 700; margin-bottom: 6px;';
            titleDiv.textContent = '✓ Recovery link sent';

            const msgDiv = doc.createElement('div');
            msgDiv.style.cssText = 'font-size: 13px; opacity: 0.85; line-height: 1.5;';
            msgDiv.appendChild(doc.createTextNode('If an account exists for '));
            const emailStrong = doc.createElement('strong');
            emailStrong.textContent = emailVal;
            msgDiv.appendChild(emailStrong);
            msgDiv.appendChild(doc.createTextNode(', we have sent a password reset and sign-in link to your inbox.'));

            feedback.appendChild(titleDiv);
            feedback.appendChild(msgDiv);
          });
        });

        let signupMsg = signinFooter.querySelector('.gh-portal-signup-message');
        if (signupMsg) {
          signinFooter.insertBefore(forgotRow, signupMsg);
        } else {
          signinFooter.appendChild(forgotRow);
        }

        // Guarantee that a Sign Up switcher ALWAYS exists in the Sign In footer
        signupMsg = signinFooter.querySelector('.gh-portal-signup-message');
        if (!signupMsg) {
          signupMsg = doc.createElement('div');
          signupMsg.className = 'gh-portal-signup-message gm-injected-signup-row';
          signupMsg.innerHTML = '<span>Don\'t have an account?</span><button type="button" class="gh-portal-btn gh-portal-btn-link gm-signup-switch-btn" data-test-button="signup-switch"><span>Sign up</span></button>';
          signinFooter.appendChild(signupMsg);
        }

        // Ensure clicking Sign Up navigates reliably to signup view
        const signupBtn = signupMsg.querySelector('button[data-test-button="signup-switch"], button.gh-portal-btn-link, .gm-signup-switch-btn');
        if (signupBtn && !signupBtn.dataset.gmBound) {
          signupBtn.dataset.gmBound = '1';
          signupBtn.addEventListener('click', (e) => {
            try {
              if (window.top) {
                window.top.location.hash = '#/portal/signup';
                const topDoc = window.top.document;
                const headSignup = topDoc.querySelector('.gm-head-signup-btn, a[href*="signup"], a[href="#/portal/signup"]');
                if (headSignup) headSignup.click();
              }
            } catch (err) {}
          });
        }
      }
    } catch (e) {}
  }

  function injectCSS(iframe, styleId, cssContent, themeName) {
    try {
      const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
      if (!doc) return;

      const targetHead = doc.head || doc.body || doc.documentElement;
      if (!targetHead) return;

      let style = doc.getElementById(styleId);
      if (style) {
        if (style.getAttribute('data-applied-theme') !== themeName || style.textContent !== cssContent) {
          style.setAttribute('data-applied-theme', themeName);
          style.textContent = cssContent;
        }
        if (targetHead.lastElementChild !== style) {
          targetHead.appendChild(style);
        }
      } else {
        style = doc.createElement('style');
        style.id = styleId;
        style.setAttribute('data-applied-theme', themeName);
        style.textContent = cssContent;
        targetHead.appendChild(style);
      }

      cleanPinkDOM(doc);

      // Mark iframe as styled so it unhides with zero FOUC
      iframe.setAttribute('data-styled', 'true');

      if (!doc._gmObserved) {
        doc._gmObserved = true;
        const frameObs = new MutationObserver(function() {
          cleanPinkDOM(doc);
          const currentStyle = doc.getElementById(styleId);
          if (currentStyle && targetHead.lastElementChild !== currentStyle) {
            targetHead.appendChild(currentStyle);
          }
        });
        frameObs.observe(doc.documentElement, {
          attributes: true,
          childList: true,
          subtree: true,
          attributeFilter: ['style', 'class']
        });
      }
    } catch (e) {}
  }

  function applyModalThemes() {
    seedGhostAccent();
    const isDark = getIsDark();
    const isLight = !isDark;
    const themeName = isLight ? 'light' : 'dark';
    const targetPortalCSS = isLight ? lightCSS : darkCSS;

    const portalIframes = Array.from(document.querySelectorAll('iframe')).filter(function(iframe) {
      return iframe.title === 'portal-popup' ||
             iframe.closest('#ghost-portal-root') ||
             (iframe.id && iframe.id.includes('portal')) ||
             (iframe.src && iframe.src.includes('portal'));
    });

    portalIframes.forEach(function(iframe) {
      injectCSS(iframe, 'gm-portal-custom-style', targetPortalCSS, themeName);
    });
  }

  // Synchronous MutationObserver: catches iframe insertion before first paint
  const observer = new MutationObserver(function(mutations) {
    for (let i = 0; i < mutations.length; i++) {
      const added = mutations[i].addedNodes;
      for (let j = 0; j < added.length; j++) {
        const node = added[j];
        if (node.nodeType === 1) {
          if (node.id === 'ghost-portal-root' || node.tagName === 'IFRAME' || (node.querySelector && node.querySelector('iframe'))) {
            applyModalThemes();
            return;
          }
        }
      }
    }
  });

  if (document.documentElement) {
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  // Theme change observer
  const themeObserver = new MutationObserver(function() {
    applyModalThemes();
  });
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'data-theme']
  });

  window.addEventListener('hashchange', function() {
    applyModalThemes();
    let count = 0;
    const interval = setInterval(function() {
      applyModalThemes();
      count++;
      if (count >= 15) clearInterval(interval);
    }, 40);
  });

  document.addEventListener('click', function(e) {
    const target = e.target;
    if (target && target.closest && target.closest('[data-portal], a[href*="#/portal"], .gh-portal-trigger, .gm-head-signin-btn, button, input')) {
      applyModalThemes();
      let count = 0;
      const interval = setInterval(function() {
        applyModalThemes();
        count++;
        if (count >= 12) clearInterval(interval);
      }, 40);
    }
  });

  applyModalThemes();
  setInterval(applyModalThemes, 400);
})();
