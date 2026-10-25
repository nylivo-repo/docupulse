import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { api } from '../core/api';
import { Store } from '../core/store';
import { DocumentList } from './document-list';
import { StatsOverview } from './stats-overview';

// Dashboard: demo presets, KPI cards and the document list
@Component({
  selector: 'app-dashboard',
  imports: [StatsOverview, DocumentList],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
    h2 { font-size: 1.15rem; font-weight: 700; margin-bottom: 14px; }
    @media (max-width: 640px) { :host { gap: 16px; } h2 { font-size: 1.02rem; margin-bottom: 10px; } }
  `,
  template: `
    <app-stats-overview [analytics]="store.analytics()" [loadingPreset]="loadingPreset()" [showPresets]="store.features().demo_presets" (runPreset)="handleRunPreset($event)" />
    <div>
      <h2>Recent Ingestion Queue &amp; Extraction Results</h2>
      <app-document-list />
    </div>
  `,
})
export class Dashboard {
  protected readonly store = inject(Store);
  private readonly router = inject(Router);
  protected readonly loadingPreset = signal(false);

  async handleRunPreset(presetType: string) {
    this.loadingPreset.set(true);
    try {
      const newDoc: any = await api.runSamplePreset(presetType);
      this.store.documentAdded(newDoc);
      this.router.navigate(['/review', newDoc.id]);
    } catch (err: any) {
      alert(`Preset error: ${err.message}`);
    } finally {
      this.loadingPreset.set(false);
    }
  }
}
