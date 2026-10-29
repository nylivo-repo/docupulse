import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AlertCircle, Check, Pencil, Plug, Plus, Trash2 } from 'lucide';
import { api, serverOrigin } from '../core/api';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

// Built-in templates that cannot be deleted
const BUILT_IN = ['schema-contract-std', 'schema-identity-std', 'schema-invoice-std'];

const defaultFields = () => [
  { name: 'document_id', label: 'Reference / Doc ID', data_type: 'text', required: true, regex_pattern: '', confidence_threshold: 0.8 },
  { name: 'issue_date', label: 'Issue Date', data_type: 'date', required: true, regex_pattern: '', confidence_threshold: 0.75 },
  { name: 'amount', label: 'Total Value', data_type: 'currency', required: false, regex_pattern: '', confidence_threshold: 0.75 },
] as any[];

// Field names that usually hold personal data: suggested as sensitive when picked as a search key
const SENSITIVE_HINT = /(ssn|social|tax|tin\b|passport_?(no|num)|national|birth|dob|account|card|licen[cs]e)/i;
// Lookup endpoint names, as the server checks them
const ENDPOINT_RE = /^[A-Za-z][A-Za-z0-9_]{2,63}$/;

// "US Passport Details" → getUsPassportDetails
const suggestEndpoint = (name: string) => {
  const words = name.match(/[A-Za-z0-9]+/g) || [];
  return words.length ? 'get' + words.map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase()).join('') : '';
};
// last_name → lastName, the query parameter name external apps use
const camel = (name: string) => name.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());

