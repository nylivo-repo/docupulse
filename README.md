# IDP

Intelligent document processing that runs fully offline: no cloud services, no internet calls,
no LLM required. Upload any PDF, scan, photo or text file and get structured fields, with a
human review screen, templates, exports and webhooks.

## How extraction works

1. **Text**: the PDF text layer is used when present. Scanned pages and images go through
   local OCR (RapidOCR, ONNX models bundled in the pip package).
2. **Pipeline** (upload with *Auto-detect*, the default):
   - Built-in rules for **contracts/NDAs**, **passports/IDs** (ICAO 9303 MRZ with every check
     digit verified) and **invoices** (subtotal + tax = total and line items = subtotal).
   - **Templates** you define: the fields a document type has, the labels they appear under,
     types, optional regex, required flags and thresholds. Auto-detect picks the best match.
   - **General**: any other document. Every "Label: value" pair becomes a field, and dates,
     amounts, emails, phones, references and tables are listed alongside.
3. **Review**: anything not found is left empty and flagged, never guessed. Documents with
   errors, low confidence or no matching template go to the review queue.

### Templates

- *Schema Builder*: create a template field by field.
- *Review > Add Field*: on any document, draw a box around a value the extractor missed (or type
  it in) and name it. It is saved on the document and included in the JSON/CSV exports.
- *Review > Save as Template*: save the document's fields, including ones you added, as a template.
  Fields you drew are read from the same place on similar documents; a contract, passport or
  invoice keeps its built-in checks (MRZ, invoice math) underneath. Similar documents are
  recognised by the sample's header (letterhead/title), so another vendor's invoice is not mixed up.
- Documents uploaded with Auto-detect use the matching template automatically. Use
  *Re-run* in Review to re-extract an older document with a new template.
- *Templates > Edit > API*: publish a lookup endpoint for the template (e.g. `getPassportDetails`),
  tick the fields other applications may search on, and mark personal data as sensitive. Callers use
  an API key with the scope `lookup:<name>`:
  `GET /api/v1/lookup/getPassportDetails?lastName=Doe&firstName=Jane`, or POST a JSON body for
  sensitive keys such as an SSN. Only the key creator's approved documents are returned, matches are
  exact (ignoring case and punctuation), sensitive fields are masked unless the key has `pii:read`,
  and every lookup is audited. Details: /docs section 6.1.

### Optional local LLM

Off by default. To let a model on your own network fill template fields the rules miss, point
the backend at any OpenAI-compatible server (Ollama, llama.cpp, vLLM, LM Studio):

```bash
export LOCAL_LLM_URL=http://localhost:11434/v1
export LOCAL_LLM_MODEL=llama3.1:8b
```

Values the model returns are kept only when they appear verbatim in the document, and are
always flagged for review.

## Folders

