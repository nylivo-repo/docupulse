import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CircleCheck, CircleX, Plus, Radio, Send, Trash2 } from 'lucide';
import { api, serverOrigin } from '../core/api';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

const EVENTS = [
  { id: 'document.completed', label: 'document.completed (STP Approved)' },
  { id: 'document.needs_review', label: 'document.needs_review (Flagged for Review)' },
  { id: 'document.approved', label: 'document.approved (Verified by Human)' },
  { id: 'document.rejected', label: 'document.rejected (Rejected Document)' },
];

@Component({
  selector: 'app-webhooks',
  imports: [FormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
    .banner { padding: 24px; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    .banner h2 { font-size: 1.2rem; font-weight: 700; }
    .banner p { color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px; }
    .banner .btn { flex-shrink: 0; }
    form, .card { padding: 24px; min-width: 0; }
    h3 { font-size: 1.05rem; font-weight: 700; margin-bottom: 16px; }
    .form-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 16px; }
    .lbl { display: block; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
    .events-box { margin-bottom: 20px; }
    .events-box .lbl { margin-bottom: 8px; }
    .events { display: flex; gap: 16px; flex-wrap: wrap; }
    .event { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; cursor: pointer; }
    .actions { display: flex; justify-content: flex-end; gap: 12px; flex-wrap: wrap; }
    .table-card { padding: 0; }
    .url-cell { display: flex; align-items: center; gap: 10px; }
    .url-cell .stat-icon-wrapper { width: 30px; height: 30px; flex-shrink: 0; }
    .url { font-family: var(--font-mono); font-size: 0.85rem; overflow-wrap: anywhere; }
    .pills { display: flex; gap: 4px; flex-wrap: wrap; }
    .pills .type-pill { font-size: 0.7rem; }
    .deliveries { font-size: 0.8rem; color: var(--text-secondary); white-space: nowrap; }
    .ok { color: var(--success-text); } .ok-b { color: var(--success-text); font-weight: 600; } .bad { color: var(--danger-text); }
    .right { text-align: right; }
    .del { color: var(--danger); }
    .cell-label { display: none; }
    .sim-title { margin-bottom: 6px; }
    .sim-text { color: var(--text-secondary); font-size: 0.82rem; margin-bottom: 16px; }
    .sim-grid { display: grid; grid-template-columns: 2fr 1fr auto; gap: 12px; align-items: center; }
    .result { margin-top: 16px; padding: 16px; border-radius: var(--radius-md); background: color-mix(in srgb, var(--danger) 8%, transparent); border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent); }
    .result.success { background: color-mix(in srgb, var(--success) 8%, transparent); border-color: color-mix(in srgb, var(--success) 30%, transparent); }
    .result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-weight: 700; font-size: 0.88rem; color: var(--danger-text); }
    .result.success .result-head { color: var(--success-text); }
    .result pre { font-size: 0.75rem; font-family: var(--font-mono); color: var(--text-secondary); overflow-x: auto; background: color-mix(in srgb, var(--shade) 30%, transparent); padding: 10px; border-radius: 4px; }
    .logs-title { font-size: 1rem; margin-bottom: 14px; }
    .logs { display: flex; flex-direction: column; gap: 8px; }
    .log { display: flex; align-items: center; justify-content: space-between; gap: 8px 16px; flex-wrap: wrap; padding: 10px 14px;
      border-radius: var(--radius-sm); background: color-mix(in srgb, var(--tint) 2%, transparent); border: 1px solid var(--border-color); font-size: 0.82rem; }
    .log-left, .log-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-width: 0; }
    .log-right { gap: 16px; color: var(--text-muted); }
    .mono { color: var(--text-secondary); font-family: var(--font-mono); }

    @media (max-width: 640px) {
      .banner { flex-direction: column; align-items: stretch; padding: 16px; }
      form, .card { padding: 16px; }
      .sim-grid { grid-template-columns: 1fr; }
      /* Phones: each webhook becomes a stacked card instead of a wide table row */
      .data-table thead { display: none; }
      .data-table, .data-table tbody, .data-table tr, .data-table td { display: block; width: 100%; }
      .data-table tr { border-bottom: 1px solid var(--border-color); padding: 8px 0; }
      .data-table td { border-bottom: none; padding: 6px 14px; text-align: left; }
      .cell-label { display: block; font-size: 0.7rem; color: var(--text-muted); margin-bottom: 2px; }
      .right { text-align: left; }
    }
  `,
  template: `
    <!-- Top Banner -->
    <div class="glass-card banner">
      <div>
        <h2>Webhook Subscriptions &amp; Event Streaming</h2>
        <p>Receive real-time push events when documents complete extraction, pass automated compliance, or require human review.</p>
      </div>
      <button class="btn btn-primary" (click)="isCreating.set(!isCreating())">
        <app-icon [icon]="Plus" [size]="16" />
        <span>Add Webhook Endpoint</span>
      </button>
    </div>

    <!-- Creation Modal / Form -->
    @if (isCreating()) {
      <form ngNativeValidate (ngSubmit)="handleCreate()" class="glass-card">
        <h3>Register New Webhook URL</h3>
        <div class="form-grid">
          <div>
            <label class="lbl" for="wh-url">Payload Destination URL *</label>
            <input id="wh-url" name="url" type="url" placeholder="https://your-api.com/webhooks/docupulse"
              [(ngModel)]="url" class="field-input" required />
          </div>
          <div>
            <label class="lbl" for="wh-secret">HMAC Secret (Optional)</label>
            <input id="wh-secret" name="secret" type="text" placeholder="whsec_..." [(ngModel)]="secret" class="field-input" />
          </div>
        </div>

        <div class="events-box">
          <span class="lbl">Subscribe to Event Triggers</span>
          <div class="events">
            @for (ev of eventOptions; track ev.id) {
              <label class="event">
                <input type="checkbox" [checked]="events().includes(ev.id)" (change)="toggleEvent(ev.id, $any($event.target).checked)" />
                <span>{{ ev.label }}</span>
              </label>
            }
          </div>
        </div>

        <div class="actions">
          <button type="button" class="btn btn-secondary" (click)="isCreating.set(false)">Cancel</button>
          <button type="submit" class="btn btn-primary">Register Webhook</button>
        </div>
      </form>
    }

    <!-- Webhook Endpoints List -->
    <div class="glass-card table-card">
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>Endpoint URL</th>
              <th>Subscribed Events</th>
              <th>Deliveries</th>
              <th>Status</th>
              <th class="right">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (wh of store.webhooks(); track wh.id) {
              <tr>
                <td>
                  <div class="url-cell">
                    <div class="stat-icon-wrapper cyan"><app-icon [icon]="Radio" [size]="14" /></div>
                    <span class="url">{{ wh.url }}</span>
                  </div>
                </td>
                <td>
                  <span class="cell-label">Subscribed Events</span>
                  <div class="pills">
                    @for (ev of wh.events; track $index) { <span class="type-pill">{{ ev }}</span> }
                  </div>
                </td>
                <td>
                  <span class="cell-label">Deliveries</span>
                  <span class="deliveries">
                    <span class="ok-b">{{ wh.successful_deliveries }}</span> succ · <span class="bad">{{ wh.failed_deliveries }}</span> fail
                  </span>
                </td>
                <td><span class="cell-label">Status</span><span class="badge badge-approved">Active</span></td>
                <td class="right">
                  <button class="btn btn-secondary btn-sm del" (click)="handleDelete(wh.id)" title="Delete Webhook" aria-label="Delete Webhook">
                    <app-icon [icon]="Trash2" [size]="14" />
                  </button>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </div>

    <!-- Live Webhook Tester Simulator -->
    <div class="glass-card card">
      <h3 class="sim-title">Interactive Webhook Delivery Simulator</h3>
      <p class="sim-text">Test your webhook ingestion server immediately with an authenticated payload dispatch.</p>

      <div class="sim-grid">
        <input type="url" [(ngModel)]="testUrl" class="field-input" placeholder="Target test URL..." aria-label="Target test URL" />
        <select [(ngModel)]="testEvent" class="field-input" aria-label="Event">
          <option value="document.completed">document.completed</option>
          <option value="document.needs_review">document.needs_review</option>
          <option value="document.approved">document.approved</option>
        </select>
        <button class="btn btn-primary" (click)="handleRunSimulator()" [disabled]="isTesting()">
          <app-icon [icon]="Send" [size]="15" />
          <span>{{ isTesting() ? 'Sending...' : 'Simulate Dispatch' }}</span>
        </button>
      </div>

      @if (testResult(); as r) {
        <div class="result" [class.success]="r.success">
          <div class="result-head">
            <app-icon [icon]="r.success ? CircleCheck : CircleX" [size]="18" />
            <span>Status Code {{ r.status_code }} ({{ r.duration_ms }}ms)</span>
          </div>
          <pre>{{ r.response || 'Empty body response' }}</pre>
        </div>
      }
    </div>

    <!-- Recent Delivery Logs -->
    <div class="glass-card card">
      <h3 class="logs-title">Recent Webhook Delivery Audit Log</h3>
      <div class="logs">
        @for (log of logs().slice(0, 5); track log.id) {
          <div class="log">
            <div class="log-left">
              <app-icon [icon]="log.success ? CircleCheck : CircleX" [size]="16" [class.ok]="log.success" [class.bad]="!log.success" />
              <span class="type-pill">{{ log.event }}</span>
              <span class="mono">HTTP {{ log.status_code }}</span>
            </div>
            <div class="log-right">
              <span>{{ log.duration_ms }}ms</span>
              <span>{{ timeStr(log.timestamp) }}</span>
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class Webhooks implements OnInit {
  protected readonly Plus = Plus; protected readonly Trash2 = Trash2; protected readonly Send = Send;
  protected readonly CircleCheck = CircleCheck; protected readonly CircleX = CircleX; protected readonly Radio = Radio;

  protected readonly store = inject(Store);
  protected readonly eventOptions = EVENTS;
  protected readonly isCreating = signal(false);
  protected url = '';
  protected readonly events = signal<string[]>(['document.completed', 'document.needs_review']);
  protected secret = '';

  // Simulator State
  // Built-in local receiver, so the simulator works with no outside service
  protected testUrl = `${serverOrigin()}/api/v1/webhooks/echo`;
  protected testEvent = 'document.completed';
  protected readonly testResult = signal<any | null>(null);
  protected readonly isTesting = signal(false);

  // Delivery Logs
  protected readonly logs = signal<any[]>([]);

  ngOnInit() {
    this.loadLogs();
  }

  async loadLogs() {
    try {
      this.logs.set(await api.getWebhookLogs());
    } catch (e) {
      console.error(e);
    }
  }

  timeStr(t: string) {
    return new Date(t).toLocaleTimeString();
  }

  toggleEvent(id: string, on: boolean) {
    this.events.update((list) => (on ? [...list, id] : list.filter((x) => x !== id)));
  }

  async handleCreate() {
    if (!this.url) return;
    try {
      const wh = await api.createWebhook({
        url: this.url,
        events: this.events(),
        secret: this.secret || undefined,
      });
      this.store.webhooks.update((list) => [wh, ...list]);
      this.url = '';
      this.secret = '';
      this.isCreating.set(false);
    } catch (err: any) {
      alert(`Failed to add webhook: ${err.message}`);
    }
  }

  async handleDelete(id: string) {
    if (!confirm('Remove this webhook?')) return;
    try {
      await api.deleteWebhook(id);
      this.store.webhooks.update((list) => list.filter((w) => w.id !== id));
    } catch (err: any) {
      alert(`Delete error: ${err.message}`);
    }
  }

  async handleRunSimulator() {
    this.isTesting.set(true);
    this.testResult.set(null);
    try {
      const res = await api.testWebhook({
        url: this.testUrl,
        event: this.testEvent,
        secret: 'whsec_demo_signature_123',
        sample_data: {
          document_id: 'doc_simulated_982',
          doc_type: 'contracts',
          status: 'approved',
          overall_confidence: 0.96,
          extracted_title: 'Master Consulting Agreement',
          timestamp: new Date().toISOString(),
        },
      });
      this.testResult.set(res);
      this.loadLogs();
    } catch (err: any) {
      this.testResult.set({
        success: false,
        status_code: 500,
        response: err.message,
        duration_ms: 0,
      });
    } finally {
      this.isTesting.set(false);
    }
  }
}
