import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';
import { Check, Copy, ExternalLink } from 'lucide';
import { apiUrl, copyText, serverOrigin } from '../core/api';
import { Icon } from '../core/icon';

const buildSnippets = (base: string) => ({
  upload_curl: {
    title: 'Upload & Process Document (cURL)',
    lang: 'bash',
    code: `curl -X POST "${base}/api/v1/documents/upload" \\
  -H "X-API-Key: dp_live_YOUR_API_KEY" \\
  -F "file=@./any_document.pdf" \\
  -F "doc_type=auto" \\
  -F "sync=true"`,
  },
  python_sdk: {
    title: 'Document Ingestion (Python Requests)',
    lang: 'python',
    code: `import requests

url = "${base}/api/v1/documents/upload"
headers = {"X-API-Key": "dp_live_YOUR_API_KEY"}

with open("passport_kyc.pdf", "rb") as f:
    files = {"file": f}
    data = {"doc_type": "identity", "sync": "true"}
    response = requests.post(url, headers=headers, files=files, data=data)

result = response.json()
print("Document Status:", result["status"])
print("Overall Confidence:", result["overall_confidence"])
print("Extracted Name:", result["fields"]["full_name"]["value"])
print("MRZ Checksum:", result["fields"]["mrz_checksum_valid"]["value"])`,
  },
  get_doc_curl: {
    title: 'Fetch Extracted Fields & Coordinates (cURL)',
    lang: 'bash',
    code: `curl -X GET "${base}/api/v1/documents/doc_sample_contract_init" \\
  -H "X-API-Key: dp_live_YOUR_API_KEY"`,
  },
  hitl_update_curl: {
    title: 'Programmatic Human-in-the-Loop Field Update (cURL)',
    lang: 'bash',
    code: `curl -X PATCH "${base}/api/v1/documents/doc_sample_contract_init/fields" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: dp_live_YOUR_API_KEY" \\
  -d '{
    "fields": [
      {"field_name": "liability_cap", "value": "$5,000,000 USD"}
    ],
    "actor": "Lead Legal Counsel"
  }'`,
  },
  schema_create: {
    title: 'Create Custom Schema Dynamically (cURL)',
    lang: 'bash',
    code: `curl -X POST "${base}/api/v1/schemas" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: dp_live_YOUR_API_KEY" \\
  -d '{
    "name": "Custom Logistics Waybill",
    "document_type_code": "waybills",
    "description": "Freight & Bill of Lading extraction",
    "fields": [
      {"name": "tracking_num", "label": "Tracking Code", "data_type": "text", "required": true},
      {"name": "gross_weight", "label": "Gross Weight (KG)", "data_type": "number", "required": false}
    ]
  }'`,
  },
});

const ENDPOINTS = [
  { method: 'POST', badge: 'badge-approved post', path: '/api/v1/documents/upload', scope: 'doc:write',
    text: 'Upload document file, classify document type, and execute extraction pipeline' },
  { method: 'GET', badge: 'badge-queued', path: '/api/v1/documents', scope: 'doc:read',
    text: 'List your documents, with type, status, search and folder filters (folder=<id> or root)' },
  { method: 'GET', badge: 'badge-queued', path: '/api/v1/documents/{id}', scope: 'doc:read',
    text: 'Get extracted fields, coordinate bounding boxes, and audit history' },
  { method: 'PATCH', badge: 'badge-needs_review', path: '/api/v1/documents/{id}/fields', scope: 'doc:write',
    text: 'Human-in-the-Loop review: update fields and mark verified' },
  { method: 'POST', badge: 'badge-approved', path: '/api/v1/documents/{id}/approve', scope: 'doc:write',
    text: 'Approve document and trigger downstream webhook dispatches' },
  { method: 'GET', badge: 'badge-queued', path: '/api/v1/folders', scope: 'doc:read',
    text: 'List your folders (the whole tree), with document counts and favourites' },
  { method: 'POST', badge: 'badge-approved', path: '/api/v1/folders', scope: 'doc:write',
    text: 'Create a folder (name, optional parent_id); upload into it with folder_id' },
  { method: 'POST', badge: 'badge-approved', path: '/api/v1/documents/move', scope: 'doc:write',
    text: 'Move documents into a folder, or to the top level' },
  { method: 'GET', badge: 'badge-queued', path: '/api/v1/documents/{id}/export/xlsx', scope: 'doc:read',
    text: 'Download fields and tables as Excel (also /export/csv and /export/json)' },
  { method: 'POST', badge: 'badge-approved', path: '/api/v1/schemas', scope: 'schema:manage',
    text: 'Dynamically register new custom document schema and extraction rules' },
];

