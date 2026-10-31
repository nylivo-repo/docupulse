// IDP web UI settings. This file is copied as-is into dist/ and can be edited
// on the web server after deployment; no rebuild is needed.
window.IDP_CONFIG = {
  // Address of the API server as browsers reach it, e.g. "https://idp-api.corp.local".
  // Leave empty when the API serves this UI itself (single-server mode) or when a reverse proxy
  // forwards /api and /docs on this same address.
  // When set, add this UI's address to the API's config/server.ini [cors] allowed_origins.
  apiBaseUrl: "",

  // Branding. Replace the files in branding/ (same names) to change the logo and icons; see branding/README.txt.
  brand: {
    name: "IDP",                     // sidebar, sign-in page and browser tab
    tagline: "Intelligent Document Processing",  // under the name in the sidebar
    logo: "branding/logo.svg",       // square logo, SVG or PNG; empty = built-in shield in the theme colours
  },
};
