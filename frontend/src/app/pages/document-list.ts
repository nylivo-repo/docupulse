import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NgTemplateOutlet } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { map } from 'rxjs';
import {
  AlertCircle, CheckCircle, ChevronRight, Clock, Download, Eye, FileSpreadsheet, FileText, Folder, FolderOpen, FolderPlus, House,
  Pencil, Plus, Search, Star, Trash2, UploadCloud, X,
} from 'lucide';
import { DismissDirective } from '../core/dismiss.directive';
import { api, apiUrl } from '../core/api';
import { Icon } from '../core/icon';
import { Store, type Doc } from '../core/store';

const FAVORITE_SLOTS = 3; // same limit as the API (folders.MAX_FAVORITES)

// The document list: used as the /documents page and embedded in the dashboard (it reads the documents
// from the Store). On the /documents page ([browse]="true") it works like Finder: folders first, a path
// to click back up, documents dragged onto a folder (or a path segment) move there, and searching looks
// in every folder. The open folder is in the address (?folder=<id>), so Back/Forward and links work.
// On phones the rows become stacked cards.
@Component({
  selector: 'app-document-list',
  imports: [Icon, NgTemplateOutlet, DismissDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: block; }
    .controls { padding: 20px 24px; border-bottom: 1px solid var(--border-color); display: flex; flex-wrap: wrap;
      gap: 16px; align-items: center; justify-content: space-between; }
    .type-filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .fav { max-width: 200px; }
    .fav span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .fav-slot { position: relative; display: inline-flex; }
    .fav-unpin { display: inline-flex; margin-left: 2px; padding: 2px; border-radius: 4px; opacity: 0.7; }
    .fav-unpin:hover { opacity: 1; background: color-mix(in srgb, var(--tint) 10%, transparent); }
    .fav-empty { border-style: dashed !important; color: var(--text-muted) !important; background: transparent !important; }
    .fav-picker { left: 0; right: auto; top: calc(100% + 6px); max-height: 280px; overflow-y: auto; min-width: 240px; }
    .fav-picker .hint { font-size: 0.75rem; color: var(--text-muted); padding: 6px 8px; }
    .star-on { color: var(--warning-text); }
    .search-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .search-box { position: relative; }
    .search-box app-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }
    .search-input { width: 220px; padding: 6px 12px 6px 32px; }
    .status-select { width: 140px; padding: 6px 10px; cursor: pointer; }
    .bulk-bar { padding: 10px 24px; display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
      border-bottom: 1px solid var(--border-color); background: color-mix(in srgb, var(--danger) 6%, transparent); }
    .bulk-bar .count { font-size: 0.85rem; font-weight: 600; }
    .check { cursor: pointer; transform: scale(1.15); }
    tr.checked td, .doc-card.checked { background: color-mix(in srgb, var(--danger) 6%, transparent); }
    tr.selected td, .doc-card.selected { background: color-mix(in srgb, var(--primary) 8%, transparent); }
    .empty { text-align: center; padding: 40px; color: var(--text-muted); }
    .doc-cell { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .doc-icon { width: 32px; height: 32px; flex-shrink: 0; border-radius: 6px; background: color-mix(in srgb, var(--tint) 5%, transparent);
      display: flex; align-items: center; justify-content: center; color: var(--accent-cyan); }
    .doc-title { font-weight: 600; font-size: 0.88rem; }
    .doc-meta { font-size: 0.72rem; color: var(--text-muted); }
    .conf { display: flex; align-items: center; gap: 8px; }
    .conf-bar { width: 48px; height: 5px; background: color-mix(in srgb, var(--tint) 8%, transparent); border-radius: 999px; overflow: hidden; }
    .conf-bar > div { height: 100%; }
    .conf-bar .high { background: var(--success); }
    .conf-bar .medium { background: var(--warning); }
    .conf-bar .low { background: var(--danger); }
    .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    /* Folders (Finder-style) */
    .hub-bar { padding: 14px 24px; border-bottom: 1px solid var(--border-color); display: flex; flex-wrap: wrap; gap: 10px;
      align-items: center; justify-content: space-between; }
    .crumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; min-width: 0; font-size: 0.9rem; }
    .crumb { background: none; border: 1px dashed transparent; color: var(--text-secondary); font: inherit; cursor: pointer;
      padding: 4px 8px; border-radius: var(--radius-sm); display: inline-flex; align-items: center; gap: 6px; max-width: 220px; }
    .crumb span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .crumb:hover { color: var(--text-primary); background: color-mix(in srgb, var(--tint) 5%, transparent); }
    .crumb.here { color: var(--text-primary); font-weight: 700; cursor: default; }
    .crumb-sep { color: var(--text-muted); }
    .hub-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .folder-icon { color: var(--primary-text); background: color-mix(in srgb, var(--primary) 12%, transparent); }
    .folder-name { background: none; border: 0; padding: 0; font: inherit; color: var(--text-primary); cursor: pointer; text-align: left;
      max-width: 100%; }
    .folder-name:hover { text-decoration: underline; }
    tr.folder-row td, .doc-card.folder-card { cursor: default; }
    .drop-target { outline: 2px dashed var(--primary); outline-offset: -2px; background: color-mix(in srgb, var(--primary) 10%, transparent) !important; }
    tr[draggable="true"] { cursor: grab; }
    .name-input { padding: 5px 8px; font-size: 0.88rem; width: 100%; max-width: 320px; }
    .where { color: var(--primary-text); }
    .move-select { width: auto; padding: 5px 8px; font-size: 0.8rem; }
    .drag-hint { font-size: 0.72rem; color: var(--text-muted); }

    /* Phone layout: stacked cards instead of the table */
    .doc-cards { display: none; }
    .doc-card { padding: 14px 16px; border-bottom: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 10px; }
    .card-top { display: flex; gap: 10px; align-items: flex-start; min-width: 0; }
    .card-top .check { margin-top: 4px; }
    .card-name { min-width: 0; flex: 1; }
    .card-tags { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .card-actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
    .card-actions .btn { justify-content: center; padding: 6px 4px; }
    .cards-head { padding: 10px 16px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center;
      gap: 10px; font-size: 0.8rem; color: var(--text-secondary); }

    @media (max-width: 640px) {
      .hub-bar { padding: 12px 16px; }
      .hub-actions { width: 100%; }
      .hub-actions .btn { flex: 1; justify-content: center; }
      .drag-hint { display: none; }
      .card-actions.folder-actions { grid-template-columns: repeat(4, minmax(0, 1fr)); }
      .fav { max-width: 150px; }
      .controls { padding: 14px 16px; gap: 12px; }
      .search-row, .search-box { width: 100%; }
      .search-box { flex: 1 1 180px; }
      .search-input { width: 100%; }
      .status-select { flex: 1 1 120px; }
      .bulk-bar { padding: 10px 16px; }
      .doc-table-wrap { display: none; }
      .doc-cards { display: block; }
    }
  `,
  template: `
    <div class="glass-card" style="padding:0">
      @if (browse()) {
        <!-- Where you are, and folder actions. Path segments are drop targets too. -->
        <div class="hub-bar">
          <nav class="crumbs" aria-label="Folder path">
            <button class="crumb" [class.here]="!current()" (click)="openFolder(null)"
              [class.drop-target]="dropOn() === 'root'" (dragover)="allowDrop($event, 'root')" (dragleave)="dropOn.set(null)" (drop)="dropInto($event, null)">
              <app-icon [icon]="House" [size]="15" /><span>All Documents</span>
            </button>
            @for (f of breadcrumb(); track f.id; let last = $last) {
              <span class="crumb-sep"><app-icon [icon]="ChevronRight" [size]="14" /></span>
              <button class="crumb" [class.here]="last" (click)="openFolder(f.id)" [title]="f.name"
                [class.drop-target]="dropOn() === f.id" (dragover)="allowDrop($event, f.id)" (dragleave)="dropOn.set(null)" (drop)="dropInto($event, f.id)">
                <app-icon [icon]="last ? FolderOpen : Folder" [size]="15" /><span>{{ f.name }}</span>
              </button>
            }
          </nav>
          <div class="hub-actions">
            <span class="drag-hint">Drag documents onto a folder to move them</span>
            <button class="btn btn-secondary btn-sm" (click)="startNewFolder()"><app-icon [icon]="FolderPlus" [size]="14" /><span>New Folder</span></button>
            <button class="btn btn-primary btn-sm" (click)="openUploadModal()"><app-icon [icon]="UploadCloud" [size]="14" /><span>Upload here</span></button>
          </div>
        </div>
      }

      <!-- Controls Header -->
      <div class="controls">
        <!-- All Documents, up to 3 favourite folders (empty slots invite pinning one), Templates -->
        <div class="type-filters">
          <button class="btn btn-sm" [class.btn-primary]="tab() === 'all'" [class.btn-secondary]="tab() !== 'all'" (click)="showAll()">All Documents</button>
          @for (slot of favSlots(); track $index) {
            @if (slot) {
              <button class="btn btn-sm fav" [class.btn-primary]="tab() === slot.id" [class.btn-secondary]="tab() !== slot.id"
                (click)="openFavorite(slot.id)" [title]="'Open ' + store.folderLabel(slot.id)">
                <app-icon [icon]="Star" [size]="13" /><span>{{ slot.name }}</span>
                <span class="fav-unpin" role="button" tabindex="0" title="Remove from favourites" aria-label="Remove from favourites"
                  (click)="$event.stopPropagation(); setFavorite(slot.id, false)"
                  (keydown.enter)="$event.stopPropagation(); setFavorite(slot.id, false)"><app-icon [icon]="X" [size]="12" /></span>
              </button>
            } @else {
              <div class="fav-slot" [appDismiss]="pickerSlot() === $index" (dismissed)="pickerSlot.set(null)">
                <button class="btn btn-sm btn-secondary fav-empty" (click)="pickerSlot.set(pickerSlot() === $index ? null : $index)"
                  aria-haspopup="menu" [attr.aria-expanded]="pickerSlot() === $index" title="Pin a folder here">
                  <app-icon [icon]="Plus" [size]="13" /><span>Favourite folder</span>
                </button>
                @if (pickerSlot() === $index) {
                  <div class="popover-menu fav-picker" role="menu">
                    @for (f of pinnable(); track f.id) {
                      <button role="menuitem" class="btn btn-secondary btn-sm" (click)="pickerSlot.set(null); setFavorite(f.id, true)">
                        <app-icon [icon]="Folder" [size]="14" /><span>{{ f.label }}</span>
                      </button>
                    } @empty {
                      <div class="hint">No folders to pin yet. Create one with New Folder in the Document Hub.</div>
                    }
                  </div>
                }
              </div>
            }
          }
          <button class="btn btn-sm" [class.btn-primary]="tab() === 'templates'" [class.btn-secondary]="tab() !== 'templates'"
            (click)="typeFilter.set('custom')" title="Documents read with a template, in every folder">Templates</button>
        </div>

        <!-- Search & Status Filter -->
        <div class="search-row">
          <div class="search-box">
            <app-icon [icon]="Search" [size]="16" />
            <input type="text" placeholder="Search filename or title..." class="field-input search-input"
              [value]="searchQuery()" (input)="searchQuery.set($any($event.target).value)" />
          </div>
          <select class="field-input status-select" [value]="statusFilter()" (change)="statusFilter.set($any($event.target).value)">
            <option value="all">All Statuses</option>
            <option value="needs_review">Needs Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      <!-- Bulk actions for the checked rows -->
      @if (visibleChecked().length > 0) {
        <div class="bulk-bar">
          <span class="count">{{ visibleChecked().length }} selected</span>
          <button class="btn btn-danger btn-sm" (click)="deleteDocs(visibleChecked())" [disabled]="deleting()">
            <app-icon [icon]="Trash2" [size]="14" />
            <span>{{ deleting() ? 'Deleting…' : 'Delete ' + visibleChecked().length }}</span>
          </button>
          <select class="field-input move-select" aria-label="Move the selected documents to a folder" [disabled]="deleting()"
            (change)="moveChecked($any($event.target)); ">
            <option value="" selected disabled>Move to…</option>
            <option value="__top">No folder (top level)</option>
            @for (f of folderOptions(); track f.id) { <option [value]="f.id">{{ f.label }}</option> }
          </select>
          <button class="btn btn-secondary btn-sm" (click)="checked.set(emptySet())" [disabled]="deleting()">Clear selection</button>
        </div>
      }

      <!-- Table Container -->
      <!-- Fixed-layout table sized to its container: long names are cut with "…" (full text on hover),
           pages/size/date sit under the name, and action labels hide on narrow widths (see .doc-table CSS) -->
      <div class="table-container doc-table-wrap">
        <table class="data-table doc-table">
          <colgroup>
            <col class="c-check" /><col class="c-doc" /><col class="c-type" /><col class="c-status" /><col class="c-conf" /><col class="c-actions" />
          </colgroup>
          <thead>
            <tr>
              <th>
                <input type="checkbox" class="check" [checked]="allVisibleChecked()" (change)="toggleAll()" [disabled]="filteredDocs().length === 0"
                  aria-label="Select all shown documents" title="Select all shown documents" />
              </th>
              <th>Document</th>
              <th>Type</th>
              <th>Status</th>
              <th>Confidence</th>
              <th style="text-align:right">Actions</th>
            </tr>
          </thead>
          <tbody>
            @if (editing()?.mode === 'new') {
              <tr class="folder-row">
                <td></td>
                <td colspan="5"><ng-container *ngTemplateOutlet="nameEditor" /></td>
              </tr>
            }
            @for (f of subfolders(); track f.id) {
              <tr class="folder-row" [class.drop-target]="dropOn() === f.id" (dblclick)="openFolder(f.id)"
                draggable="true" (dragstart)="dragFolder($event, f.id)" (dragend)="dragEnd()"
                (dragover)="allowDrop($event, f.id)" (dragleave)="dropOn.set(null)" (drop)="dropInto($event, f.id)">
                <td></td>
                <td>
                  @if (editing()?.id === f.id) {
                    <ng-container *ngTemplateOutlet="nameEditor" />
                  } @else {
                    <div class="doc-cell">
                      <div class="doc-icon folder-icon"><app-icon [icon]="Folder" [size]="16" /></div>
                      <div style="min-width:0">
                        <button class="truncate doc-title folder-name" (click)="openFolder(f.id)" [title]="'Open ' + f.name">{{ f.name }}</button>
                        <div class="truncate doc-meta">{{ folderMeta(f) }}</div>
                      </div>
                    </div>
                  }
                </td>
                <td><span class="type-pill">Folder</span></td>
                <td></td>
                <td></td>
                <td style="text-align:right"><div class="row-actions"><ng-container *ngTemplateOutlet="folderButtons; context: { $implicit: f }" /></div></td>
              </tr>
            }
            @for (doc of filteredDocs(); track doc.id) {
              <tr [attr.draggable]="browse() ? 'true' : null" (dragstart)="dragDocs($event, doc.id)" (dragend)="dragEnd()"
                [class.checked]="checked().has(doc.id)" [class.selected]="!checked().has(doc.id) && selectedDocId() === doc.id">
                <td>
                  <input type="checkbox" class="check" [checked]="checked().has(doc.id)" (change)="toggle(doc.id)" [attr.aria-label]="'Select ' + doc.title" />
                </td>
                <td>
                  <div class="doc-cell">
                    <div class="doc-icon"><app-icon [icon]="FileText" [size]="16" /></div>
                    <div style="min-width:0">
                      <div class="truncate doc-title" [title]="doc.title">{{ doc.title }}</div>
                      <div class="truncate doc-meta" [title]="metaTitle(doc)">{{ metaLine(doc) }}</div>
                    </div>
                  </div>
                </td>
                <td><span class="type-pill">{{ typeLabel(doc.doc_type) }}</span></td>
                <td><ng-container *ngTemplateOutlet="statusBadge; context: { $implicit: doc.status }" /></td>
                <td><ng-container *ngTemplateOutlet="confidence; context: { $implicit: doc }" /></td>
                <td style="text-align:right">
                  <ng-container *ngTemplateOutlet="actions; context: { $implicit: doc }" />
                </td>
              </tr>
            } @empty {
              @if (!subfolders().length && editing()?.mode !== 'new') {
                <tr><td colspan="6" class="empty">{{ emptyText() }}</td></tr>
              }
            }
          </tbody>
        </table>
      </div>

      <!-- Phones: the same rows as stacked cards -->
      <div class="doc-cards">
        @if (filteredDocs().length > 0) {
          <label class="cards-head">
            <input type="checkbox" class="check" [checked]="allVisibleChecked()" (change)="toggleAll()" aria-label="Select all shown documents" />
            <span>Select all shown documents</span>
          </label>
        }
        @if (editing()?.mode === 'new') {
          <div class="doc-card folder-card"><ng-container *ngTemplateOutlet="nameEditor" /></div>
        }
        @for (f of subfolders(); track f.id) {
          <div class="doc-card folder-card">
            @if (editing()?.id === f.id) {
              <ng-container *ngTemplateOutlet="nameEditor" />
            } @else {
              <div class="card-top">
                <div class="doc-icon folder-icon"><app-icon [icon]="Folder" [size]="16" /></div>
                <div class="card-name">
                  <button class="truncate doc-title folder-name" (click)="openFolder(f.id)">{{ f.name }}</button>
                  <div class="truncate doc-meta">{{ folderMeta(f) }}</div>
                </div>
              </div>
              <div class="card-actions folder-actions"><ng-container *ngTemplateOutlet="folderButtons; context: { $implicit: f }" /></div>
            }
          </div>
        }
        @for (doc of filteredDocs(); track doc.id) {
          <div class="doc-card" [class.checked]="checked().has(doc.id)" [class.selected]="!checked().has(doc.id) && selectedDocId() === doc.id">
            <div class="card-top">
              <input type="checkbox" class="check" [checked]="checked().has(doc.id)" (change)="toggle(doc.id)" [attr.aria-label]="'Select ' + doc.title" />
              <div class="doc-icon"><app-icon [icon]="FileText" [size]="16" /></div>
              <div class="card-name">
                <div class="truncate doc-title" [title]="doc.title">{{ doc.title }}</div>
                <div class="truncate doc-meta" [title]="metaTitle(doc)">{{ metaLine(doc) }}</div>
              </div>
            </div>
            <div class="card-tags">
              <span class="type-pill">{{ typeLabel(doc.doc_type) }}</span>
              <ng-container *ngTemplateOutlet="statusBadge; context: { $implicit: doc.status }" />
              <ng-container *ngTemplateOutlet="confidence; context: { $implicit: doc }" />
            </div>
            <div class="card-actions">
              <ng-container *ngTemplateOutlet="actionButtons; context: { $implicit: doc }" />
            </div>
          </div>
        } @empty {
          @if (!subfolders().length && editing()?.mode !== 'new') {
            <div class="empty">{{ emptyText() }}</div>
          }
        }
      </div>
    </div>

    <ng-template #nameEditor>
      <div class="doc-cell">
        <div class="doc-icon folder-icon"><app-icon [icon]="Folder" [size]="16" /></div>
        <input class="field-input name-input" [value]="editing()!.name" aria-label="Folder name" #nameBox
          (keydown.enter)="saveName(nameBox.value)" (keydown.escape)="editing.set(null)" (blur)="saveName(nameBox.value)" />
      </div>
    </ng-template>

    <ng-template #folderButtons let-f>
      <button class="btn btn-secondary btn-sm" (click)="setFavorite(f.id, !f.favorite)"
        [title]="f.favorite ? 'Remove from favourites' : 'Add to favourites'" [attr.aria-label]="f.favorite ? 'Remove from favourites' : 'Add to favourites'">
        <app-icon [icon]="Star" [size]="14" [class.star-on]="f.favorite" /><span class="act-label">{{ f.favorite ? 'Unpin' : 'Favourite' }}</span>
      </button>
      <button class="btn btn-secondary btn-sm" (click)="openFolder(f.id)" title="Open" aria-label="Open">
        <app-icon [icon]="FolderOpen" [size]="14" /><span class="act-label">Open</span>
      </button>
      <button class="btn btn-secondary btn-sm" (click)="startRename(f)" title="Rename" aria-label="Rename">
        <app-icon [icon]="Pencil" [size]="14" /><span class="act-label">Rename</span>
      </button>
      <button class="btn btn-danger btn-sm" (click)="deleteFolder(f)" title="Delete folder (its contents move up)" aria-label="Delete folder">
        <app-icon [icon]="Trash2" [size]="14" /><span class="act-label">Delete</span>
      </button>
    </ng-template>

    <ng-template #statusBadge let-status>
      @switch (status) {
        @case ('approved') { <span class="badge badge-approved"><app-icon [icon]="CheckCircle" [size]="12" /> Approved (STP)</span> }
        @case ('needs_review') { <span class="badge badge-needs_review"><app-icon [icon]="AlertCircle" [size]="12" /> Needs Review</span> }
        @case ('rejected') { <span class="badge badge-rejected">Rejected</span> }
        @case ('failed') { <span class="badge badge-rejected"><app-icon [icon]="AlertCircle" [size]="12" /> Failed</span> }
        @default { <span class="badge badge-processing"><app-icon [icon]="Clock" [size]="12" /> Processing</span> }
      }
    </ng-template>

    <ng-template #confidence let-doc>
      <div class="conf">
        <span class="confidence-indicator" [class]="confClass(doc)">{{ confPercent(doc) }}%</span>
        <div class="conf-bar"><div [class]="confClass(doc)" [style.width.%]="confPercent(doc)"></div></div>
      </div>
    </ng-template>

    <ng-template #actions let-doc>
      <div class="row-actions">
        <ng-container *ngTemplateOutlet="actionButtons; context: { $implicit: doc }" />
      </div>
    </ng-template>

    <ng-template #actionButtons let-doc>
      <button class="btn btn-secondary btn-sm" (click)="selectDocument(doc.id)" title="Review" aria-label="Review">
        <app-icon [icon]="Eye" [size]="14" /><span class="act-label">Review</span>
      </button>
      <a [href]="exportUrl(doc.id, 'json')" download class="btn btn-secondary btn-sm" title="Download JSON" aria-label="Download JSON">
        <app-icon [icon]="Download" [size]="14" /><span class="act-label">JSON</span>
      </a>
      <a [href]="exportUrl(doc.id, 'csv')" download class="btn btn-secondary btn-sm" title="Download CSV (fields and tables)" aria-label="Download CSV">
        <app-icon [icon]="FileSpreadsheet" [size]="14" /><span class="act-label">CSV</span>
      </a>
      <button class="btn btn-danger btn-sm" (click)="deleteDocs([doc.id])" [disabled]="deleting()" title="Delete" aria-label="Delete">
        <app-icon [icon]="Trash2" [size]="14" /><span class="act-label">Delete</span>
      </button>
    </ng-template>
  `,
})
export class DocumentList {
  protected readonly Search = Search; protected readonly Trash2 = Trash2; protected readonly FileText = FileText;
  protected readonly CheckCircle = CheckCircle; protected readonly AlertCircle = AlertCircle; protected readonly Clock = Clock;
  protected readonly Eye = Eye; protected readonly Download = Download; protected readonly FileSpreadsheet = FileSpreadsheet;
  protected readonly Folder = Folder; protected readonly FolderOpen = FolderOpen; protected readonly FolderPlus = FolderPlus;
  protected readonly House = House; protected readonly ChevronRight = ChevronRight; protected readonly Pencil = Pencil;
  protected readonly UploadCloud = UploadCloud; protected readonly Star = Star; protected readonly Plus = Plus; protected readonly X = X;

  /** Finder-style folder browsing (the /documents page); off in the dashboard's list */
  readonly browse = input(false);
  private readonly route = inject(ActivatedRoute);
  private readonly folderParam = toSignal(this.route.queryParamMap.pipe(map((p) => p.get('folder'))),
    { initialValue: this.route.snapshot.queryParamMap.get('folder') });
  /** The open folder (null = top level) */
  protected readonly current = computed(() => (this.browse() ? this.folderParam() || null : null));
  protected readonly breadcrumb = computed(() => this.store.folderPath(this.current()));
  protected readonly editing = signal<{ mode: 'new' | 'rename'; id?: string; name: string } | null>(null);
  protected readonly dropOn = signal<string | null>(null);
  private dragging: { docs?: string[]; folder?: string } | null = null;
  protected readonly folderOptions = computed(() =>
    this.store.folders().map((f) => ({ id: f.id, label: this.store.folderLabel(f.id) })).sort((a, b) => a.label.localeCompare(b.label)));
  /** Folders inside the open one; while searching, every folder whose name matches */
  protected readonly subfolders = computed(() => {
    if (!this.browse()) return [];
    const q = this.searchQuery().toLowerCase();
    if (q) return this.store.folders().filter((f) => f.name.toLowerCase().includes(q));
    if (this.typeFilter() !== 'all' || this.statusFilter() !== 'all') return [];
    return this.store.folders().filter((f) => (f.parent_id || null) === this.current());
  });

  protected readonly store = inject(Store);
  private readonly router = inject(Router);
  /** Favourite folders in pin order, padded with empty slots */
  protected readonly favSlots = computed(() => {
    const favs = this.store.folders().filter((f) => f.favorite).sort((a, b) => a.favorite_rank - b.favorite_rank);
    return [...favs.slice(0, FAVORITE_SLOTS), ...Array(Math.max(0, FAVORITE_SLOTS - favs.length)).fill(null)];
  });
  protected readonly pinnable = computed(() =>
    this.store.folders().filter((f) => !f.favorite).map((f) => ({ id: f.id, label: this.store.folderLabel(f.id) }))
      .sort((a, b) => a.label.localeCompare(b.label)));
  protected readonly pickerSlot = signal<number | null>(null);
  /** Which tab is lit: Templates, a favourite folder that is open, or All Documents at the top level */
  protected readonly tab = computed(() => {
    if (this.typeFilter() === 'custom') return 'templates';
    const here = this.current();
    if (here) return this.store.folders().some((f) => f.favorite && f.id === here) ? here : null;
    return 'all';
  });

  protected readonly typeFilter = signal('all');
  protected readonly statusFilter = signal('all');
  protected readonly searchQuery = signal('');
  protected readonly checked = signal<Set<string>>(new Set());
  protected readonly deleting = signal(false);

  protected readonly documents = computed(() => this.store.documents());
  protected readonly selectedDocId = computed(() => this.store.selectedDoc()?.id);

  protected readonly filteredDocs = computed(() => {
    const type = this.typeFilter();
    const status = this.statusFilter();
    const q = this.searchQuery().toLowerCase();
    const browse = this.browse();
    const here = this.current();
    return this.documents().filter((doc: Doc) => {
      // In the hub, a folder shows only its own documents; a search looks in every folder
      if (browse && !q && type !== 'custom' && (doc.folder_id || null) !== here) return false;
      if (type !== 'all' && doc.doc_type !== type) return false;
      if (status !== 'all' && doc.status !== status) return false;
      if (q) {
        const matchTitle = doc.title?.toLowerCase().includes(q);
        const matchFile = doc.file_name?.toLowerCase().includes(q);
        if (!matchTitle && !matchFile) return false;
      }
      return true;
    });
  });
  protected readonly visibleChecked = computed(() => {
    const checked = this.checked();
    return this.filteredDocs().filter((d: Doc) => checked.has(d.id)).map((d: Doc) => d.id as string);
  });
  protected readonly allVisibleChecked = computed(
    () => this.filteredDocs().length > 0 && this.visibleChecked().length === this.filteredDocs().length,
  );

  constructor() {
    // New uploads go to the folder open here; leaving the hub resets that to the top level
    effect(() => {
      if (this.browse()) this.store.currentFolder.set(this.current());
    });
    inject(DestroyRef).onDestroy(() => {
      if (this.browse()) this.store.currentFolder.set(null);
    });
  }

  protected emptyText() {
    if (this.searchQuery() || this.typeFilter() !== 'all' || this.statusFilter() !== 'all') return 'No documents found matching the filter criteria.';
    return this.browse() && this.current() ? 'This folder is empty. Upload here, or drag documents onto it.' : 'No documents yet.';
  }

  showAll() {
    this.typeFilter.set('all');
    if (this.browse()) this.openFolder(null);
  }

  openFavorite(id: string) {
    this.typeFilter.set('all');
    this.openFolder(id);
  }

  async setFavorite(id: string, favorite: boolean) {
    try {
      await api.favoriteFolder(id, favorite);
      await this.store.refreshFolders();
    } catch (err: any) {
      alert(err.message);
    }
  }

  openFolder(id: string | null) {
    this.editing.set(null);
    this.checked.set(new Set());
    this.router.navigate(['/documents'], { queryParams: id ? { folder: id } : {} });
  }

  protected folderMeta(f: any) {
    const parts = [`${f.document_count} document${f.document_count === 1 ? '' : 's'}`];
    if (f.folder_count) parts.push(`${f.folder_count} folder${f.folder_count === 1 ? '' : 's'}`);
    if (this.searchQuery() && f.parent_id) parts.push(`in ${this.store.folderLabel(f.parent_id)}`);
    return parts.join(' · ');
  }

  startNewFolder() {
    this.searchQuery.set('');
    this.typeFilter.set('all');
    this.statusFilter.set('all');
    this.editing.set({ mode: 'new', name: this.untitledName() });
    this.focusNameBox();
  }

  startRename(f: any) {
    this.editing.set({ mode: 'rename', id: f.id, name: f.name });
    this.focusNameBox();
  }

  private focusNameBox() {
    setTimeout(() => {
      const box = document.querySelector<HTMLInputElement>('.name-input');
      box?.focus();
      box?.select();
    });
  }

  private untitledName() {
    const taken = new Set(this.store.folders().filter((f) => (f.parent_id || null) === this.current()).map((f) => f.name.toLowerCase()));
    let name = 'untitled folder';
    for (let n = 2; taken.has(name); n++) name = `untitled folder ${n}`;
    return name;
  }

  // Enter or clicking away saves (like Finder); Escape cancels
  async saveName(value: string) {
    const edit = this.editing();
    if (!edit) return;
    this.editing.set(null);
    const name = value.trim();
    if (!name || (edit.mode === 'rename' && name === edit.name)) return;
    try {
      if (edit.mode === 'new') await api.createFolder(name, this.current());
      else await api.renameFolder(edit.id!, name);
      await this.store.refreshFolders();
    } catch (err: any) {
      alert(err.message);
    }
  }

  async deleteFolder(f: any) {
    const where = f.parent_id ? `"${this.store.folderLabel(f.parent_id)}"` : 'the top level';
    const inside = f.document_count || f.folder_count
      ? ` Its ${this.folderMeta(f).replace(/ · in .*/, '')} move to ${where}; no documents are deleted.` : '';
    if (!confirm(`Delete the folder "${f.name}"?${inside}`)) return;
    try {
      await api.deleteFolder(f.id);
      // Its documents now sit in the parent folder
      this.store.documents.update((list) => list.map((d) => (d.folder_id === f.id ? { ...d, folder_id: f.parent_id || null } : d)));
      await this.store.refreshFolders();
    } catch (err: any) {
      alert(err.message);
    }
  }

  // ---- moving: drag a document (or the checked ones) or a folder onto a folder or a path segment ----
  dragDocs(e: DragEvent, id: string) {
    if (!this.browse()) return;
    const ids = this.checked().has(id) ? this.visibleChecked() : [id];
    this.dragging = { docs: ids };
    e.dataTransfer?.setData('text/plain', ids.join(','));
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  dragFolder(e: DragEvent, id: string) {
    this.dragging = { folder: id };
    e.dataTransfer?.setData('text/plain', id);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  dragEnd() {
    this.dragging = null;
    this.dropOn.set(null);
  }

  allowDrop(e: DragEvent, target: string) {
    if (!this.dragging || this.dragging.folder === target) return;
    e.preventDefault();
    this.dropOn.set(target);
  }

  async dropInto(e: DragEvent, folderId: string | null) {
    e.preventDefault();
    const what = this.dragging;
    this.dragEnd();
    if (!what) return;
    try {
      if (what.docs) {
        await this.store.moveDocuments(what.docs, folderId);
        this.checked.set(new Set());
      } else if (what.folder && what.folder !== folderId) {
        await api.moveFolder(what.folder, folderId);
        await this.store.refreshFolders();
      }
    } catch (err: any) {
      alert(err.message);
    }
  }

  async moveChecked(select: HTMLSelectElement) {
    const target = select.value === '__top' ? null : select.value;
    select.value = '';
    const ids = this.visibleChecked();
    if (!ids.length) return;
    try {
      await this.store.moveDocuments(ids, target);
      this.checked.set(new Set());
    } catch (err: any) {
      alert(err.message);
    }
  }

  protected emptySet() {
    return new Set<string>();
  }

  // Deletes after a confirmation naming what will go: the document, its file and its extracted data
  async deleteDocs(ids: string[]) {
    const docsById = Object.fromEntries(this.documents().map((d: Doc) => [d.id, d]));
    const what = ids.length === 1 ? `"${docsById[ids[0]]?.title || ids[0]}"` : `${ids.length} documents`;
    if (!confirm(`Delete ${what}? The uploaded file, extracted fields and history are removed. This cannot be undone.`)) return;
    this.deleting.set(true);
    try {
      const res: any = await api.deleteDocuments(ids);
      this.checked.update((prev) => new Set([...prev].filter((id) => !res.deleted.includes(id))));
      this.store.documentsDeleted(res.deleted);
    } catch (err: any) {
      alert(`Delete error: ${err.message}`);
    } finally {
      this.deleting.set(false);
    }
  }

  toggle(id: string) {
    this.checked.update((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  toggleAll() {
    const all = this.allVisibleChecked();
    this.checked.update((prev) => {
      const next = new Set(prev);
      this.filteredDocs().forEach((d: Doc) => (all ? next.delete(d.id) : next.add(d.id)));
      return next;
    });
  }

  selectDocument(id: string) {
    this.router.navigate(['/review', id]);
  }

  openUploadModal() {
    this.store.uploadOpen.set(true);
  }

  protected exportUrl(id: string, kind: 'json' | 'csv') {
    return apiUrl(`/api/v1/documents/${id}/export/${kind}`);
  }

  protected typeLabel(type: string) {
    switch (type) {
      case 'contracts': return 'Contract / NDA';
      case 'identity': return 'Passport / KYC';
      case 'invoices': return 'Tax Invoice';
      case 'generic': return 'General Document';
      default: return 'Template';
    }
  }

  protected confPercent(doc: Doc) {
    return Math.round(doc.overall_confidence * 100);
  }

  protected confClass(doc: Doc) {
    const p = this.confPercent(doc);
    return p >= 90 ? 'high' : p >= 75 ? 'medium' : 'low';
  }

  protected metaTitle(doc: Doc) {
    return `${doc.file_name} · ${doc.page_count} page${doc.page_count > 1 ? 's' : ''} · ${(doc.file_size_bytes / 1024).toFixed(1)} KB · ${new Date(doc.created_at).toLocaleString()}`;
  }

  protected metaLine(doc: Doc) {
    const when = new Date(doc.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    const line = `${doc.file_name} · ${doc.page_count} pg · ${(doc.file_size_bytes / 1024).toFixed(1)} KB · ${when}`;
    // Outside its folder (dashboard, search results) say where the document is
    const showFolder = doc.folder_id && (!this.browse() || this.searchQuery() || this.typeFilter() === 'custom');
    return showFolder ? `${this.store.folderLabel(doc.folder_id)} · ${line}` : line;
  }
}