The Document Hub works like Finder: create folders (and folders inside folders), open them from the
list or the path bar, drag documents onto a folder (or use *Move to…*), and pick the folder when
uploading. Documents uploaded with no folder stay at the top level. Above the list: All Documents, up to three
favourite folders (pin from an empty slot or a folder's Favourite button) and Templates. Deleting a folder moves its
contents up a level; it never deletes documents. Folders are private to each user. API:
`/api/v1/folders`, `folder_id` on upload, `?folder=<id>|root` on the document list, `POST /api/v1/documents/move`, `PATCH /api/v1/folders/<id>` with `{"favorite": true}` to pin.

## Sign-in, roles and private documents

- **First run on a new server**: the local **admin** account is created with a temporary password in
  `backend/storage/initial_admin_password.txt` (or set `IDP_ADMIN_PASSWORD` before the first start). Sign in;
  you must set your own password before anything else, and the file is then deleted. Passwords an admin sets
  for others are temporary too.
- **Sign-in method at server start**: `backend/config/auth.ini` → `[signin] mode = local` (default), `ldap` or
  `okta`, with the `[ldap]` / `[okta]` settings; secrets in `IDP_LDAP_BIND_PASSWORD` / `IDP_OKTA_CLIENT_SECRET`.
  The file wins and Admin Settings shows it read-only; `mode = ui` hands the choice to Admin Settings instead.
- **Admin Settings → Users & Sign-in** (admins only):
  - Sign-in method (when `auth.ini` has `mode = ui`; otherwise shown read-only): **Local** accounts, or **Okta** (issuer, client ID/secret, redirect URI, scopes,
    groups claim). Local admins can always sign in as a backup, so Okta problems never lock you out.
    Okta is a cloud service: the server must be able to reach your Okta address.
  - Or **Active Directory / LDAP**: server (ldaps:// or ldap:// with StartTLS), search base, service
    account, user filter, group attribute and nested AD groups. Passwords are checked by your domain
    controllers and nothing leaves the network. "Test directory" can try a real user and show their
    groups and resulting role.
  - **Group roles**: map AD/Okta group names to Admin or User, and choose what happens to people in no
    mapped group. Roles are refreshed at each Okta sign-in unless set by hand.
  - **Users**: add local users, change roles, disable accounts, reset passwords.
- Templates, API keys, webhooks and the API reference are admin-only.
- **Every document belongs to the person who uploaded it.** Nobody else, admins included, can list, open,
  export, edit or delete it; the server enforces this on every request. API keys act as the user who created them.
- Passwords are stored as salted PBKDF2 hashes (600,000 rounds), API keys and session tokens as SHA-256 hashes,
  and the Okta client secret / directory bind password encrypted (key in `backend/storage/secret.key`).

## Security and logging

- Runs on **Python 3.12** (3.11 minimum; 3.9/3.10 no longer get security fixes) with pinned packages that have no
  known vulnerabilities (`pip-audit -r backend/requirements.txt`); the UI's packages pass `npm audit`.
- Sign-in lock-out (5 failures per user / 30 per address → 15 minutes), 12-character passwords, strict
  Content-Security-Policy and security headers, cross-site request check, upload content checks, CSV formula
  protection, no stack traces or echoed input in errors.
- Logs in `backend/storage/logs/` (rotated): `app.log` (requests, errors) and `audit.log` (sign-ins, admin
  changes, every data change), JSON lines with a request id that also appears in error messages and the `X-Request-ID` response header. No passwords,
  tokens or document contents are logged. Settings: `[logging]` and `[security]` in `backend/config/server.ini`.
- Full list of controls, check results and how to repeat the checks: `/docs`, section 7.

## Database

`backend/config/database.ini` (created from `database.example.ini` on first start) chooses the database:
`engine = sqlite` (default), `postgresql` or `sqlserver`, with a section of connection settings for each.
Environment variables `IDP_DB_ENGINE`, `IDP_DB_HOST`, `IDP_DB_PORT`, `IDP_DB_NAME`, `IDP_DB_USER`,
`IDP_DB_PASSWORD` and `IDP_DB_PATH` override the file; keeping the password in `IDP_DB_PASSWORD` is recommended.

On start the server connects and, only if the tables are missing, runs `backend/db/schema/<engine>.sql`
and adds the built-in templates. A database that is already set up is left untouched. The schema files
can also be run by a DBA ahead of time (create the empty database and a login first; see each file's header).

Drivers: SQLite needs nothing. PostgreSQL needs `pip install "psycopg[binary]"`; SQL Server needs
`pip install pymssql` (no ODBC driver needed). Download them on a connected machine together with the
other wheels for an offline install.

## Run (development)

```bash
cd backend && ../venv/bin/python run.py          # API on http://127.0.0.1:8000
cd frontend && npm start                          # UI on http://localhost:4200 (forwards /api to :8000)
```

The web UI is Angular 22 and needs Node.js 22 or 24 to build (`npm ci && npm run build` → `frontend/dist`).

## Web UI: phones, tablets and install as an app

The UI is responsive: on narrow screens the sidebar becomes a slide-out menu, lists become cards and
the Review Studio stacks the page above the fields (drawing a box works with touch). It is also an
installable app (PWA): browsers offer *Install app* / *Add to Home Screen*, and the installed app's
screens load even when the server is unreachable. Documents are always fetched live, never stored on
the device. Installing needs the UI on `https://` (or `localhost`); on plain `http://` it works as a
normal web page.

Branding: replace the logo, browser-tab icon and app icons in `frontend/dist/branding/` (same file names;
sizes in `branding/README.txt` and `/docs` section 12 "Branding") and the name and tagline in `config.js` → `brand`
(shipped as "IDP" over "Intelligent Document Processing"). The product was called DocuPulse up to 1.5.0; Docker
image and container names, the example database name and the repository still use the old name (see `/docs` section 12).
No rebuild or restart; reload the page.

Themes: the user menu → *Appearance* switches Light / Dark / Auto (follows the device) and six colour
themes, including Ocean (white and blue). The choice is saved per browser.

## Install, start and stop (Mac, Linux, Windows)

| Task | Mac / Linux | Windows |
| --- | --- | --- |
| Install (Python env, packages, UI build) | `build/mac-linux/install.sh` | `build\windows\install.bat` |
| Start in the background | `build/mac-linux/start.sh` | `build\windows\start.bat` |
| Stop | `build/mac-linux/stop.sh` | `build\windows\stop.bat` |
| Status | `build/mac-linux/status.sh` | `build\windows\status.bat` |

Listen address, port and everything else come from `backend/config/server.ini`
(set `host = 0.0.0.0` to accept connections from other machines on the intranet).

## Layered deployment (UI, API and database on separate servers)

All settings are in files, no rebuild needed:

| File | Set |
| --- | --- |
| `frontend/dist/config.js` | `apiBaseUrl`: where the API server is |
| `backend/config/server.ini` | `serve_frontend = false`, `frontend_url`, `[cors] allowed_origins` (the UI's address), listen host/port, cookies |
| `backend/config/database.ini` | the database server (SQL Server / PostgreSQL / SQLite) |

Copy `frontend/dist` to any web server, run the API on its own server, and point it at the database
server. Full steps, cookie notes and examples are in the technical documentation at `/docs`.

**Changing hostnames, ports or IPs, or adding a load balancer** (several API servers): every address is a
setting, nothing is hard-coded. `/docs` section 11.9 lists where each one lives (`server.ini` host/port,
`[cors]`, `frontend_url`, `[security] trusted_proxies`, `config.js apiBaseUrl`, `database.ini`, the Okta
redirect URI), an nginx load-balancer example and a step-by-step checklist. No sticky sessions are needed;
all API servers share one database and one storage folder.

## Installing on another server (Windows, Linux) with no internet

Don't copy this working folder: about 650 of its ~670 MB are this Mac's Python environment (`venv`) and the
UI build tools (`frontend/node_modules`), plus your own documents and databases in `backend/storage`.
Build a clean package instead, on a machine with internet:

```bash
build/mac-linux/make-package.sh windows 3.12      # Windows, Python 3.12, SQL Server driver included
```

It creates `../IDP_dist/IDP-<version>-windows/` and a `.zip` (~160 MB, almost all of it the Windows
Python packages for an offline install). Copy that to the server, install Python 3.12 (and the Microsoft Visual
C++ Redistributable x64 if missing), then run `build\windows\install.bat` and `build\windows\start.bat`.
Targets: `windows`, `linux`, `mac-arm`, `mac-intel`; see `/docs` section 11.1.

## Docker / NAS (UGREEN, Synology, any Linux Docker host)

Two containers: Nginx (HTTPS, the web UI, forwards `/api`, `/docs`) and the API (Python 3.12). Build the images
on a machine with Docker and internet, then copy one folder to the NAS:

```bash
build/docker/make-bundle.sh            # linux/amd64 (Intel NAS); linux/arm64 for ARM models
```

It creates `../IDP_dist/IDP-<version>-docker/` (images, `docker-compose.yml`, `.env.example`,
`INSTALL.txt`). On the NAS: `docker load -i docupulse-idp-images.tar.gz`, `cp .env.example .env`,
`docker compose up -d`, then open `https://<nas>:7443`. Config, documents, database, keys and certificates
stay in `data/` next to the compose file. Full guide: `/docs` section 11.10.
For outside testers, an optional Cloudflare tunnel container (`docker compose --profile public up -d`, token in
`.env`) publishes it on a hostname without opening router ports; see `/docs` 11.10 "Public access for testing".

## Settings

Feature flag: the Instant Demo (sample contract, US passport and invoice buttons) appears only with
`demo_presets = true` under `[features]` in `backend/config/server.ini` (off by default).

All settings are in `backend/config/server.ini` and `backend/config/database.ini` (each created from
its `.example` on first start), plus `frontend/dist/config.js` for the UI. Environment variables
override the files; the full reference is in `/docs`, section 12.

## Licences

IDP is released under the [MIT License](LICENSE). Every dependency is open source; see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)
(regenerate with `venv/bin/python build/tools/third_party_licenses.py`).

## Notes

- Every request needs a sign-in session or an API key; anonymous requests are refused (except `/api/health`
  and the sign-in endpoints). Run it behind HTTPS (see `/docs`, 11.6) in production.
- Numeric dates like `05/10/2026` are read month-first (US style).
