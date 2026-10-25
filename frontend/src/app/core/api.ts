// Where the API server is: set in config.js next to index.html (editable after build, no rebuild needed).
// Empty means the API is on the same server as this page (single-server mode).
const API_ROOT = String(window.IDP_CONFIG?.apiBaseUrl || '').replace(/\/+$/, '');

// Full URL for an API path, for fetch calls and for links/images the browser loads directly
export const apiUrl = (path: string) => (path && path.startsWith('/') ? `${API_ROOT}${path}` : path);

// Every request goes to the configured API, with the sign-in cookie even when the UI is served from
// another host (the API must list this UI's origin in config/server.ini [cors])
const call = (url: string, opts: RequestInit = {}) => window.fetch(apiUrl(url), { credentials: 'include', ...opts });

const API_BASE = '/api/v1';

async function handle(res: Response): Promise<any> {
  if (res.status === 401) {
    // Session expired or signed out elsewhere: the app shows the login page
    window.dispatchEvent(new Event('idp:unauthorized'));
  }
  if (!res.ok) {
    let message = 'API Request Failed';
    try {
      const data = await res.json();
      message = typeof data.detail === 'string' ? data.detail : data.message || JSON.stringify(data.detail ?? data);
      // Validation errors list the fields; a server error carries a reference for the administrator
      if (Array.isArray(data.errors) && data.errors.length) {
        message += ' ' + data.errors.map((e: any) => `${e.field}: ${e.problem}`).join('; ');
      }
      if (res.status >= 500 && data.request_id) message += ` (reference ${data.request_id})`;
    } catch {
      message = res.statusText || message;
    }
    throw new Error(message);
  }
  if (res.status === 204) return null;
  return res.json();
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});
const get = async (url: string) => handle(await call(url));
const send = async (url: string, method: string, body?: unknown) =>
  handle(await call(url, body === undefined ? { method } : json(method, body)));
const q = encodeURIComponent;

export const auth = {
  config: () => get('/api/auth/config'),
  me: async () => {
    const res = await call('/api/auth/me');
    if (res.status === 401) return null;
    return handle(res);
  },
  login: (username: string, password: string) => send('/api/auth/login', 'POST', { username, password }),
  logout: () => send('/api/auth/logout', 'POST'),
  changePassword: (current_password: string, new_password: string) =>
    send('/api/auth/change-password', 'POST', { current_password, new_password }),
};

export const admin = {
  getAuthSettings: () => get(`${API_BASE}/admin/settings/auth`),
  saveAuthSettings: (s: unknown) => send(`${API_BASE}/admin/settings/auth`, 'PUT', s),
  testLdap: (body: unknown) => send(`${API_BASE}/admin/settings/auth/test-ldap`, 'POST', body),
  testOkta: (okta: unknown) => send(`${API_BASE}/admin/settings/auth/test-okta`, 'POST', okta),
  listUsers: () => get(`${API_BASE}/admin/users`),
  createUser: (u: unknown) => send(`${API_BASE}/admin/users`, 'POST', u),
  updateUser: (id: number | string, changes: unknown) => send(`${API_BASE}/admin/users/${id}`, 'PATCH', changes),
};

