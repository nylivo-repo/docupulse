# DocuPulse web UI (Angular 22, PWA)

Needs Node.js 22 or 24.

```bash
npm ci
npm start          # http://localhost:4200, forwards /api and /docs to the API on :8000 (proxy.conf.js)
# other API / address:  IDP_API_URL=http://idp-api:8000 npx ng serve --host 0.0.0.0 --port 4300
npm run build      # production build in dist/ (served by the API, or copy it to any web server)
```

- `public/config.js` (copied to `dist/config.js`): where the API is; edit it after deploying, no rebuild.
- `ngsw-config.json`: the service worker caches the app shell only; API responses are never cached.
- Code: `src/app/core` (API client, state, shared dismiss directive, icons), `src/app/shell`
  (login, sidebar/header), `src/app/pages` (one file per screen).

See the project README and `/docs` for deployment.
