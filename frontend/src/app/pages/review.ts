import {
  ChangeDetectionStrategy, Component, ElementRef, computed, effect, inject, input, signal, untracked, viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import {
  Check, CircleCheck, CircleX, Download, FileBraces, FileSpreadsheet, FileText, History, Layers, Plus,
  RotateCcw, Save, SquareDashedMousePointer, TriangleAlert, X, ZoomIn, ZoomOut,
} from 'lucide';
import { api, apiUrl } from '../core/api';
import { DismissDirective } from '../core/dismiss.directive';
import { Icon } from '../core/icon';
import { Store } from '../core/store';
import { AutoFocusDirective } from './review/auto-focus.directive';

type Drag = { x0: number; y0: number; x1: number; y1: number };
type NewField = { label: string; dataType: string; value: string; region: any };
type TemplateForm = { name: string; code: string; useRegions: boolean; fields: Record<string, boolean> };

// Review Studio: the page image with a box around every extracted value on the left, the fields to check,
// fix and approve on the right. Below 1100px wide the two panels stack.
@Component({
  selector: 'app-review',
  imports: [FormsModule, Icon, DismissDirective, AutoFocusDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: block; }
    .review-root { display: flex; flex-direction: column; gap: 16px; }
    .hitl-workspace > * { min-width: 0; }
    .empty-state { padding: 60px; text-align: center; }
    .empty-state app-icon { color: var(--text-muted); margin-bottom: 16px; }
    .empty-state p { color: var(--text-secondary); margin-top: 8px; }
    .error-text { color: var(--danger) !important; }

    .toast {
      background: color-mix(in srgb, var(--success) 15%, transparent); border: 1px solid color-mix(in srgb, var(--success) 40%, transparent); color: var(--success-text);
      padding: 12px 20px; border-radius: var(--radius-md); display: flex; align-items: center; gap: 8px;
      font-weight: 600; font-size: 0.88rem;
    }

    .viewer-toolbar { flex-wrap: wrap; gap: 8px; }
    .tool-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .tool-title { font-size: 0.85rem; font-weight: 600; }
    .sep { width: 1px; height: 18px; background: var(--border-color); margin: 0 4px; }
    .mono { font-size: 0.75rem; font-family: var(--font-mono); }
    .zoom-pct { min-width: 40px; text-align: center; }

    .doc-canvas-container { cursor: crosshair; user-select: none; -webkit-user-select: none; }
    /* Touch drags only draw while the draw tool is on, so on phones the page still scrolls otherwise */
    .doc-canvas-container.drawing { touch-action: none; }
    .page-img { width: 680px; display: block; }
    .draw-box { pointer-events: none; z-index: 5; }

    .inspector-header { gap: 12px; }
    .doc-title { font-size: 1rem; font-weight: 700; overflow-wrap: anywhere; }
    .doc-sub { font-size: 0.75rem; color: var(--text-muted); overflow-wrap: anywhere; }
    .audit-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .audit-head h4 { font-size: 0.9rem; font-weight: 600; }
    .audit-list { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
    .audit-entry {
      padding: 12px; border-radius: var(--radius-sm); background: color-mix(in srgb, var(--tint) 2%, transparent);
      border: 1px solid var(--border-color); font-size: 0.8rem;
    }
    .audit-entry-top { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
    .audit-user { font-weight: 600; color: var(--accent-cyan); }
    .audit-time { color: var(--text-muted); font-size: 0.72rem; }
    .audit-action { color: var(--text-primary); margin-bottom: 4px; }
    .audit-diff {
      font-size: 0.75rem; color: var(--text-secondary); background: color-mix(in srgb, var(--shade) 30%, transparent); padding: 6px;
      border-radius: 4px; overflow-wrap: anywhere;
    }
    .audit-diff .new { color: var(--success-text); }

    .notices {
      padding: 10px 12px; border-radius: var(--radius-sm); background: color-mix(in srgb, var(--warning) 10%, transparent);
      border: 1px solid color-mix(in srgb, var(--warning) 30%, transparent); font-size: 0.78rem; color: var(--warning-text);
    }
    .notice { display: flex; gap: 6px; align-items: flex-start; }
    .notice app-icon { margin-top: 2px; }
    .hint { font-size: 0.75rem; color: var(--text-muted); }
    .small-hint { font-size: 0.72rem; color: var(--text-muted); margin-bottom: 8px; }
    .form-card { cursor: default; }
    .form-card .field-label { display: block; margin-bottom: 8px; }
    .form-card .field-input { margin-bottom: 6px; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
    .tpl-fields { font-size: 0.75rem; color: var(--text-secondary); max-height: 160px; overflow: auto; margin-top: 2px; }
    .check-row { display: flex; gap: 6px; align-items: center; padding: 2px 0; }
    .regions-row { display: flex; gap: 6px; align-items: center; font-size: 0.75rem; margin: 8px 0; color: var(--text-secondary); }
    .no-fields { font-size: 0.8rem; color: var(--text-muted); padding: 12px 0; }

    .field-card { cursor: pointer; }
    .field-card-top { gap: 8px; }
    .field-card-top .field-label { cursor: text; overflow-wrap: anywhere; }
    .rename-input { padding: 3px 6px; font-size: 0.75rem; max-width: 70%; }
    .tag {
      font-size: 0.68rem; color: var(--accent-cyan); background: color-mix(in srgb, var(--accent-cyan) 10%, transparent); padding: 2px 5px; border-radius: 3px;
    }
    .remove-btn { padding: 1px 5px; font-size: 0.68rem; }

    .table-block { border-top: 1px solid var(--border-color); padding-top: 10px; overflow-x: auto; flex-shrink: 0; }
    .table-block .field-label { display: block; margin-bottom: 6px; }
    .table-block .data-table { font-size: 0.72rem; }
    .table-block th, .table-block td { padding: 4px 6px; }
    .entities { font-size: 0.75rem; color: var(--text-secondary); border-top: 1px solid var(--border-color); padding-top: 10px; }
    .entities .field-label { display: block; margin-bottom: 6px; }
    .entities > div { margin-bottom: 4px; overflow-wrap: anywhere; }
    .entities b { text-transform: capitalize; }

    .inspector-footer { flex-wrap: wrap; gap: 8px; }
    .footer-group { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    .rerun-select { width: auto; max-width: 100%; padding: 5px 8px; font-size: 0.75rem; }
    .actions-group { display: flex; gap: 8px; position: relative; flex-wrap: wrap; justify-content: flex-end; }
    /* The formats open as a row of their own under the buttons, so they never cover another control */
    .export-area { display: contents; }
    .export-menu { position: static; order: 10; flex-basis: 100%; display: flex; gap: 6px; justify-content: flex-end;
      flex-wrap: wrap; min-width: 0; padding: 0; background: none; border: 0; box-shadow: none; }
    .popover-menu.export-menu .btn { width: auto; margin-top: 0; }

    @media (max-width: 640px) {
      .viewer-panel { height: 60vh; min-height: 360px; }
      .canvas-scroll-area { padding: 12px; }
      /* The page fits the screen width; boxes are percentages so they stay on their text */
      .doc-canvas-container { width: 100%; }
      .page-img { width: 100%; }
      .inspector-panel { height: auto; }
      .inspector-body { overflow: visible; }
      .inspector-header, .inspector-body, .inspector-footer { padding-left: 14px; padding-right: 14px; }
      .actions-group { justify-content: flex-start; }
      .empty-state { padding: 40px 20px; }
    }
  `,
  template: `
    @if (doc(); as document) {
      <div class="review-root">
        <!-- Toast Banner -->
        @if (actionSuccess()) {
          <div class="toast" role="status">
            <app-icon [icon]="Check" [size]="18" />
            <span>{{ actionSuccess() }}</span>
          </div>
        }

        <!-- Main Review Split Layout -->
        <div class="hitl-workspace">
          <!-- Left Side: Document Visualizer Canvas -->
          <div class="glass-card viewer-panel">
            <div class="viewer-toolbar">
              <div class="tool-group">
                <span class="tool-title">Visual Inspector</span>
                <span class="type-pill" style="text-transform: capitalize">{{ document.doc_type }}</span>
              </div>

              <div class="tool-group">
                <button class="btn btn-sm" [class.btn-primary]="showBoxes()" [class.btn-secondary]="!showBoxes()"
                  (click)="showBoxes.set(!showBoxes())" title="Toggle Bounding Boxes">
                  <app-icon [icon]="Layers" [size]="14" />
                  <span>Boxes {{ showBoxes() ? 'ON' : 'OFF' }}</span>
                </button>

                <button class="btn btn-sm" [class.btn-primary]="addMode()" [class.btn-secondary]="!addMode()"
                  (click)="addMode.set(!addMode())" [attr.aria-pressed]="addMode()"
                  title="Draw a box around a value to add it as a field (with a mouse you can always draw; on a touch screen turn this on first)">
                  <app-icon [icon]="SquareDashedMousePointer" [size]="14" />
                  <span>Draw {{ addMode() ? 'ON' : 'OFF' }}</span>
                </button>

                <button class="btn btn-sm btn-secondary" (click)="startTypedField()"
                  title="Add a field by typing its value (or just draw a box on the page)">
                  <app-icon [icon]="Plus" [size]="14" />
                  <span>Add Field</span>
                </button>

                @if (pageCount() > 1) {
                  <div class="sep"></div>
                  <button class="btn btn-secondary btn-sm" (click)="prevPage()" [disabled]="page() <= 1" title="Previous page">‹</button>
                  <span class="mono">Page {{ page() }}/{{ pageCount() }}</span>
                  <button class="btn btn-secondary btn-sm" (click)="nextPage()" [disabled]="page() >= pageCount()" title="Next page">›</button>
                }

                <div class="sep"></div>

                <button class="btn btn-secondary btn-sm" (click)="zoomOut()" title="Zoom Out">
                  <app-icon [icon]="ZoomOut" [size]="14" />
                </button>
                <span class="mono zoom-pct">{{ zoomPct() }}%</span>
                <button class="btn btn-secondary btn-sm" (click)="zoomIn()" title="Zoom In">
                  <app-icon [icon]="ZoomIn" [size]="14" />
                </button>
                <button class="btn btn-secondary btn-sm" (click)="zoomLevel.set(1)" title="Reset Zoom">
                  <app-icon [icon]="RotateCcw" [size]="14" />
                </button>
              </div>
            </div>

            <div class="canvas-scroll-area">
              <div #canvas class="doc-canvas-container" [class.drawing]="addMode()"
                [style.transform]="'scale(' + zoomLevel() + ')'"
                title="Drag a box around any value to add it as a field"
                (pointerdown)="onPointerDown($event)"
                (pointermove)="onPointerMove($event)"
                (pointerup)="onPointerUp($event)"
                (pointercancel)="cancelDrag()">
                @if (drag(); as d) {
                  <div class="bounding-box-overlay selected draw-box"
                    [style.left.%]="min(d.x0, d.x1)" [style.top.%]="min(d.y0, d.y1)"
                    [style.width.%]="abs(d.x1 - d.x0)" [style.height.%]="abs(d.y1 - d.y0)"></div>
                }
                @if (newField()?.region; as r) {
                  @if (r.page === page()) {
                    <div class="bounding-box-overlay selected draw-box"
                      [style.left.%]="r.x0" [style.top.%]="r.y0"
                      [style.width.%]="r.x1 - r.x0" [style.height.%]="r.y1 - r.y0"></div>
                  }
                }
                @for (url of [pageImageUrl()]; track url) {
                  <img [src]="url" alt="Document Page Preview" class="doc-canvas-img page-img" draggable="false"
                    (error)="hideImage($event)" />
                }

                <!-- Bounding Box Highlights Overlay -->
                @if (showBoxes()) {
                  @for (b of pageBoxes(); track b.key) {
                    <div class="bounding-box-overlay" [class.selected]="selectedField() === b.key" [class.error]="b.hasError"
                      [style.left.%]="b.left" [style.top.%]="b.top" [style.width.%]="b.width" [style.height.%]="b.height"
                      (click)="selectedField.set(b.key)" [title]="b.title">
                      @if (selectedField() === b.key) {
                        <div class="box-label-tag">{{ b.name }} ({{ b.confidence }}%)</div>
                      }
                    </div>
                  }
                }
              </div>
            </div>
          </div>

          <!-- Right Side: Field Inspector & Verification Controls -->
          <div class="glass-card inspector-panel">
            <div class="inspector-header">
              <div>
                <div class="doc-title">{{ document.title }}</div>
                <div class="doc-sub">ID: {{ document.id }} · Score: {{ round(document.overall_confidence * 100) }}%</div>
              </div>
              <div style="display: flex; gap: 8px">
                <button class="btn btn-sm" [class.btn-primary]="showAuditTrail()" [class.btn-secondary]="!showAuditTrail()"
                  (click)="showAuditTrail.set(!showAuditTrail())" title="View Audit Trail History">
                  <app-icon [icon]="History" [size]="14" />
                  <span>Audit</span>
                </button>
              </div>
            </div>

            @if (showAuditTrail()) {
              <!-- Audit Trail Drawer Mode -->
              <div class="inspector-body">
                <div class="audit-head">
                  <h4>Document Audit History</h4>
                  <button class="btn btn-secondary btn-sm" (click)="showAuditTrail.set(false)">Back to Fields</button>
                </div>
                <div class="audit-list">
                  @for (entry of document.audit_trail || []; track $index) {
                    <div class="audit-entry">
                      <div class="audit-entry-top">
                        <span class="audit-user">{{ entry.user }}</span>
                        <span class="audit-time">{{ timeOf(entry.timestamp) }}</span>
                      </div>
                      <div class="audit-action">{{ entry.action }}</div>
                      @if (entry.details?.modified_fields) {
                        <div class="audit-diff">
                          @for (m of entriesOf(entry.details.modified_fields); track m[0]) {
                            <div><b>{{ m[0] }}:</b> "{{ m[1].old }}" → <span class="new">"{{ m[1].new }}"</span></div>
                          }
                        </div>
                      }
                    </div>
                  }
                </div>
              </div>
            } @else {
              <!-- Field Editing List -->
              <div class="inspector-body">
                @if (notices().length > 0) {
                  <div class="notices">
                    @for (n of notices(); track $index) {
                      <div class="notice"><app-icon [icon]="TriangleAlert" [size]="13" /><span>{{ n }}</span></div>
                    }
                  </div>
                }

                <div class="hint">Missing something? Drag a box around it on the page. Click a field name to rename it.</div>

                @if (newField(); as nf) {
                  <div class="field-card active form-card">
                    <div class="field-label">New field</div>
                    <input class="field-input" placeholder="Field name, e.g. Given Names" appAutoFocus
                      [ngModel]="nf.label" (ngModelChange)="patchNewField({ label: $event })" />
                    <select class="field-input" [ngModel]="nf.dataType" (ngModelChange)="patchNewField({ dataType: $event })">
                      <option value="text">Text</option>
                      <option value="date">Date</option>
                      <option value="number">Number</option>
                      <option value="currency">Amount</option>
                      <option value="email">Email</option>
                    </select>
                    <input class="field-input" [placeholder]="nf.region ? 'No text found in the box: type the value' : 'Value'"
                      [ngModel]="nf.value" (ngModelChange)="patchNewField({ value: $event })" />
                    <div class="small-hint">
                      {{ nf.region
                        ? 'Read from the box you drew. A template saved from this document will look in the same place.'
                        : 'Typed value: kept on this document only (optional in templates).' }}
                    </div>
                    <div class="form-actions">
                      <button class="btn btn-secondary btn-sm" (click)="newField.set(null)">Cancel</button>
                      <button class="btn btn-primary btn-sm" (click)="handleAddField()" [disabled]="saving() || !nf.label.trim()">Add Field</button>
                    </div>
                  </div>
                }

                @if (templateForm(); as tf) {
                  <div class="field-card active form-card">
                    <div class="field-label">Save these fields as a template</div>
                    <input class="field-input" placeholder="Template name" [ngModel]="tf.name" (ngModelChange)="patchTemplate({ name: $event })" />
                    <input class="field-input" placeholder="Document type code, e.g. purchase_order" [ngModel]="tf.code"
                      (ngModelChange)="patchTemplate({ code: $event })" />
                    <div class="tpl-fields">
                      @for (f of fieldEntries(); track f[0]) {
                        <label class="check-row">
                          <input type="checkbox" [checked]="!!tf.fields[f[0]]" (change)="toggleTemplateField(f[0], $event)" />
                          <span>{{ f[1].display_name || f[0] }}</span>
                        </label>
                      }
                    </div>
                    <label class="regions-row">
                      <input type="checkbox" [checked]="tf.useRegions" (change)="patchTemplate({ useRegions: checked($event) })" />
                      <span>Also remember where each value sits on the page (fixed-layout forms)</span>
                    </label>
                    <div class="form-actions">
                      <button class="btn btn-secondary btn-sm" (click)="templateForm.set(null)">Cancel</button>
                      <button class="btn btn-primary btn-sm" (click)="handleSaveTemplate()" [disabled]="saving() || !tf.name || !tf.code">Save Template</button>
                    </div>
                  </div>
                }

                @if (document.fields && fieldEntries().length === 0) {
                  <div class="no-fields">No fields were extracted. Re-run with a different pipeline or template below.</div>
                }

                @for (f of fieldEntries(); track f[0]) {
                  @let key = f[0];
                  @let field = f[1];
                  @let conf = round((field.confidence || 0) * 100);
                  <div class="field-card" [class.active]="selectedField() === key" [class.has-error]="!!field.validation_error"
                    (click)="selectedField.set(key)">
                    <div class="field-card-top">
                      @if (editingLabel()?.key === key) {
                        <input class="field-input rename-input" appAutoFocus="select"
                          [ngModel]="editingLabel()!.text" (ngModelChange)="editingLabel.set({ key, text: $event })"
                          (keydown.enter)="handleRename()" (keydown.escape)="editingLabel.set(null)"
                          (blur)="handleRename()" (click)="$event.stopPropagation()" />
                      } @else {
                        <span class="field-label" title="Click to rename" (click)="startRename($event, key, field)">
                          {{ field.display_name || key }}
                        </span>
                      }
                      <div class="field-meta">
                        @if (field.is_manually_edited) {
                          <span class="tag">{{ field.is_manually_added ? 'Added' : 'Edited' }}</span>
                        }
                        @if (field.is_manually_added) {
                          <button class="btn btn-secondary btn-sm remove-btn" title="Remove this field" aria-label="Remove this field"
                            (click)="$event.stopPropagation(); handleRemoveField(key)">
                            <app-icon [icon]="X" [size]="11" />
                          </button>
                        }
                        <span [class]="'confidence-indicator ' + (conf >= 90 ? 'high' : conf >= 75 ? 'medium' : 'low')">{{ conf }}%</span>
                      </div>
                    </div>

                    <div class="field-input-wrapper">
                      <input type="text" class="field-input" placeholder="Not found in document: enter value"
                        [ngModel]="fieldValues()[key] ?? ''" (ngModelChange)="handleFieldChange(key, $event)" />
                    </div>

                    @if (field.validation_error) {
                      <div class="field-error-msg">
                        <app-icon [icon]="TriangleAlert" [size]="14" />
                        <span>{{ field.validation_error }}</span>
                      </div>
                    }
                  </div>
                }

                @for (table of tables(); track $index; let ti = $index) {
                  <div class="table-block">
                    <div class="field-label">Table {{ ti + 1 }} · {{ table.rows.length }} rows (included in CSV export)</div>
                    <table class="data-table">
                      <thead>
                        <tr>@for (c of table.columns; track $index) { <th>{{ c }}</th> }</tr>
                      </thead>
                      <tbody>
                        @for (row of table.rows; track $index) {
                          <tr>@for (cell of row; track $index) { <td>{{ cell }}</td> }</tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }

                @if (entities().length > 0) {
                  <div class="entities">
                    <div class="field-label">Also found in the text</div>
                    @for (e of entities(); track e[0]) {
                      <div><b>{{ e[0] }}:</b> {{ e[1].slice(0, 8).join(' · ') }}</div>
                    }
                  </div>
                }
              </div>
            }

            <!-- Pipeline Actions -->
            <div class="inspector-footer">
              <div class="footer-group">
                <select class="field-input rerun-select" [ngModel]="rerunTarget()" (ngModelChange)="rerunTarget.set($event)"
                  title="Pipeline or template to re-run with">
                  <option value="auto">Auto-detect</option>
                  <option value="generic">General (all labelled values)</option>
                  <option value="contracts">Contracts</option>
                  <option value="identity">Passport / ID</option>
                  <option value="invoices">Invoices</option>
                  @for (s of rerunSchemas(); track s.id) {
                    <option [value]="'schema:' + s.id">Template: {{ s.name }}</option>
                  }
                </select>
                <button class="btn btn-secondary btn-sm" (click)="handleRerun()" [disabled]="saving()">
                  <app-icon [icon]="RotateCcw" [size]="14" />
                  <span>Re-run</span>
                </button>
              </div>
              <div class="footer-group">
                <button class="btn btn-secondary btn-sm" (click)="openTemplateForm()" [disabled]="saving() || !fieldEntries().length"
                  title="Save this document's fields as a reusable template">
                  <app-icon [icon]="Layers" [size]="14" />
                  <span>Save as Template</span>
                </button>
                <button class="btn btn-secondary btn-sm" (click)="handleDelete()" [disabled]="saving()" title="Delete document">
                  <app-icon [icon]="CircleX" [size]="14" />
                  <span>Delete</span>
                </button>
              </div>
            </div>

            <!-- Footer Actions -->
            <div class="inspector-footer">
              <button class="btn btn-secondary btn-sm" (click)="handleSaveFields()" [disabled]="saving()">
                <app-icon [icon]="Save" [size]="14" />
                <span>Save Fields</span>
              </button>

              <div class="actions-group">
                <!-- The dismiss area is just the Export button and its formats -->
                <span class="export-area" [appDismiss]="showExport()" (dismissed)="showExport.set(false)">
                  <button class="btn btn-secondary btn-sm" (click)="showExport.set(!showExport())" [disabled]="saving()"
                    title="Download this document's fields and tables" aria-haspopup="menu" [attr.aria-expanded]="showExport()">
                    <app-icon [icon]="Download" [size]="14" />
                    <span>Export</span>
                  </button>
                  @if (showExport()) {
                    <div role="menu" class="popover-menu export-menu">
                      <button role="menuitem" class="btn btn-secondary btn-sm" (click)="handleExport('xlsx')">
                        <app-icon [icon]="FileSpreadsheet" [size]="14" /><span>Excel (.xlsx)</span>
                      </button>
                      <button role="menuitem" class="btn btn-secondary btn-sm" (click)="handleExport('csv')">
                        <app-icon [icon]="FileText" [size]="14" /><span>CSV</span>
                      </button>
                      <button role="menuitem" class="btn btn-secondary btn-sm" (click)="handleExport('json')">
                        <app-icon [icon]="FileBraces" [size]="14" /><span>JSON</span>
                      </button>
                    </div>
                  }
                </span>
                <button class="btn btn-danger btn-sm" (click)="handleReject()" [disabled]="saving()">
                  <app-icon [icon]="CircleX" [size]="14" />
                  <span>Reject</span>
                </button>
                <button class="btn btn-success btn-sm" (click)="handleApprove()" [disabled]="saving()">
                  <app-icon [icon]="CircleCheck" [size]="14" />
                  <span>Approve (STP)</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    } @else if (loadError()) {
      <div class="glass-card empty-state">
        <app-icon [icon]="FileText" [size]="48" />
        <h3>Document could not be opened</h3>
        <p class="error-text">{{ loadError() }}</p>
      </div>
    } @else if (id()) {
      <div class="glass-card empty-state">
        <app-icon [icon]="FileText" [size]="48" />
        <p>Loading document…</p>
      </div>
    } @else {
      <div class="glass-card empty-state">
        <app-icon [icon]="FileText" [size]="48" />
        <h3>No Document Selected for Review</h3>
        <p>Select a document from the Document Hub to inspect its extracted tokens and perform Human-in-the-Loop verification.</p>
      </div>
    }
  `,
})
export class Review {
  protected readonly store = inject(Store);
  private readonly router = inject(Router);

  /** From the route /review/:id */
  readonly id = input<string>();

  protected readonly Check = Check;
  protected readonly CircleCheck = CircleCheck;
  protected readonly CircleX = CircleX;
  protected readonly Download = Download;
  protected readonly FileBraces = FileBraces;
  protected readonly FileSpreadsheet = FileSpreadsheet;
  protected readonly FileText = FileText;
  protected readonly History = History;
  protected readonly Layers = Layers;
  protected readonly Plus = Plus;
  protected readonly RotateCcw = RotateCcw;
  protected readonly Save = Save;
  protected readonly SquareDashedMousePointer = SquareDashedMousePointer;
  protected readonly TriangleAlert = TriangleAlert;
  protected readonly X = X;
  protected readonly ZoomIn = ZoomIn;
  protected readonly ZoomOut = ZoomOut;

  protected readonly loadError = signal<string | null>(null);

  /** The document on screen: the one in the URL once loaded, else the store's selected document */
  protected readonly doc = computed<any | null>(() => {
    const d = this.store.selectedDoc();
    const id = this.id();
    if (id) return d && String(d.id) === String(id) ? d : null;
    return d;
  });

  protected readonly page = signal(1);
  protected readonly templateForm = signal<TemplateForm | null>(null);
  protected readonly rerunTarget = signal('auto');
  protected readonly zoomLevel = signal(1);
  protected readonly selectedField = signal<string | null>(null);
  protected readonly showBoxes = signal(true);
  protected readonly fieldValues = signal<Record<string, any>>({});
  protected readonly saving = signal(false);
  protected readonly actionSuccess = signal<string | null>(null);
  protected readonly showAuditTrail = signal(false);
  // "Add field" tool: draw a box on the page, then name the field. With a mouse drawing always works;
  // touch drags only draw while this is on, so the page can still be scrolled with a finger otherwise.
  protected readonly addMode = signal(false);
  protected readonly drag = signal<Drag | null>(null);
  protected readonly newField = signal<NewField | null>(null);
  protected readonly editingLabel = signal<{ key: string; text: string } | null>(null);
  protected readonly showExport = signal(false);

  private readonly canvas = viewChild<ElementRef<HTMLElement>>('canvas');
  // The drag lives here as well as in the signal, so fast pointer events never read a stale value. The canvas
  // rectangle is captured at pointer-down, so a toolbar re-layout mid-drag cannot offset the box.
  private dragRef: (Drag & { rect: DOMRect; pointerId: number }) | null = null;
  private selectAfterUpdate: string | null = null;
  private toastTimer: ReturnType<typeof setTimeout> | undefined;
  private lastDocId: unknown = undefined;

  protected readonly fieldEntries = computed<[string, any][]>(() => Object.entries(this.doc()?.fields || {}));
  protected readonly pageCount = computed(() => this.doc()?.page_count || 1);
  protected readonly pageImageUrl = computed(() => {
    const d = this.doc();
    return d ? apiUrl(d.page_urls?.[this.page() - 1] || d.file_url) : '';
  });
  protected readonly zoomPct = computed(() => Math.round(this.zoomLevel() * 100));
  private readonly meta = computed<any>(() => this.doc()?.metadata || {});
  protected readonly notices = computed<string[]>(() => {
    const meta = this.meta();
    return [
      ...(meta.review_reasons || []),
      ...((meta.extraction && meta.extraction.warnings) || []),
      ...(meta.error ? [`Processing failed: ${meta.error}`] : []),
      ...(meta.rejection_reason ? [`Rejected: ${meta.rejection_reason}`] : []),
    ];
  });
  protected readonly entities = computed<[string, any[]][]>(() => {
    const e = this.meta().entities;
    return e ? (Object.entries(e).filter(([, v]: any) => v && v.length) as [string, any[]][]) : [];
  });
  protected readonly tables = computed<any[]>(() => this.meta().tables || []);
  protected readonly rerunSchemas = computed(() =>
    this.store.schemas().filter((s) => !['contracts', 'identity', 'invoices'].includes(s.document_type_code)));

  protected readonly pageBoxes = computed(() => {
    const page = this.page();
    return this.fieldEntries()
      .filter(([, field]) => field.bounding_box && (field.bounding_box.page || 1) === page)
      .map(([key, field]) => {
        const box = field.bounding_box;
        // Hug the value with a small margin (no minimum size, which used to push boxes off their text)
        const pad = 0.25;
        return {
          key,
          hasError: !!field.validation_error,
          left: Math.max(0, box.x0 - pad),
          top: Math.max(0, box.y0 - pad),
          width: box.x1 - box.x0 + pad * 2,
          height: box.y1 - box.y0 + pad * 2,
          title: `${field.display_name || key}: ${field.value ?? ''}`,
          name: field.display_name || key,
          confidence: Math.round(field.confidence * 100),
        };
      });
  });

  constructor() {
    // /review/:id opens that document (a bookmarked or shared link)
    effect(() => {
      const id = this.id();
      this.loadError.set(null);
      if (!id) return;
      untracked(() => {
        this.store.openDocument(id).catch((err: any) => {
          if (this.id() === id) this.loadError.set(err?.message || 'Document not found');
        });
      });
    });

    effect(() => {
      const document = this.doc();
      untracked(() => {
        // Start on page 1 for a new document
        if (document?.id !== this.lastDocId) {
          this.lastDocId = document?.id;
          this.page.set(1);
        }
        if (!document?.fields) return;
        const initial: Record<string, any> = {};
        Object.entries(document.fields).forEach(([k, v]: [string, any]) => { initial[k] = v.value ?? ''; });
        this.fieldValues.set(initial);
        this.templateForm.set(null);
        // Select the field just added or renamed, else the first field with an error, else the first field
        const errField = Object.entries(document.fields).find(([, v]: [string, any]) => v.validation_error);
        if (this.selectAfterUpdate && document.fields[this.selectAfterUpdate]) {
          this.selectedField.set(this.selectAfterUpdate);
          this.selectAfterUpdate = null;
        } else if (errField) {
          this.selectedField.set(errField[0]);
        } else {
          const firstKey = Object.keys(document.fields)[0];
          if (firstKey) this.selectedField.set(firstKey);
        }
      });
    });

    // Follow the selected field to its page
    effect(() => {
      const key = this.selectedField();
      const p = key ? this.doc()?.fields?.[key]?.bounding_box?.page : null;
      if (p) untracked(() => this.page.set(p));
    });
  }

  protected round = Math.round;
  protected min = Math.min;
  protected abs = Math.abs;
  protected entriesOf(o: any): [string, any][] { return Object.entries(o || {}); }
  protected timeOf(ts: string) { return new Date(ts).toLocaleTimeString(); }
  protected checked(e: Event) { return (e.target as HTMLInputElement).checked; }
  protected hideImage(e: Event) { (e.target as HTMLElement).style.display = 'none'; }

  protected prevPage() { this.page.update((p) => Math.max(1, p - 1)); }
  protected nextPage() { this.page.update((p) => Math.min(this.pageCount(), p + 1)); }
  protected zoomOut() { this.zoomLevel.update((z) => Math.max(0.6, z - 0.15)); }
  protected zoomIn() { this.zoomLevel.update((z) => Math.min(2.0, z + 0.15)); }

  private toast(message: string, ms: number) {
    clearTimeout(this.toastTimer);
    this.actionSuccess.set(message);
    this.toastTimer = setTimeout(() => this.actionSuccess.set(null), ms);
  }

  protected handleFieldChange(fieldName: string, newVal: string) {
    this.fieldValues.update((prev) => ({ ...prev, [fieldName]: newVal }));
  }

  // Only fields the reviewer actually changed are sent, so untouched values are not marked as edited
  private changedUpdates(): any {
    const document = this.doc();
    return Object.entries(this.fieldValues())
      .filter(([k, v]) => String(v ?? '') !== String(document.fields[k]?.value ?? ''))
      .map(([field_name, value]) => ({ field_name, value }));
  }

  protected async handleSaveFields() {
    const document = this.doc();
    const updates = this.changedUpdates();
    if (updates.length === 0) {
      this.toast('No changes to save', 2500);
      return;
    }
    this.saving.set(true);
    try {
      const updated = await api.updateFields(document.id, updates);
      this.store.documentUpdated(updated);
      this.toast('Field updates saved & verified successfully', 3500);
    } catch (err: any) {
      alert(`Save error: ${err.message}`);
    } finally {
      this.saving.set(false);
    }
  }

  protected async handleApprove() {
    const document = this.doc();
    this.saving.set(true);
    try {
      // First persist any current field changes
      const updates = this.changedUpdates();
      if (updates.length > 0) await api.updateFields(document.id, updates);
      const updated = await api.approveDocument(document.id);
      this.store.documentUpdated(updated);
      this.toast('Document approved! Downstream webhooks dispatched.', 3500);
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    } finally {
      this.saving.set(false);
    }
  }

  protected async handleReject() {
    const document = this.doc();
    const reason = prompt('Please enter rejection reason:', 'Unreadable or invalid document fields');
    if (!reason) return;
    this.saving.set(true);
    try {
      const updated = await api.rejectDocument(document.id, reason);
      this.store.documentUpdated(updated);
      this.toast('Document rejected.', 3500);
    } catch (err: any) {
      alert(`Rejection error: ${err.message}`);
    } finally {
      this.saving.set(false);
    }
  }

  // Pointer position as a percentage of the page image (works at any zoom level), measured against the
  // rectangle captured when the drag began
  private toPercent(e: PointerEvent, r: DOMRect) {
    return {
      x: Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100)),
      y: Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100)),
    };
  }

  protected onPointerDown(e: PointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (e.pointerType !== 'mouse' && !this.addMode()) return; // a finger scrolls the page unless Draw is on
    if ((e.target as HTMLElement).closest('.bounding-box-overlay')) return; // clicking a box selects its field
    const el = this.canvas()?.nativeElement;
    if (!el) return;
    e.preventDefault();
    const rect = el.getBoundingClientRect();
    const p = this.toPercent(e, rect);
    this.dragRef = { x0: p.x, y0: p.y, x1: p.x, y1: p.y, rect, pointerId: e.pointerId };
    try { el.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
    this.drag.set({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
  }

  protected onPointerMove(e: PointerEvent) {
    const d = this.dragRef;
    if (!d || e.pointerId !== d.pointerId) return;
    const p = this.toPercent(e, d.rect);
    d.x1 = p.x;
    d.y1 = p.y;
    this.drag.set({ x0: d.x0, y0: d.y0, x1: d.x1, y1: d.y1 });
  }

  protected cancelDrag() {
    this.dragRef = null;
    this.drag.set(null);
  }

  // Drawing a box anywhere on the page adds it as a field at once: the text inside becomes the value,
  // the label beside or above it becomes the name (renamable right away on the right)
  protected async onPointerUp(e: PointerEvent) {
    const d = this.dragRef;
    if (!d || e.pointerId !== d.pointerId) return;
    const p = this.toPercent(e, d.rect);
    this.dragRef = null;
    const region = {
      page: this.page(),
      x0: Math.min(d.x0, p.x), y0: Math.min(d.y0, p.y),
      x1: Math.max(d.x0, p.x), y1: Math.max(d.y0, p.y),
    };
    this.drag.set(null);
    if (region.x1 - region.x0 < 0.5 || region.y1 - region.y0 < 0.3) return; // a click, not a box
    const document = this.doc();
    this.saving.set(true);
    try {
      const updates = this.changedUpdates(); // keep unsaved edits: adding a field reloads the document
      if (updates.length > 0) await api.updateFields(document.id, updates);
      const before = new Set(Object.keys(document.fields || {}));
      const updated = await api.addField(document.id, { region, dataType: null });
      const added = Object.keys(updated.fields).find((k) => !before.has(k));
      this.selectAfterUpdate = added || null;
      this.store.documentUpdated(updated);
      if (added) this.editingLabel.set({ key: added, text: updated.fields[added].display_name || added });
    } catch (err: any) {
      alert(`Add field error: ${err.message}`);
    } finally {
      this.saving.set(false);
    }
  }

  protected startTypedField() {
    this.addMode.set(false);
    this.newField.set({ label: '', dataType: 'text', value: '', region: null });
  }

  protected patchNewField(p: Partial<NewField>) {
    this.newField.update((f) => (f ? { ...f, ...p } : f));
  }

  protected patchTemplate(p: Partial<TemplateForm>) {
    this.templateForm.update((t) => (t ? { ...t, ...p } : t));
  }

  protected toggleTemplateField(key: string, e: Event) {
    const on = this.checked(e);
    this.templateForm.update((t) => (t ? { ...t, fields: { ...t.fields, [key]: on } } : t));
  }

  // Saves any unsaved edits first, so the file matches what is on screen
  protected async handleExport(format: string) {
    const document = this.doc();
    this.showExport.set(false);
    try {
      const updates = this.changedUpdates();
      if (updates.length > 0) this.store.documentUpdated(await api.updateFields(document.id, updates));
      const a = window.document.createElement('a');
      a.href = apiUrl(`/api/v1/documents/${document.id}/export/${format}`);
      a.download = '';
      window.document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err: any) {
      alert(`Export error: ${err.message}`);
    }
  }

  protected startRename(e: Event, key: string, field: any) {
    e.stopPropagation();
    this.selectedField.set(key);
    this.editingLabel.set({ key, text: field.display_name || key });
  }

  protected async handleRename() {
    const document = this.doc();
    const edit = this.editingLabel();
    this.editingLabel.set(null);
    if (!edit || !edit.text.trim() || edit.text.trim() === (document.fields[edit.key]?.display_name || edit.key)) return;
    try {
      this.selectAfterUpdate = edit.key;
      this.store.documentUpdated(await api.renameField(document.id, edit.key, edit.text.trim()));
    } catch (err: any) {
      alert(`Rename error: ${err.message}`);
    }
  }

  protected async handleAddField() {
    const document = this.doc();
    const nf = this.newField();
    if (!nf?.label?.trim()) return;
    this.saving.set(true);
    try {
      // Keep unsaved edits: adding a field reloads the document
      const updates = this.changedUpdates();
      if (updates.length > 0) await api.updateFields(document.id, updates);
      const updated = await api.addField(document.id, {
        label: nf.label.trim(),
        dataType: nf.dataType,
        value: nf.value || null,
        region: nf.region,
      });
      this.store.documentUpdated(updated);
      this.newField.set(null);
      this.toast(`Field '${nf.label.trim()}' added. Save as Template to reuse it on similar documents.`, 4000);
    } catch (err: any) {
      alert(`Add field error: ${err.message}`);
    } finally {
      this.saving.set(false);
    }
  }

  protected async handleRemoveField(fieldName: string) {
    if (!confirm('Remove this field from the document?')) return;
    try {
      this.store.documentUpdated(await api.removeField(this.doc().id, fieldName));
    } catch (err: any) {
      alert(`Remove error: ${err.message}`);
    }
  }

  protected async handleSaveTemplate() {
    const document = this.doc();
    const tf = this.templateForm();
    if (!tf?.name || !tf?.code) return;
    this.saving.set(true);
    try {
      const fieldNames = Object.keys(document.fields).filter((k) => tf.fields[k]);
      const schema = await api.createSchemaFromDocument(document.id, {
        name: tf.name,
        documentTypeCode: tf.code,
        fieldNames,
        useRegions: tf.useRegions,
      });
      this.store.schemaCreated(schema);
      this.templateForm.set(null);
      this.toast(`Template '${schema.name}' saved. Matching documents will use it automatically.`, 4500);
    } catch (err: any) {
      alert(`Template error: ${err.message}`);
    } finally {
      this.saving.set(false);
    }
  }

  protected openTemplateForm() {
    const document = this.doc();
    const fields: Record<string, boolean> = {};
    Object.entries(document.fields).forEach(([k, f]: [string, any]) => {
      fields[k] = f.value !== null && f.value !== undefined && f.value !== '';
    });
    this.templateForm.set({
      name: document.title,
      code: document.title.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 40),
      useRegions: true,
      fields,
    });
  }

  protected async handleRerun() {
    const document = this.doc();
    const target = this.rerunTarget();
    this.saving.set(true);
    try {
      const isSchema = target.startsWith('schema:');
      const updated = await api.reprocessDocument(document.id, {
        docType: isSchema ? 'custom' : target,
        schemaId: isSchema ? target.slice(7) : null,
      });
      this.store.documentUpdated(updated);
      this.toast('Extraction re-run.', 3000);
    } catch (err: any) {
      alert(`Re-run error: ${err.message}`);
    } finally {
      this.saving.set(false);
    }
  }

  protected async handleDelete() {
    const document = this.doc();
    if (!confirm(`Delete "${document.title}" and its extracted data? This cannot be undone.`)) return;
    try {
      await api.deleteDocument(document.id);
      this.store.documentsDeleted([document.id]);
      this.router.navigate(['/documents']);
    } catch (err: any) {
      alert(`Delete error: ${err.message}`);
    }
  }
}