export const api = {
  getAnalytics: () => get(`${API_BASE}/analytics`),

  // Documents
  getDocuments: ({ docType = 'all', status = 'all', search = '' } = {}) => {
    const params = new URLSearchParams();
    if (docType && docType !== 'all') params.append('doc_type', docType);
    if (status && status !== 'all') params.append('status', status);
    if (search) params.append('search', search);
    return get(`${API_BASE}/documents?${params.toString()}`);
  },
  getDocument: (id: string) => get(`${API_BASE}/documents/${id}`),
  uploadDocument: async ({ file, docType = 'auto', schemaId = null, sync = true, folderId = null }:
    { file: File; docType?: string; schemaId?: string | null; sync?: boolean; folderId?: string | null }) => {
    const form = new FormData();
    form.append('file', file);
    form.append('doc_type', docType);
    form.append('sync', sync ? 'true' : 'false');
    if (schemaId) form.append('schema_id', schemaId);
    if (folderId) form.append('folder_id', folderId);
    return handle(await call(`${API_BASE}/documents/upload`, { method: 'POST', body: form }));
  },
  runSamplePreset: (sampleType: string) => send(`${API_BASE}/documents/sample/${sampleType}`, 'POST'),
  updateFields: (id: string, fields: Record<string, unknown>) =>
    send(`${API_BASE}/documents/${id}/fields`, 'PATCH', { fields }),
  approveDocument: (id: string) => send(`${API_BASE}/documents/${id}/approve`, 'POST'),
  rejectDocument: (id: string, reason = 'Document failed quality checks') =>
    send(`${API_BASE}/documents/${id}/reject?reason=${q(reason)}`, 'POST'),
  deleteDocument: (id: string) => send(`${API_BASE}/documents/${id}`, 'DELETE'),
  deleteDocuments: (ids: string[]) => send(`${API_BASE}/documents/bulk-delete`, 'POST', { ids }),
  reprocessDocument: (id: string, { docType = 'auto', schemaId = null }: { docType?: string; schemaId?: string | null } = {}) =>
    send(`${API_BASE}/documents/${id}/reprocess`, 'POST', { doc_type: docType, schema_id: schemaId }),
  addField: (id: string, { label = null, dataType = null, value = null, region = null }:
    { label?: string | null; dataType?: string | null; value?: string | null; region?: unknown }) =>
    send(`${API_BASE}/documents/${id}/fields`, 'POST', { label, data_type: dataType, value, region }),
  renameField: (id: string, fieldName: string, displayName: string) =>
    send(`${API_BASE}/documents/${id}/fields/${q(fieldName)}/label`, 'PATCH', { display_name: displayName }),
  removeField: (id: string, fieldName: string) => send(`${API_BASE}/documents/${id}/fields/${q(fieldName)}`, 'DELETE'),

  moveDocuments: (ids: string[], folderId: string | null) => send(`${API_BASE}/documents/move`, 'POST', { ids, folder_id: folderId }),

  // Folders (each person's own)
  getFolders: () => get(`${API_BASE}/folders`),
  createFolder: (name: string, parentId: string | null) => send(`${API_BASE}/folders`, 'POST', { name, parent_id: parentId }),
  renameFolder: (id: string, name: string) => send(`${API_BASE}/folders/${id}`, 'PATCH', { name }),
  moveFolder: (id: string, parentId: string | null) =>
    send(`${API_BASE}/folders/${id}`, 'PATCH', parentId ? { parent_id: parentId } : { move_to_top: true }),
  deleteFolder: (id: string) => send(`${API_BASE}/folders/${id}`, 'DELETE'),
  favoriteFolder: (id: string, favorite: boolean) => send(`${API_BASE}/folders/${id}`, 'PATCH', { favorite }),

  // Templates (custom schemas)
  getSchemas: () => get(`${API_BASE}/schemas`),
  createSchema: (schema: unknown) => send(`${API_BASE}/schemas`, 'POST', schema),
  deleteSchema: (id: string) => send(`${API_BASE}/schemas/${id}`, 'DELETE'),
  createSchemaFromDocument: (docId: string, { name, documentTypeCode, fieldNames, useRegions = true }:
    { name: string; documentTypeCode: string; fieldNames: string[]; useRegions?: boolean }) =>
    send(`${API_BASE}/schemas/from-document/${docId}`, 'POST',
      { name, document_type_code: documentTypeCode, field_names: fieldNames, use_regions: useRegions }),

  // API keys
  getApiKeys: () => get(`${API_BASE}/keys`),
  createApiKey: (key: unknown) => send(`${API_BASE}/keys`, 'POST', key),
  revokeApiKey: (id: string) => send(`${API_BASE}/keys/${id}`, 'DELETE'),

  // Webhooks
  getWebhooks: () => get(`${API_BASE}/webhooks`),
  createWebhook: (hook: unknown) => send(`${API_BASE}/webhooks`, 'POST', hook),
  deleteWebhook: (id: string) => send(`${API_BASE}/webhooks/${id}`, 'DELETE'),
  testWebhook: (test: unknown) => send(`${API_BASE}/webhooks/test`, 'POST', test),
  getWebhookLogs: () => get(`${API_BASE}/webhooks/logs`),

};

// Base URL of the server as the browser sees it, for code samples and links (works from any intranet host)
export const serverOrigin = () => API_ROOT || window.location.origin;

// navigator.clipboard only exists on https or localhost; intranet http pages need the fallback
export function copyText(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
  } finally {
    document.body.removeChild(ta);
  }
  return Promise.resolve();
}
