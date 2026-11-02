let settingsCache;
let urlUtils;
try {
  settingsCache = require('../../../shared/settings-cache');
  urlUtils = require('../../../shared/url-utils').default;
} catch (e) {
  // fallback if loaded outside core server
}

module.exports = ({ email, url, siteTitle, siteUrl, siteLogo }) => {
  try {
    if (!siteTitle && settingsCache) siteTitle = settingsCache.get('title');
    if (!siteUrl && urlUtils) siteUrl = urlUtils.urlFor('home', true);
    if (!siteLogo && settingsCache && urlUtils) {
      const rawLogo = settingsCache.get('logo') || settingsCache.get('icon');
      if (rawLogo) {
        siteLogo = rawLogo.startsWith('http')
          ? rawLogo
          : rawLogo.replace(/^__GHOST_URL__/, siteUrl.replace(/\/$/, '')).replace(/^\//, siteUrl.replace(/\/$/, '') + '/');
      }
    }
  } catch (e) {}

  siteTitle = siteTitle || 'Ghost';
  siteUrl = siteUrl || '#';

  return `<!doctype html>
<html>
  <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <meta name="color-scheme" content="dark">
    <meta name="supported-color-schemes" content="dark">
    <title>Confirm your email address</title>
    <style>
    @media only screen and (max-width: 620px) {
      .container { width: 100% !important; padding: 16px 10px !important; }
      .main-card { padding: 30px 22px !important; border-radius: 16px !important; }
      h1.heading { font-size: 21px !important; margin-bottom: 12px !important; }
      .btn-cta { display: block !important; width: 100% !important; box-sizing: border-box !important; text-align: center !important; }
    }
    @media all {
      .ExternalClass { width: 100%; }
      .ExternalClass, .ExternalClass p, .ExternalClass span, .ExternalClass font, .ExternalClass td, .ExternalClass div { line-height: 100%; }
    }
    a { color: #ffffff; text-decoration: none; }
    </style>
  </head>
  <body style="background-color: #08090b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; font-size: 14px; line-height: 1.6; margin: 0; padding: 0; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%;">
    <!-- PREHEADER TEXT -->
    <span style="color: transparent; display: none; height: 0; max-height: 0; max-width: 0; opacity: 0; overflow: hidden; mso-hide: all; visibility: hidden; width: 0;">Confirm your email address</span>
    <div style="display:none; max-height:0; overflow:hidden; mso-hide: all;" aria-hidden="true" role="presentation">${'&zwnj;&nbsp;'.repeat(75)}</div>

    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #08090b; width: 100%;">
      <tr>
        <td align="center" style="padding: 42px 16px;">
          <table border="0" cellpadding="0" cellspacing="0" class="container" style="max-width: 540px; width: 100%; margin: 0 auto;">
            <!-- BRAND LOGO HEADER -->
            <tr>
              <td align="center" style="padding-bottom: 28px;">
                ${siteLogo ? `
                <a href="${siteUrl}" target="_blank" style="text-decoration: none; display: inline-block;">
                  <img src="${siteLogo}" alt="${siteTitle}" style="max-height: 48px; max-width: 230px; height: auto; width: auto; border: 0; display: block; margin: 0 auto; object-fit: contain;" />
                </a>` : `
                <a href="${siteUrl}" target="_blank" style="text-decoration: none; display: inline-block; font-size: 20px; font-weight: 800; letter-spacing: -0.02em; color: #ffffff;">${siteTitle}</a>`}
              </td>
            </tr>
            <!-- MAIN CARD -->
            <tr>
              <td>
                <table border="0" cellpadding="0" cellspacing="0" width="100%" class="main-card" style="background: #111318; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 20px; padding: 42px 38px; box-shadow: 0 16px 44px rgba(0, 0, 0, 0.55);">
                  <tr>
                    <td>
                      <h1 class="heading" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 24px; font-weight: 800; color: #ffffff; letter-spacing: -0.025em; margin: 0 0 14px 0; line-height: 1.3;">Confirm your email address</h1>
                      <p style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; color: rgba(255, 255, 255, 0.74); line-height: 1.6; margin: 0 0 28px 0;">Please click the button below to verify your email address (${email}) for ${siteTitle}.</p>
                      
                      <div style="margin-bottom: 28px;">
                        <a href="${url}" target="_blank" class="btn-cta" style="display: inline-block; background-color: #ffffff; color: #000000 !important; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; font-weight: 700; text-decoration: none; border-radius: 9999px; padding: 14px 34px; letter-spacing: -0.01em; box-shadow: 0 4px 16px rgba(255, 255, 255, 0.16);">Verify email</a>
                      </div>

                      <p style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 13px; color: rgba(255, 255, 255, 0.48); line-height: 1.5; margin: 0 0 24px 0;">For your security, this verification link will expire in 24 hours.</p>

                      <!-- FALLBACK URL -->
                      <div style="border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 22px;">
                        <p style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; color: rgba(255, 255, 255, 0.5); margin: 0 0 8px 0; line-height: 1.5;">You can also copy & paste this URL into your browser:</p>
                        <p style="word-break: break-all; font-family: SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; line-height: 1.5; margin: 0; color: rgba(255, 255, 255, 0.65);">${url}</p>
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!-- FOOTER -->
            <tr>
              <td align="center" style="padding-top: 32px; padding-bottom: 16px; text-align: center;">
                <p style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; color: rgba(255, 255, 255, 0.42); margin: 0; line-height: 1.5;">If you did not request this email, you can safely ignore it.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`;
};
