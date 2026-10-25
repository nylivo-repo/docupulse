import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { Activity, AlertTriangle, CreditCard, FileBadge, FileCheck2, FileSignature, Receipt, Zap } from 'lucide';
import { Icon } from '../core/icon';

// Demo presets bar and the KPI cards at the top of the dashboard
@Component({
  selector: 'app-stats-overview',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: block; }
    .wrap { display: flex; flex-direction: column; gap: 20px; }
    .presets-banner .stat-icon-wrapper { width: 38px; height: 38px; }
    .credit-info { width: 100%; padding-right: 12px; }
    .credit-value { font-size: 1.4rem; }
    .meter { margin-top: 8px; background: color-mix(in srgb, var(--tint) 6%, transparent); border-radius: 999px; height: 6px; overflow: hidden; }
    .meter > div { background: linear-gradient(90deg, var(--primary), var(--accent-cyan)); height: 100%; border-radius: 999px; }
    @media (max-width: 640px) {
      .presets-actions .btn { flex: 1 1 100%; justify-content: flex-start; }
    }
  `,
  template: `
    @if (analytics(); as a) {
      <div class="wrap">
        <!-- 1-Click demo presets: only when the server's demo feature flag is on -->
        @if (showPresets()) {
        <div class="presets-banner">
          <div class="presets-info">
            <div class="stat-icon-wrapper indigo"><app-icon [icon]="Zap" [size]="20" /></div>
            <div>
              <h3>Instant Demo Presets (1-Click Processing)</h3>
              <p>Test the full OCR, extraction, and validation pipeline immediately with curated sample documents:</p>
            </div>
          </div>
          <div class="presets-actions">
            <button class="btn btn-secondary btn-sm" (click)="runPreset.emit('contract')" [disabled]="loadingPreset()">
              <app-icon [icon]="FileSignature" [size]="15" style="color:var(--primary-text)" /><span>Commercial Contract (MSA)</span>
            </button>
            <button class="btn btn-secondary btn-sm" (click)="runPreset.emit('passport')" [disabled]="loadingPreset()">
              <app-icon [icon]="FileBadge" [size]="15" style="color:var(--accent-text)" /><span>US Passport (MRZ &amp; KYC)</span>
            </button>
            <button class="btn btn-secondary btn-sm" (click)="runPreset.emit('invoice')" [disabled]="loadingPreset()">
              <app-icon [icon]="Receipt" [size]="15" style="color:var(--success-text)" /><span>Commercial Invoice (Math)</span>
            </button>
          </div>
        </div>
        }

        <!-- Primary KPI Grid -->
        <div class="stats-grid">
          <!-- STP Rate -->
          <div class="glass-card stat-card">
            <div class="stat-info">
              <span class="stat-label">Straight-Through Rate (STP)</span>
              <span class="stat-value" style="color:var(--success-text)">{{ a.straight_through_rate }}%</span>
              <div class="stat-subtext"><span>Automated with zero human edits</span></div>
            </div>
            <div class="stat-icon-wrapper emerald"><app-icon [icon]="Zap" [size]="22" /></div>
          </div>

          <!-- Total Documents -->
          <div class="glass-card stat-card">
            <div class="stat-info">
              <span class="stat-label">Total Documents Ingested</span>
              <span class="stat-value">{{ a.total_documents }}</span>
              <div class="stat-subtext"><span>{{ a.approved_count }} approved · {{ a.rejected_count }} rejected</span></div>
            </div>
            <div class="stat-icon-wrapper cyan"><app-icon [icon]="FileCheck2" [size]="22" /></div>
          </div>

          <!-- Avg Confidence -->
          <div class="glass-card stat-card">
            <div class="stat-info">
              <span class="stat-label">Model Confidence Score</span>
              <span class="stat-value">{{ avgConfidence() }}%</span>
              <div class="stat-subtext"><span>Weighted OCR &amp; regex heuristic</span></div>
            </div>
            <div class="stat-icon-wrapper indigo"><app-icon [icon]="Activity" [size]="22" /></div>
          </div>

          <!-- Needs Review -->
          <div class="glass-card stat-card">
            <div class="stat-info">
              <span class="stat-label">Needs Human Verification</span>
              <span class="stat-value" [style.color]="a.needs_review_count > 0 ? 'var(--warning-text)' : 'var(--text-secondary)'">{{ a.needs_review_count }}</span>
              <div class="stat-subtext"><span>In HITL review queue</span></div>
            </div>
            <div class="stat-icon-wrapper amber"><app-icon [icon]="AlertTriangle" [size]="22" /></div>
          </div>

          <!-- API key usage: only for people who own API keys -->
          @if (a.credits_total > 0) {
            <div class="glass-card stat-card">
              <div class="stat-info credit-info">
                <span class="stat-label">SaaS API Credit Meter</span>
                <span class="stat-value credit-value">{{ a.credits_used.toLocaleString() }} / {{ a.credits_total.toLocaleString() }}</span>
                <div class="meter"><div [style.width.%]="quotaPercent()"></div></div>
              </div>
              <div class="stat-icon-wrapper indigo"><app-icon [icon]="CreditCard" [size]="20" /></div>
            </div>
          }
        </div>
      </div>
    }
  `,
})
export class StatsOverview {
  protected readonly Zap = Zap; protected readonly FileSignature = FileSignature; protected readonly FileBadge = FileBadge;
  protected readonly Receipt = Receipt; protected readonly FileCheck2 = FileCheck2; protected readonly Activity = Activity;
  protected readonly AlertTriangle = AlertTriangle; protected readonly CreditCard = CreditCard;

  readonly analytics = input<any | null>(null);
  readonly loadingPreset = input(false);
  readonly showPresets = input(false);
  readonly runPreset = output<string>();

  protected readonly avgConfidence = computed(() => Math.round((this.analytics()?.avg_confidence ?? 0) * 100));
  protected readonly quotaPercent = computed(() => {
    const a = this.analytics();
    return a?.credits_total ? Math.min(100, Math.round((a.credits_used / a.credits_total) * 100)) : 0;
  });
}
