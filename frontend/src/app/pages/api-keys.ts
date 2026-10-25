import { ChangeDetectionStrategy, Component, WritableSignal, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Check, Copy, Key, Plus, Terminal, Trash2 } from 'lucide';
import { api, copyText, serverOrigin } from '../core/api';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

const SCOPES = [
  { id: 'doc:read', label: 'doc:read (View documents & exports)' },
  { id: 'doc:write', label: 'doc:write (Upload & review documents)' },
  { id: 'schema:manage', label: 'schema:manage (Configure custom schemas)' },
  { id: 'admin', label: 'admin (Manage keys & webhooks)' },
];

@Component({
  selector: 'app-api-keys',
  imports: [FormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
    .created { padding: 20px 24px; border: 1px solid color-mix(in srgb, var(--success) 40%, transparent); background: color-mix(in srgb, var(--success) 8%, transparent); }
    .created-title { display: flex; align-items: center; gap: 8px; color: var(--success-text); font-weight: 700; margin-bottom: 6px; }
    .created p { font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 12px; }
    .created-row { display: flex; align-items: center; gap: 8px; }
    .created-row .field-input { font-family: var(--font-mono); color: var(--accent-text); font-weight: 600; min-width: 0; flex: 1; }
    .banner { padding: 24px; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    .banner h2 { font-size: 1.2rem; font-weight: 700; }
    .banner p { color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px; }
    .banner .btn { flex-shrink: 0; }
    form { padding: 24px; }
    h3 { font-size: 1.05rem; font-weight: 700; margin-bottom: 16px; }
    .form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 16px; }
    .lbl { display: block; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
    .scopes-box { margin-bottom: 20px; }
    .scopes-box .lbl { margin-bottom: 8px; }
    .scopes { display: flex; gap: 16px; flex-wrap: wrap; }
    .scope { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; cursor: pointer; }
    .actions { display: flex; justify-content: flex-end; gap: 12px; flex-wrap: wrap; }
    .table-card { padding: 0; }
    .name-cell { display: flex; align-items: center; gap: 10px; }
    .name-cell .stat-icon-wrapper { width: 30px; height: 30px; flex-shrink: 0; }
    .name { font-weight: 600; }
    .prefix { font-family: var(--font-mono); font-size: 0.82rem; color: var(--accent-text); }
    .pills { display: flex; gap: 4px; flex-wrap: wrap; }
    .pills .type-pill { font-size: 0.7rem; }
    .meter { width: 130px; }
    .meter-nums { display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 4px; }
    .meter-nums span:last-child { color: var(--text-muted); }
    .bar { height: 5px; background: color-mix(in srgb, var(--tint) 8%, transparent); border-radius: 999px; overflow: hidden; }
    .bar div { height: 100%; background: var(--primary); }
    .bar div.high { background: var(--danger); }
    .date { font-size: 0.8rem; color: var(--text-secondary); }
    .right { text-align: right; }
    .revoke { color: var(--danger); }
    .snippet { padding: 24px; min-width: 0; }
    .snippet-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    .snippet-title { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 0.95rem; color: var(--accent-cyan); }
    .snippet-title span { color: var(--text-primary); }
    .cell-label { display: none; }

    @media (max-width: 640px) {
      .banner { flex-direction: column; align-items: stretch; padding: 16px; }
      form, .snippet { padding: 16px; }
      .created { padding: 16px; }
      .created-row { flex-wrap: wrap; }
      .created-row .field-input { flex: 1 1 100%; }
      /* Phones: each key becomes a stacked card instead of a wide table row */
      .data-table thead { display: none; }
      .data-table, .data-table tbody, .data-table tr, .data-table td { display: block; width: 100%; }
      .data-table tr { border-bottom: 1px solid var(--border-color); padding: 8px 0; }
      .data-table td { border-bottom: none; padding: 6px 14px; text-align: left; }
      .cell-label { display: block; font-size: 0.7rem; color: var(--text-muted); margin-bottom: 2px; }
      .right { text-align: left; }
      .meter { width: 100%; }
    }
  `,
  template: `
    <!-- Newly Created Key Alert Modal/Banner -->
    @if (createdKey()) {
      <div class="glass-card created">
        <div class="created-title">
          <app-icon [icon]="Check" [size]="20" />
          <span>API Key Generated Successfully</span>
        </div>
        <p>Make sure to copy your API key now. You won't be able to see it again!</p>
        <div class="created-row">
          <input type="text" readonly [value]="createdKey()" class="field-input" />
          <button class="btn btn-primary" (click)="copy(createdKey()!, copiedKey)">
            <app-icon [icon]="copiedKey() ? Check : Copy" [size]="16" />
            <span>{{ copiedKey() ? 'Copied!' : 'Copy' }}</span>
          </button>
          <button class="btn btn-secondary" (click)="createdKey.set(null)">Done</button>
        </div>
      </div>
    }

    <!-- Top Banner -->
    <div class="glass-card banner">
      <div>
        <h2>Programmatic API Access &amp; Tokens</h2>
        <p>Generate scoped API keys for server-to-server automated document ingestion and webhook integration.</p>
      </div>
      <button class="btn btn-primary" (click)="isCreating.set(!isCreating())">
        <app-icon [icon]="Plus" [size]="16" />
        <span>Generate New Key</span>
      </button>
    </div>

    <!-- Creation Modal / Form -->
    @if (isCreating()) {
      <form ngNativeValidate (ngSubmit)="handleCreate()" class="glass-card">
        <h3>Create New Scoped API Key</h3>
        <div class="form-grid">
          <div>
            <label class="lbl" for="key-name">Key Identifier / Name *</label>
            <input id="key-name" name="name" type="text" placeholder="e.g. Backend Invoice Processor Worker"
              [(ngModel)]="name" class="field-input" required />
          </div>
          <div>
            <label class="lbl" for="key-quota">Monthly Processing Quota (Pages)</label>
            <input id="key-quota" name="quota" type="number" [(ngModel)]="quota" class="field-input" min="100" step="500" />
          </div>
        </div>

        <div class="scopes-box">
          <span class="lbl">Select Permitted Scopes</span>
          <div class="scopes">
            @for (s of scopeOptions; track s.id) {
              <label class="scope">
                <input type="checkbox" [checked]="scopes().includes(s.id)" (change)="toggleScope(s.id, $any($event.target).checked)" />
                <span>{{ s.label }}</span>
              </label>
            }
          </div>
        </div>

        <div class="actions">
          <button type="button" class="btn btn-secondary" (click)="isCreating.set(false)">Cancel</button>
          <button type="submit" class="btn btn-primary" [disabled]="loading()">
            {{ loading() ? 'Generating...' : 'Generate Secret Key' }}
          </button>
        </div>
      </form>
    }

    <!-- Keys Table -->
    <div class="glass-card table-card">
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>Key Name</th>
              <th>Token Prefix</th>
              <th>Assigned Scopes</th>
              <th>Quota Meter</th>
              <th>Created Date</th>
              <th class="right">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (k of store.apiKeys(); track k.id) {
              <tr>
                <td>
                  <div class="name-cell">
                    <div class="stat-icon-wrapper indigo"><app-icon [icon]="Key" [size]="15" /></div>
                    <span class="name">{{ k.name }}</span>
                  </div>
                </td>
                <td><span class="cell-label">Token Prefix</span><span class="prefix">{{ k.key_prefix }}</span></td>
                <td>
                  <span class="cell-label">Assigned Scopes</span>
                  <div class="pills">
                    @for (sc of k.scopes; track $index) { <span class="type-pill">{{ sc }}</span> }
                  </div>
                </td>
                <td>
                  <span class="cell-label">Quota Meter</span>
                  <div class="meter">
                    <div class="meter-nums">
                      <span>{{ k.quota_used.toLocaleString() }}</span>
                      <span>{{ k.quota_limit.toLocaleString() }}</span>
                    </div>
                    <div class="bar"><div [style.width.%]="quotaPercent(k)" [class.high]="quotaPercent(k) > 90"></div></div>
                  </div>
                </td>
                <td><span class="cell-label">Created Date</span><span class="date">{{ dateStr(k.created_at) }}</span></td>
                <td class="right">
                  <button class="btn btn-secondary btn-sm revoke" (click)="handleRevoke(k.id)" title="Revoke Key">
                    <app-icon [icon]="Trash2" [size]="14" />
                    <span>Revoke</span>
                  </button>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </div>

    <!-- Developer Snippet Card -->
    <div class="glass-card snippet">
      <div class="snippet-head">
        <div class="snippet-title">
          <app-icon [icon]="Terminal" [size]="18" />
          <span>Quick cURL Ingestion Request</span>
        </div>
        <button class="btn btn-secondary btn-sm" (click)="copy(curlExample(), copiedSnippet)">
          <app-icon [icon]="copiedSnippet() ? Check : Copy" [size]="14" />
          <span>{{ copiedSnippet() ? 'Copied' : 'Copy cURL' }}</span>
        </button>
      </div>
      <pre class="code-box"><code>{{ curlExample() }}</code></pre>
    </div>
  `,
})
export class ApiKeys {
  protected readonly Check = Check; protected readonly Copy = Copy; protected readonly Plus = Plus;
  protected readonly Key = Key; protected readonly Trash2 = Trash2; protected readonly Terminal = Terminal;

  protected readonly store = inject(Store);
  protected readonly scopeOptions = SCOPES;
  protected readonly isCreating = signal(false);
  protected name = '';
  protected quota: number | string = 10000;
  protected readonly scopes = signal<string[]>(['doc:read', 'doc:write']);
  protected readonly createdKey = signal<string | null>(null);
  protected readonly copiedKey = signal(false);
  protected readonly copiedSnippet = signal(false);
  protected readonly loading = signal(false);

  protected readonly curlExample = computed(() => `curl -X POST "${serverOrigin()}/api/v1/documents/upload" \\
  -H "X-API-Key: ${this.store.apiKeys()[0]?.key_prefix ? 'dp_live_...' : 'dp_live_YOUR_KEY'}" \\
  -F "file=@./commercial_contract.pdf" \\
  -F "doc_type=contracts" \\
  -F "sync=true"`);

  quotaPercent(k: any) {
    return Math.min(100, Math.round((k.quota_used / k.quota_limit) * 100));
  }

  dateStr(d: string) {
    return new Date(d).toLocaleDateString();
  }

  toggleScope(id: string, on: boolean) {
    this.scopes.update((list) => (on ? [...list, id] : list.filter((x) => x !== id)));
  }

  async handleCreate() {
    if (!this.name) return;
    this.loading.set(true);
    try {
      const newKey = await api.createApiKey({
        name: this.name,
        quota_limit: parseInt(String(this.quota), 10),
        scopes: this.scopes(),
      });
      this.createdKey.set(newKey.full_key);
      this.store.apiKeys.update((list) => [newKey, ...list]);
      this.name = '';
      this.isCreating.set(false);
    } catch (err: any) {
      alert(`Failed to create API key: ${err.message}`);
    } finally {
      this.loading.set(false);
    }
  }

  async handleRevoke(id: string) {
    if (!confirm('Are you sure you want to revoke this API key immediately? Programmatic integrations using it will fail.')) return;
    try {
      await api.revokeApiKey(id);
      this.store.apiKeys.update((list) => list.filter((k) => k.id !== id));
    } catch (err: any) {
      alert(`Revoke error: ${err.message}`);
    }
  }

  copy(text: string, flag: WritableSignal<boolean>) {
    copyText(text);
    flag.set(true);
    setTimeout(() => flag.set(false), 2500);
  }
}
