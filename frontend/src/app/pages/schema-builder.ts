import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AlertCircle, Check, Plus, Trash2 } from 'lucide';
import { api } from '../core/api';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

// Built-in templates that cannot be deleted
const BUILT_IN = ['schema-contract-std', 'schema-identity-std', 'schema-invoice-std'];

const defaultFields = () => [
  { name: 'document_id', label: 'Reference / Doc ID', data_type: 'text', required: true, regex_pattern: '', confidence_threshold: 0.8 },
  { name: 'issue_date', label: 'Issue Date', data_type: 'date', required: true, regex_pattern: '', confidence_threshold: 0.75 },
  { name: 'amount', label: 'Total Value', data_type: 'currency', required: false, regex_pattern: '', confidence_threshold: 0.75 },
] as any[];

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
      <button class="btn btn-primary" (click)="isCreating.set(!isCreating())">
        <app-icon [icon]="Plus" [size]="16" />
        <span>{{ isCreating() ? 'Close Builder' : 'New Custom Schema' }}</span>
      </button>
    </div>

    <!-- Creation Form -->
    @if (isCreating()) {
      <form ngNativeValidate (ngSubmit)="handleSubmit()" class="glass-card">
        <h3>Define New Extraction Schema</h3>

        @if (errorMsg()) {
          <div class="error">
            <app-icon [icon]="AlertCircle" [size]="16" />
            <span>{{ errorMsg() }}</span>
          </div>
        }

        <div class="form-grid">
          <div>
            <label class="lbl" for="sb-name">Schema Title *</label>
            <input id="sb-name" name="name" type="text" placeholder="e.g., Logistics Bill of Lading" [(ngModel)]="name" class="field-input" required />
          </div>
          <div>
            <label class="lbl" for="sb-code">Type Code (API Slug) *</label>
            <input id="sb-code" name="docTypeCode" type="text" placeholder="e.g., bill_of_lading" [(ngModel)]="docTypeCode" class="field-input" required />
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

        <div class="actions">
          <button type="button" class="btn btn-secondary" (click)="isCreating.set(false)">Cancel</button>
          <button type="submit" class="btn btn-primary" [disabled]="saving()">
            {{ saving() ? 'Registering Schema...' : 'Save & Activate Schema' }}
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
              <h3>{{ s.name }}</h3>
              <p class="schema-desc">{{ s.description || 'No description provided' }}</p>
            </div>
            @if (!builtIn.includes(s.id)) {
              <button class="btn btn-secondary btn-sm del" (click)="handleDelete(s.id)" title="Delete Schema" aria-label="Delete Schema">
                <app-icon [icon]="Trash2" [size]="14" />
              </button>
            }
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
      const formattedFields = this.fields().map((f) => ({
        name: f.name.trim().toLowerCase().replace(/[\s\-]+/g, '_'),
        label: f.label.trim(),
        data_type: f.data_type,
        required: f.required,
        regex_pattern: f.regex_pattern ? f.regex_pattern.trim() : null,
        confidence_threshold: parseFloat(f.confidence_threshold) || 0.75,
        enum_values: f.enum_values ? f.enum_values.split(',').map((x: string) => x.trim()).filter(Boolean) : null,
        aliases: f.aliases ? f.aliases.split(',').map((x: string) => x.trim()).filter(Boolean) : null,
      }));

      const name = this.name;
      const newSchema = await api.createSchema({
        name,
        document_type_code: this.docTypeCode.trim().toLowerCase().replace(/[\s\-]+/g, '_'),
        description: this.description,
        fields: formattedFields,
      });

      this.store.schemaCreated(newSchema);
      this.successMsg.set(`Schema '${name}' created successfully!`);
      this.isCreating.set(false);
      this.name = '';
      this.docTypeCode = '';
      this.description = '';
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