@Component({
  selector: 'app-api-console',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
    .banner { padding: 24px; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    .banner h2 { font-size: 1.2rem; font-weight: 700; }
    .banner p { color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px; }
    .banner .btn { flex-shrink: 0; }
    .flush { padding: 0; min-width: 0; }
    .tabs { padding: 16px 20px; border-bottom: 1px solid var(--border-color); display: flex; gap: 8px; overflow-x: auto; }
    .tabs .btn { flex-shrink: 0; }
    .code-view { padding: 20px; }
    .code-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
    .code-title { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
    .code-box { padding: 18px; font-size: 0.82rem; line-height: 1.6; }
    .section-head { padding: 16px 20px; border-bottom: 1px solid var(--border-color); }
    .section-head h3 { font-size: 1rem; font-weight: 700; }
    .post { background: color-mix(in srgb, var(--success) 20%, transparent); }
    .path { font-family: var(--font-mono); color: var(--accent-text); overflow-wrap: anywhere; }
    .cell-label { display: none; }

    @media (max-width: 640px) {
      .banner { flex-direction: column; align-items: stretch; padding: 16px; }
      .tabs { padding: 12px; }
      .code-view { padding: 12px; }
      .code-box { padding: 12px; font-size: 0.75rem; }
      .section-head { padding: 12px; }
      /* Phones: each endpoint becomes a stacked card instead of a wide table row */
      .data-table thead { display: none; }
      .data-table, .data-table tbody, .data-table tr, .data-table td { display: block; width: 100%; }
      .data-table tr { border-bottom: 1px solid var(--border-color); padding: 8px 0; }
      .data-table td { border-bottom: none; padding: 4px 12px; }
      .cell-label { display: inline-block; font-size: 0.7rem; color: var(--text-muted); margin-right: 6px; }
    }
  `,
  template: `
    <!-- Top Banner -->
    <div class="glass-card banner">
      <div>
        <h2>Developer API Explorer &amp; SDKs</h2>
        <p>Every capability of DocuPulse IDP is exposed via high-performance REST endpoints with OpenAPI v3 specification.</p>
      </div>
      <a [href]="docsUrl" target="_blank" rel="noreferrer" class="btn btn-primary">
        <app-icon [icon]="ExternalLink" [size]="16" />
        <span>Launch Interactive Swagger UI</span>
      </a>
    </div>

    <!-- Code Snippets Section -->
    <div class="glass-card flush">
      <!-- Navigation tabs -->
      <div class="tabs" role="tablist">
        @for (k of snippetKeys; track k) {
          <button class="btn btn-sm" [class.btn-primary]="selectedSnippet() === k" [class.btn-secondary]="selectedSnippet() !== k"
            role="tab" [attr.aria-selected]="selectedSnippet() === k" (click)="selectedSnippet.set(k)">
            <span>{{ snippets[k].title.split('(')[0] }}</span>
          </button>
        }
      </div>

      <!-- Code View -->
      <div class="code-view">
        <div class="code-head">
          <span class="code-title">{{ activeSnippet().title }}</span>
          <button class="btn btn-secondary btn-sm" (click)="copyCode(activeSnippet().code)">
            <app-icon [icon]="copied() ? Check : Copy" [size]="14" />
            <span>{{ copied() ? 'Copied!' : 'Copy Code' }}</span>
          </button>
        </div>
        <pre class="code-box"><code>{{ activeSnippet().code }}</code></pre>
      </div>
    </div>

    <!-- REST API Endpoints Quick Reference Table -->
    <div class="glass-card flush">
      <div class="section-head"><h3>Core API Endpoints Overview</h3></div>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>HTTP Method</th>
              <th>Endpoint Path</th>
              <th>Required Scope</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            @for (e of endpoints; track e.path + e.method) {
              <tr>
                <td><span [class]="'badge ' + e.badge">{{ e.method }}</span></td>
                <td><code class="path">{{ e.path }}</code></td>
                <td><span class="cell-label">Scope</span><span class="type-pill">{{ e.scope }}</span></td>
                <td>{{ e.text }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class ApiConsole {
  protected readonly Check = Check; protected readonly Copy = Copy; protected readonly ExternalLink = ExternalLink;

  protected readonly docsUrl = apiUrl('/docs');
  protected readonly snippets: Record<string, { title: string; lang: string; code: string }> = buildSnippets(serverOrigin());
  protected readonly snippetKeys = Object.keys(this.snippets);
  protected readonly endpoints = ENDPOINTS;
  protected readonly selectedSnippet = signal('upload_curl');
  protected readonly copied = signal(false);
  protected readonly activeSnippet = computed(() => this.snippets[this.selectedSnippet()]);

  copyCode(text: string) {
    copyText(text);
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 2500);
  }
}