@Component({
  selector: 'app-schema-builder',
  imports: [FormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
    .success { background: color-mix(in srgb, var(--success) 15%, transparent); border: 1px solid color-mix(in srgb, var(--success) 40%, transparent); color: var(--success-text); padding: 12px 20px;
      border-radius: var(--radius-md); display: flex; align-items: center; gap: 8px; font-weight: 600; }
    .banner { padding: 24px; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    .banner h2 { font-size: 1.2rem; font-weight: 700; }
    .banner p { color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px; }
    .banner .btn { flex-shrink: 0; }
    form { padding: 28px; min-width: 0; }
    h3 { font-size: 1.05rem; font-weight: 700; margin-bottom: 16px; }
    .error { padding: 10px 14px; border-radius: var(--radius-sm); background: color-mix(in srgb, var(--danger) 15%, transparent); border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent);
      color: var(--danger-text); font-size: 0.8rem; display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 16px; }
    .lbl { display: block; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
    .desc { margin-bottom: 24px; }
    .fields-box { border-top: 1px solid var(--border-color); padding-top: 20px; margin-bottom: 20px; }
    .fields-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
    .fields-head h4 { font-size: 0.95rem; font-weight: 600; }
    .field-list { display: flex; flex-direction: column; gap: 12px; }
    .field-row { padding: 16px; border-radius: var(--radius-md); background: color-mix(in srgb, var(--tint) 2%, transparent); border: 1px solid var(--border-color);
      display: grid; grid-template-columns: 1.1fr 1.1fr 1.3fr 0.9fr 1.3fr 60px 40px; gap: 12px; align-items: center; }
    .field-row > div { min-width: 0; }
    .flbl { font-size: 0.72rem; color: var(--text-muted); display: block; margin-bottom: 4px; }
    .field-row .field-input { font-size: 0.8rem; padding: 6px 8px; }
    .field-row .mono { font-family: var(--font-mono); }
    .req { text-align: center; }
    .req input { cursor: pointer; transform: scale(1.2); }
    .remove { text-align: right; }
    .remove .btn { padding: 6px; color: var(--danger); }
    .actions { display: flex; justify-content: flex-end; gap: 12px; flex-wrap: wrap; }
    .api-box { border-top: 1px solid var(--border-color); padding-top: 20px; margin-bottom: 20px; display: flex; flex-direction: column; gap: 14px; }
    .api-box h4 { font-size: 0.95rem; font-weight: 600; display: flex; align-items: center; gap: 8px; }
    .api-box .hint { font-size: 0.78rem; color: var(--text-secondary); }
    .switch { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; width: fit-content; }
    .switch input { transform: scale(1.2); cursor: pointer; }
    .ep-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: 16px; align-items: start; }
    .ep-msg { font-size: 0.75rem; margin-top: 4px; color: var(--text-muted); }
    .ep-msg.bad { color: var(--danger-text); }
    .ep-url { font-family: var(--font-mono); font-size: 0.75rem; color: var(--accent-text); overflow-wrap: anywhere; padding: 8px 10px;
      border-radius: var(--radius-sm); background: color-mix(in srgb, var(--tint) 4%, transparent); border: 1px solid var(--border-color); }
    .keys { border: 1px solid var(--border-color); border-radius: var(--radius-md); overflow: hidden; }
    .key-row { display: grid; grid-template-columns: minmax(0, 1fr) 110px 110px; gap: 8px; align-items: center; padding: 8px 14px; font-size: 0.82rem; }
    .key-row + .key-row { border-top: 1px solid var(--border-color); }
    .key-row.head { font-size: 0.72rem; font-weight: 600; color: var(--text-muted); background: color-mix(in srgb, var(--tint) 3%, transparent); }
    .key-row label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
    .key-row .param { font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted); margin-left: 6px; }
    .key-row .fixed { color: var(--text-muted); font-size: 0.75rem; }
    .api-pill { color: var(--success-text); }
    .schema-actions { display: flex; gap: 6px; flex-shrink: 0; }
    .schemas { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(380px, 100%), 1fr)); gap: 20px; }
    .schema { padding: 24px; display: flex; flex-direction: column; gap: 16px; min-width: 0; }
    .schema-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
    .schema-head > div { min-width: 0; }
    .code { color: var(--accent-cyan); }
    .schema h3 { margin: 6px 0 0; overflow-wrap: anywhere; }
    .schema-desc { font-size: 0.78rem; color: var(--text-secondary); margin-top: 4px; }
    .del { color: var(--danger); }
    .configured { border-top: 1px solid var(--border-color); padding-top: 12px; }
    .configured-title { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip { font-size: 0.72rem; padding: 3px 8px; border-radius: 4px; background: color-mix(in srgb, var(--tint) 4%, transparent); border: 1px solid var(--border-color); color: var(--text-secondary); }
    .star { color: var(--accent-cyan); }
    .more { font-size: 0.72rem; color: var(--text-muted); align-self: center; }
    .schema-foot { margin-top: auto; border-top: 1px solid var(--border-color); padding-top: 12px; display: flex; justify-content: space-between;
      gap: 8px; flex-wrap: wrap; font-size: 0.75rem; color: var(--text-muted); }

    /* Field rows: 7 columns on wide screens, a compact grid on tablets, one column on phones */
    @media (max-width: 1100px) {
      .field-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .req, .remove { text-align: left; }
      .req { display: flex; align-items: center; gap: 8px; }
      .req .flbl { margin: 0; }
    }
    @media (max-width: 640px) {
      .ep-row { grid-template-columns: 1fr; }
      .key-row { grid-template-columns: minmax(0, 1fr) 84px 84px; padding: 8px 10px; }
      .banner { flex-direction: column; align-items: stretch; padding: 16px; }
      form { padding: 16px; }
      .schema { padding: 16px; }
      .field-row { grid-template-columns: 1fr; padding: 12px; }
      .remove .btn { width: 100%; justify-content: center; }
    }
  `,
  template: `
    @if (successMsg()) {
      <div class="success">
        <app-icon [icon]="Check" [size]="18" />
        <span>{{ successMsg() }}</span>
      </div>
    }

    <!-- Top Banner -->
    <div class="glass-card banner">
      <div>
        <h2>Custom Document Extraction Schemas</h2>
        <p>
          Templates tell the extractor which fields a document type has: labels and other names they appear under, types, optional regex and thresholds.
          Uploads set to Auto-detect pick the matching template. Tip: open any document in Review and click "Save as Template" to build one from it.
        </p>
      </div>
      <button class="btn btn-primary" (click)="isCreating() ? closeBuilder() : startNew()">
        <app-icon [icon]="Plus" [size]="16" />
        <span>{{ isCreating() ? 'Close Builder' : 'New Custom Schema' }}</span>
      </button>
    </div>

    <!-- Creation Form -->
    @if (isCreating()) {
      <form ngNativeValidate (ngSubmit)="handleSubmit()" class="glass-card">
        <h3>{{ editingId() ? 'Edit Template' : 'Define New Extraction Schema' }}</h3>

        @if (errorMsg()) {
          <div class="error">
            <app-icon [icon]="AlertCircle" [size]="16" />
            <span>{{ errorMsg() }}</span>
          </div>
        }

        <div class="form-grid">
          <div>
            <label class="lbl" for="sb-name">Schema Title *</label>
            <input id="sb-name" name="name" type="text" placeholder="e.g., Logistics Bill of Lading" [(ngModel)]="name"
              (ngModelChange)="nameChanged()" class="field-input" required />
          </div>
          <div>
            <label class="lbl" for="sb-code">Type Code (API Slug) *</label>
            <input id="sb-code" name="docTypeCode" type="text" placeholder="e.g., bill_of_lading" [(ngModel)]="docTypeCode" class="field-input"
              required [disabled]="!!editingId()" [title]="editingId() ? 'The type code of an existing template cannot change' : ''" />
          </div>
        </div>

        <div class="desc">
          <label class="lbl" for="sb-desc">Description</label>
          <input id="sb-desc" name="description" type="text" placeholder="e.g., Extraction rules for maritime cargo transport manifests"
            [(ngModel)]="description" class="field-input" />
        </div>

        <!-- Fields List -->
        <div class="fields-box">
          <div class="fields-head">
            <h4>Schema Field Definitions ({{ fields().length }})</h4>
            <button type="button" class="btn btn-secondary btn-sm" (click)="addField()">
              <app-icon [icon]="Plus" [size]="14" />
              <span>Add Field</span>
            </button>
          </div>

          <div class="field-list">
            @for (f of fields(); track f; let idx = $index) {
              <div class="field-row">
                <div>
                  <label class="flbl" [for]="'f-name-' + idx">Key Name</label>
                  <input [id]="'f-name-' + idx" [name]="'f-name-' + idx" type="text" [(ngModel)]="f.name" class="field-input" />
                </div>
                <div>
                  <label class="flbl" [for]="'f-label-' + idx">Display Label</label>
                  <input [id]="'f-label-' + idx" [name]="'f-label-' + idx" type="text" [(ngModel)]="f.label" class="field-input" />
                </div>
                <div>
                  <label class="flbl" [for]="'f-alias-' + idx">Other labels it appears as</label>
                  <input [id]="'f-alias-' + idx" [name]="'f-alias-' + idx" type="text" placeholder="e.g. Ref No, Reference #"
                    [ngModel]="f.aliases || ''" (ngModelChange)="f.aliases = $event" class="field-input"
                    title="Comma-separated alternative labels used in different documents" />
                </div>
                <div>
                  <label class="flbl" [for]="'f-type-' + idx">Data Type</label>
                  <select [id]="'f-type-' + idx" [name]="'f-type-' + idx" [(ngModel)]="f.data_type" class="field-input">
                    <option value="text">Text (String)</option>
                    <option value="date">Date</option>
                    <option value="currency">Currency / Price</option>
                    <option value="number">Numeric</option>
                    <option value="regex">Regex Match</option>
                    <option value="enum">Enum Choices</option>
                  </select>
                </div>
                <div>
                  <label class="flbl" [for]="'f-pat-' + idx">{{ f.data_type === 'enum' ? 'Choices (comma-separated)' : 'Regex / Pattern (optional)' }}</label>
                  <input [id]="'f-pat-' + idx" [name]="'f-pat-' + idx" type="text" class="field-input mono"
                    [placeholder]="f.data_type === 'enum' ? 'OPTION_A, OPTION_B' : patternPlaceholder"
                    [ngModel]="f.data_type === 'enum' ? f.enum_values || '' : f.regex_pattern || ''"
                    (ngModelChange)="setPattern(f, $event)" />
                </div>
                <div class="req">
                  <label class="flbl" [for]="'f-req-' + idx">Req?</label>
                  <input [id]="'f-req-' + idx" type="checkbox" [checked]="f.required" (change)="f.required = $any($event.target).checked" />
                </div>
                <div class="remove">
                  <button type="button" class="btn btn-secondary btn-sm" (click)="removeField(idx)" title="Remove Field" aria-label="Remove Field">
                    <app-icon [icon]="Trash2" [size]="15" />
                  </button>
                </div>
              </div>
            }
          </div>
        </div>

        <!-- Lookup API: other applications find documents of this template and read their fields -->
        <div class="api-box">
          <h4><app-icon [icon]="Plug" [size]="16" /> API</h4>
          <p class="hint">
            Publish a lookup endpoint so other applications can find approved documents of this template and read their fields as JSON.
            Lookup by document ID is always available; tick the fields that can also be searched on.
          </p>
          <label class="switch">
            <input type="checkbox" name="apiEnabled" [checked]="apiEnabled" (change)="toggleApi($any($event.target).checked)" />
            <span>Publish a lookup endpoint</span>
          </label>
          @if (apiEnabled) {
            <div class="ep-row">
              <div>
                <label class="lbl" for="sb-endpoint">Endpoint name *</label>
                <input id="sb-endpoint" name="apiEndpoint" type="text" class="field-input mono" placeholder="getPassportDetails"
                  [(ngModel)]="apiEndpoint" (ngModelChange)="endpointTouched = true" autocomplete="off" />
                <div class="ep-msg" [class.bad]="!!endpointError()">{{ endpointError() || 'Unique across templates; letters, digits and _' }}</div>
              </div>
              <div>
                <span class="lbl">Example call</span>
                <div class="ep-url">GET {{ exampleUrl() }}</div>
              </div>
            </div>
            <div class="keys" role="table" aria-label="Search keys">
              <div class="key-row head" role="row"><span>Field</span><span>Search key</span><span>Sensitive</span></div>
              <div class="key-row" role="row">
                <span>Document ID <span class="param">documentId</span></span>
                <span class="fixed">Always</span><span></span>
              </div>
              @for (f of fields(); track f; let idx = $index) {
                <div class="key-row" role="row">
                  <span>{{ f.label || f.name }} <span class="param">{{ paramName(f) }}</span></span>
                  @if (reserved(f)) {
                    <span class="fixed" title="documentId, limit and offset are lookup parameters already; rename the key to search on it">Reserved name</span>
                  } @else {
                    <label><input type="checkbox" [checked]="!!f.api_search" (change)="setSearch(f, $any($event.target).checked)" /> Search</label>
                  }
                  <label title="Personal data (SSN, date of birth…): masked in results unless the key has pii:read, and searchable only in a POST body">
                    <input type="checkbox" [checked]="!!f.sensitive" (change)="f.sensitive = $any($event.target).checked" /> Sensitive</label>
                </div>
              }
            </div>
            <p class="hint">
              Callers need an API key with the scope <code>lookup:{{ apiEndpoint || '…' }}</code> (API Keys page). A key sees only its creator's
              approved documents. Sensitive fields come back masked unless the key also has <code>pii:read</code>.
            </p>
          }
        </div>

        <div class="actions">
          <button type="button" class="btn btn-secondary" (click)="closeBuilder()">Cancel</button>
          <button type="submit" class="btn btn-primary" [disabled]="saving()">
            {{ saving() ? 'Saving...' : editingId() ? 'Save Changes' : 'Save & Activate Schema' }}
          </button>
        </div>
      </form>
    }

    <!-- Existing Schemas Grid -->
    <div class="schemas">
      @for (s of store.schemas(); track s.id) {
        <div class="glass-card schema">
          <div class="schema-head">
            <div>
              <span class="type-pill code">{{ s.document_type_code }}</span>
              @if (s.api_enabled && s.api_endpoint) { <span class="type-pill api-pill" title="Lookup endpoint">API: {{ s.api_endpoint }}</span> }
              <h3>{{ s.name }}</h3>
              <p class="schema-desc">{{ s.description || 'No description provided' }}</p>
            </div>
            <div class="schema-actions">
              <button class="btn btn-secondary btn-sm" (click)="startEdit(s)" title="Edit template" aria-label="Edit template">
                <app-icon [icon]="Pencil" [size]="14" />
              </button>
              @if (!builtIn.includes(s.id)) {
                <button class="btn btn-secondary btn-sm del" (click)="handleDelete(s.id)" title="Delete Schema" aria-label="Delete Schema">
                  <app-icon [icon]="Trash2" [size]="14" />
                </button>
              }
            </div>
          </div>

          <div class="configured">
            <div class="configured-title">CONFIGURED FIELDS ({{ s.fields?.length || 0 }})</div>
            <div class="chips">
              @for (f of (s.fields || []).slice(0, 8); track $index) {
                <span class="chip">{{ f.label }} @if (f.required) { <span class="star">*</span> }</span>
              }
              @if ((s.fields?.length || 0) > 8) {
                <span class="more">+{{ (s.fields?.length || 0) - 8 }} more</span>
              }
            </div>
          </div>

          <div class="schema-foot">
            <span>{{ s.documents_count || 0 }} Ingested Docs</span>
            <span>Updated {{ dateStr(s.updated_at) }}</span>
          </div>
        </div>
      }
    </div>
  `,
})
export class SchemaBuilder {
  protected readonly Plus = Plus; protected readonly Trash2 = Trash2;
  protected readonly Pencil = Pencil; protected readonly Plug = Plug;
  protected readonly Check = Check; protected readonly AlertCircle = AlertCircle;

  protected readonly store = inject(Store);
  protected readonly builtIn = BUILT_IN;
  protected readonly patternPlaceholder = '([A-Z]{3}-\\d+)';
  protected readonly isCreating = signal(false);
  protected name = '';
  protected docTypeCode = '';
  protected description = '';
  // Each field object is edited in place by the form
  protected readonly fields = signal<any[]>(defaultFields());
  protected readonly saving = signal(false);
  protected readonly errorMsg = signal<string | null>(null);
  protected readonly successMsg = signal<string | null>(null);
  // Template being edited (null: creating a new one)
  protected readonly editingId = signal<string | null>(null);
  protected apiEnabled = false;
  protected apiEndpoint = '';
  protected endpointTouched = false;

  paramName(f: any) {
    return camel(String(f.name || '').trim().toLowerCase().replace(/[\s\-]+/g, '_'));
  }

  // A field whose parameter would clash with the lookup's own (documentId, limit, offset) cannot be a search key
  reserved(f: any) {
    return ['documentid', 'limit', 'offset'].includes(this.paramName(f).toLowerCase());
  }

  // Empty when the name is fine; checked again by the server
  endpointError() {
    const name = this.apiEndpoint.trim();
    if (!name) return 'Give the endpoint a name.';
    if (!ENDPOINT_RE.test(name)) return 'Start with a letter; letters, digits and _ only (3–64 characters).';
    const taken = this.store.schemas().find((s) => s.id !== this.editingId() && s.api_endpoint?.toLowerCase() === name.toLowerCase());
    return taken ? `Already used by "${taken.name}".` : '';
  }

  exampleUrl() {
    const keys = this.fields().filter((f) => f.api_search && !f.sensitive).slice(0, 2);
    const query = keys.length ? keys.map((f) => `${this.paramName(f)}=…`).join('&') : 'documentId=doc_…';
    return `${serverOrigin()}/api/v1/lookup/${this.apiEndpoint.trim() || '…'}?${query}`;
  }

  // The endpoint name follows the template name until someone types their own
  nameChanged() {
    if (this.endpointTouched) return;
    let base = suggestEndpoint(this.name), candidate = base, n = 2;
    const used = new Set(this.store.schemas().filter((s) => s.id !== this.editingId()).map((s) => s.api_endpoint?.toLowerCase()));
    while (candidate && used.has(candidate.toLowerCase())) candidate = `${base}${n++}`;
    this.apiEndpoint = candidate;
  }

  toggleApi(on: boolean) {
    this.apiEnabled = on;
    if (on && !this.apiEndpoint) this.nameChanged();
  }

  setSearch(f: any, on: boolean) {
    f.api_search = on;
    if (on && f.sensitive === undefined && SENSITIVE_HINT.test(`${f.name} ${f.label}`)) f.sensitive = true;
  }

  private resetForm() {
    this.name = '';
    this.docTypeCode = '';
    this.description = '';
    this.apiEnabled = false;
    this.apiEndpoint = '';
    this.endpointTouched = false;
    this.errorMsg.set(null);
  }

  startNew() {
    this.resetForm();
    this.editingId.set(null);
    this.fields.set(defaultFields());
    this.isCreating.set(true);
  }

  startEdit(s: any) {
    this.resetForm();
    this.editingId.set(s.id);
    this.name = s.name;
    this.docTypeCode = s.document_type_code;
    this.description = s.description || '';
    this.apiEnabled = !!s.api_enabled;
    this.apiEndpoint = s.api_endpoint || '';
    this.endpointTouched = !!s.api_endpoint;
    // Lists are edited as comma-separated text; everything else (regions, locate…) is kept as it is
    this.fields.set((s.fields || []).map((f: any) => ({
      ...f,
      aliases: (f.aliases || []).join(', '),
      enum_values: (f.enum_values || []).join(', '),
      regex_pattern: f.regex_pattern || '',
    })));
    this.isCreating.set(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  closeBuilder() {
    this.isCreating.set(false);
    this.editingId.set(null);
  }

  dateStr(d: string) {
    return new Date(d).toLocaleDateString();
  }

  addField() {
    this.fields.update((fields) => [
      ...fields,
      {
        name: `field_${fields.length + 1}`,
        label: `Custom Field ${fields.length + 1}`,
        data_type: 'text',
        required: false,
        regex_pattern: '',
        confidence_threshold: 0.75,
        enum_values: '',
      },
    ]);
  }

  setPattern(f: any, value: string) {
    if (f.data_type === 'enum') f.enum_values = value;
    else f.regex_pattern = value;
  }

  removeField(index: number) {
    this.fields.update((fields) => fields.filter((_, i) => i !== index));
  }

  async handleSubmit() {
    if (!this.name || !this.docTypeCode) {
      this.errorMsg.set('Please specify Schema Name and Document Type Code.');
      return;
    }
    if (this.fields().length === 0) {
      this.errorMsg.set('At least one field definition is required.');
      return;
    }

    this.saving.set(true);
    this.errorMsg.set(null);

    try {
      if (this.apiEnabled && this.endpointError()) {
        this.errorMsg.set(`API endpoint: ${this.endpointError()}`);
        return;
      }
      const formattedFields = this.fields().map((f) => ({
        ...f,
        name: f.name.trim().toLowerCase().replace(/[\s\-]+/g, '_'),
        label: f.label.trim(),
        data_type: f.data_type,
        required: f.required,
        regex_pattern: f.regex_pattern ? f.regex_pattern.trim() : null,
        confidence_threshold: parseFloat(f.confidence_threshold) || 0.75,
        enum_values: f.enum_values ? f.enum_values.split(',').map((x: string) => x.trim()).filter(Boolean) : null,
        aliases: f.aliases ? f.aliases.split(',').map((x: string) => x.trim()).filter(Boolean) : null,
        api_search: !!f.api_search && !this.reserved(f),
        sensitive: !!f.sensitive,
      }));

      const name = this.name;
      const payload = {
        name,
        document_type_code: this.docTypeCode.trim().toLowerCase().replace(/[\s\-]+/g, '_'),
        description: this.description,
        fields: formattedFields,
        api_enabled: this.apiEnabled,
        api_endpoint: this.apiEndpoint.trim() || null,
      };
      const id = this.editingId();
      if (id) {
        const updated = await api.updateSchema(id, payload);
        this.store.schemas.update((list) => list.map((x) => (x.id === id ? updated : x)));
        this.successMsg.set(`Template '${name}' saved.`);
      } else {
        this.store.schemaCreated(await api.createSchema(payload));
        this.successMsg.set(`Schema '${name}' created successfully!`);
      }
      this.closeBuilder();
      this.resetForm();
      setTimeout(() => this.successMsg.set(null), 3500);
    } catch (err: any) {
      this.errorMsg.set(err.message || 'Failed to create schema.');
    } finally {
      this.saving.set(false);
    }
  }

  async handleDelete(schemaId: string) {
    if (!confirm('Are you sure you want to deactivate this custom schema?')) return;
    try {
      await api.deleteSchema(schemaId);
      this.store.schemas.update((list) => list.filter((x) => x.id !== schemaId));
    } catch (err: any) {
      alert(`Delete error: ${err.message}`);
    }
  }
}
