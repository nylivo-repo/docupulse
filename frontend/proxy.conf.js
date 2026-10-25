// Dev server (npm start) forwards API calls to the API server. Default: the API on this machine.
// Another API:  IDP_API_URL=http://idp-api.corp.local:8000 npm start
const target = process.env.IDP_API_URL || 'http://127.0.0.1:8000';
module.exports = {
  '/api/': { target, secure: false, changeOrigin: true },
  '/docs': { target, secure: false, changeOrigin: true },
  '/openapi.json': { target, secure: false, changeOrigin: true },
};
