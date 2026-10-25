import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AlertCircle, FileBadge, FileSignature, FileText, FolderPlus, Loader2, Receipt, Sparkles, UploadCloud, X } from 'lucide';
import { api } from '../core/api';
import { DismissDirective } from '../core/dismiss.directive';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

const PIPELINES = [
  { id: 'auto', label: 'Auto-detect (any document)' },
  { id: 'generic', label: 'General: all labelled values' },
  { id: 'contracts', label: 'Commercial Contracts & NDAs' },
  { id: 'identity', label: 'Passport & Identity (MRZ)' },
  { id: 'invoices', label: 'Invoices & Accounts Payable' },
  { id: 'custom', label: 'Use a Template' },
];

// Global ingestion modal. The shell renders it only while store.uploadOpen() is true.
@Component({
  selector: 'app-upload-modal',
  imports: [Icon, DismissDirective, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .title-row { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .title-row .stat-icon-wrapper { width: 32px; height: 32px; flex-shrink: 0; }
    h3 { font-size: 1.05rem; font-weight: 700; }
    .subtitle { font-size: 0.75rem; color: var(--text-secondary); }
    .close-btn { padding: 6px; border-radius: 50%; flex-shrink: 0; }
    .error { padding: 10px 14px; border-radius: var(--radius-sm); background: color-mix(in srgb, var(--danger) 15%, transparent);
      border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent); color: var(--danger-text); font-size: 0.8rem; display: flex; align-items: center; gap: 8px; }
    .section-label { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
    .presets { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 6px; }
    .presets .btn { font-size: 0.75rem; padding: 8px 6px; justify-content: flex-start; }
    .divider { border-top: 1px solid var(--border-color); margin: 4px 0; }
    .field-label { display: block; font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; color: var(--text-secondary); }
    .folder-row { display: flex; gap: 8px; align-items: center; }
    .folder-row select { flex: 1; min-width: 0; }
    .pipelines { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .pipelines .btn { justify-content: flex-start; padding: 8px 12px; text-align: left; }
    .drop-content { display: flex; flex-direction: column; align-items: center; gap: 8px; }
    .drop-icon { width: 48px; height: 48px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
    .drop-icon.ready { background: color-mix(in srgb, var(--success) 15%, transparent); color: var(--success-text); }
    .drop-icon.empty { background: color-mix(in srgb, var(--primary) 15%, transparent); color: var(--primary-text); }
    .file-name { font-weight: 600; font-size: 0.9rem; word-break: break-all; }
    .hint { font-size: 0.75rem; color: var(--text-muted); }
    .replace { font-size: 0.72rem; color: var(--primary); margin-top: 4px; }
    .spin { animation: spin 1s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (max-width: 640px) {
      .presets { grid-template-columns: 1fr; }
      .pipelines { grid-template-columns: 1fr; }
      .dropzone { padding: 28px 16px; }
      .modal-footer .btn { flex: 1 1 auto; justify-content: center; }
    }
  `,
  template: `
    <div class="modal-backdrop">
      <!-- Same rule as every popover: a click outside the dialog or Escape closes it -->
      <div class="modal-dialog" role="dialog" aria-modal="true" aria-label="Ingest Document to Pipeline"
        [appDismiss]="true" (dismissed)="handleClose()">
        <div class="modal-header">
          <div class="title-row">
            <div class="stat-icon-wrapper indigo"><app-icon [icon]="UploadCloud" [size]="16" /></div>
            <div>
              <h3>Ingest Document to Pipeline</h3>
              <p class="subtitle">PDF, image or text with automated OCR, layout analysis &amp; field extraction</p>
            </div>
          </div>
          <button class="btn btn-secondary btn-sm close-btn" (click)="handleClose()" aria-label="Close">
            <app-icon [icon]="X" [size]="16" />
          </button>
        </div>

        <div class="modal-body">
          @if (errorMessage()) {
            <div class="error"><app-icon [icon]="AlertCircle" [size]="16" /><span>{{ errorMessage() }}</span></div>
          }

          <!-- Quick Presets row: only when the server's demo feature flag is on -->
          @if (store.features().demo_presets) {
          <div>
            <span class="section-label">Or Test With Instant Sample Preset</span>
            <div class="presets">
              <button type="button" class="btn btn-secondary btn-sm" (click)="handleSampleClick('contract')" [disabled]="isUploading()">
                <app-icon [icon]="FileSignature" [size]="14" style="color:var(--primary-text)" /><span>Contract MSA</span>
              </button>
              <button type="button" class="btn btn-secondary btn-sm" (click)="handleSampleClick('passport')" [disabled]="isUploading()">
                <app-icon [icon]="FileBadge" [size]="14" style="color:var(--accent-text)" /><span>US Passport</span>
              </button>
              <button type="button" class="btn btn-secondary btn-sm" (click)="handleSampleClick('invoice')" [disabled]="isUploading()">
                <app-icon [icon]="Receipt" [size]="14" style="color:var(--success-text)" /><span>Cloud Invoice</span>
              </button>
            </div>
          </div>

          <div class="divider"></div>
          }

          <!-- Pipeline Type Selector -->
          <div>
            <label class="field-label">Document Processing Pipeline</label>
            <div class="pipelines">
              @for (p of pipelines; track p.id) {
                <button type="button" class="btn btn-sm" [class.btn-primary]="docType() === p.id" [class.btn-secondary]="docType() !== p.id"
                  (click)="docType.set(p.id)">
                  <app-icon [icon]="Sparkles" [size]="14" /><span>{{ p.label }}</span>
                </button>
              }
            </div>
          </div>

          <!-- Schema Selector if custom -->
          @if (docType() === 'custom') {
            <div>
              <label class="field-label" for="upload-schema">Select Template</label>
              <select id="upload-schema" class="field-input" [ngModel]="selectedSchemaId()" (ngModelChange)="selectedSchemaId.set($event)">
                <option value="">-- Choose Template --</option>
                @for (s of store.schemas(); track s.id) {
                  <option [value]="s.id">{{ s.name }} ({{ s.document_type_code }})</option>
                }
              </select>
            </div>
          }

          <!-- Where the document goes: the folder open in the Document Hub, or none (top level) -->
          <div>
            <label class="field-label" for="upload-folder">Save to folder</label>
            <div class="folder-row">
              <select id="upload-folder" class="field-input" [ngModel]="folderId()" (ngModelChange)="folderId.set($event || null)">
                <option [ngValue]="null">No folder (top level)</option>
                @for (f of folderOptions(); track f.id) {
                  <option [ngValue]="f.id">{{ f.label }}</option>
                }
              </select>
              <button type="button" class="btn btn-secondary btn-sm" (click)="newFolder()" [disabled]="isUploading()" title="Create a folder inside the one selected">
                <app-icon [icon]="FolderPlus" [size]="14" /><span>New folder</span>
              </button>
            </div>
          </div>

          <!-- Drag & Drop File Zone (tap to pick a file; phones also offer the camera / photo library) -->
          <div class="dropzone" [class.active]="isDragOver()" role="button" tabindex="0"
            (dragover)="$event.preventDefault(); isDragOver.set(true)"
            (dragleave)="isDragOver.set(false)"
            (drop)="handleDrop($event)"
            (click)="fileInput.click()"
            (keydown.enter)="fileInput.click()" (keydown.space)="$event.preventDefault(); fileInput.click()">
            <input #fileInput type="file" style="display:none"
              accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.txt,.md,.csv,.json"
              (click)="$event.stopPropagation()"
              (change)="handleFileSelect($any($event.target).files?.[0])" />

            @if (selectedFile(); as file) {
              <div class="drop-content">
                <div class="drop-icon ready"><app-icon [icon]="FileText" [size]="24" /></div>
                <div class="file-name">{{ file.name }}</div>
                <div class="hint">{{ (file.size / 1024).toFixed(1) }} KB · Ready to Process</div>
                <span class="replace">Click to replace file</span>
              </div>
            } @else {
              <div class="drop-content">
                <div class="drop-icon empty"><app-icon [icon]="UploadCloud" [size]="24" /></div>
                <div class="file-name">Drop document here, or browse files</div>
                <div class="hint">PDF (multi-page, text or scanned), PNG, JPG, TIFF or TXT · OCR runs locally</div>
              </div>
            }
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" (click)="handleClose()" [disabled]="isUploading()">Cancel</button>
          <button type="button" class="btn btn-primary" (click)="handleUpload()" [disabled]="isUploading() || !selectedFile()">
            @if (isUploading()) {
              <app-icon class="spin" [icon]="Loader2" [size]="16" /><span>Running Extraction Pipeline...</span>
            } @else {
              <app-icon [icon]="Sparkles" [size]="16" /><span>Ingest &amp; Extract Data</span>
            }
          </button>
        </div>
      </div>
    </div>
  `,
})
export class UploadModal {
  protected readonly X = X; protected readonly UploadCloud = UploadCloud; protected readonly FileText = FileText;
  protected readonly AlertCircle = AlertCircle; protected readonly Loader2 = Loader2; protected readonly Sparkles = Sparkles;
  protected readonly FileSignature = FileSignature; protected readonly FileBadge = FileBadge; protected readonly Receipt = Receipt;
  protected readonly FolderPlus = FolderPlus;

  protected readonly store = inject(Store);
  private readonly router = inject(Router);
  protected readonly pipelines = PIPELINES;

  protected readonly selectedFile = signal<File | null>(null);
  protected readonly docType = signal('auto');
  protected readonly selectedSchemaId = signal('');
  protected readonly isUploading = signal(false);
  protected readonly isDragOver = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly folderId = signal<string | null>(this.store.currentFolder());
  protected readonly folderOptions = computed(() =>
    this.store.folders()
      .map((f) => ({ id: f.id, label: this.store.folderLabel(f.id) }))
      .sort((a, b) => a.label.localeCompare(b.label)));

  async newFolder() {
    const name = prompt('New folder name:')?.trim();
    if (!name) return;
    try {
      const f: any = await api.createFolder(name, this.folderId());
      await this.store.refreshFolders();
      this.folderId.set(f.id);
    } catch (err: any) {
      this.errorMessage.set(err.message);
    }
  }

  handleClose() {
    if (this.isUploading()) return;
    this.selectedFile.set(null);
    this.errorMessage.set(null);
    this.store.uploadOpen.set(false);
  }

  handleFileSelect(file: File | null | undefined) {
    if (!file) return;
    this.selectedFile.set(file);
    this.errorMessage.set(null);
  }

  handleDrop(e: DragEvent) {
    e.preventDefault();
    this.isDragOver.set(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) this.handleFileSelect(file);
  }

  private documentUploaded(doc: any) {
    this.store.documentAdded(doc);
    this.store.uploadOpen.set(false);
    this.router.navigate(['/review', doc.id]);
  }

  async handleUpload() {
    const file = this.selectedFile();
    if (!file) {
      this.errorMessage.set('Please select a file to upload.');
      return;
    }
    if (this.docType() === 'custom' && !this.selectedSchemaId()) {
      this.errorMessage.set('Choose a template, or use Auto-detect.');
      return;
    }

    this.isUploading.set(true);
    this.errorMessage.set(null);
    try {
      const doc = await api.uploadDocument({
        file,
        docType: this.docType(),
        schemaId: this.docType() === 'custom' ? this.selectedSchemaId() : null,
        sync: true,
        folderId: this.folderId(),
      });
      this.selectedFile.set(null);
      this.documentUploaded(doc);
    } catch (err: any) {
      this.errorMessage.set(err.message || 'Upload and processing failed.');
    } finally {
      this.isUploading.set(false);
    }
  }

  async handleSampleClick(sampleType: string) {
    this.isUploading.set(true);
    this.errorMessage.set(null);
    try {
      let doc = await api.runSamplePreset(sampleType);
      // Samples are made at the top level; put this one in the chosen folder
      if (this.folderId()) {
        await api.moveDocuments([doc.id], this.folderId());
        doc = { ...doc, folder_id: this.folderId() };
      }
      this.documentUploaded(doc);
    } catch (err: any) {
      this.errorMessage.set(err.message || 'Sample generation failed.');
    } finally {
      this.isUploading.set(false);
    }
  }
}
