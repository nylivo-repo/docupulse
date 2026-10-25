import { Injectable, computed, signal } from '@angular/core';
import { api, auth } from './api';

export type Doc = any;

// App-wide state for the signed-in person: their documents, templates, keys, webhooks and figures.
// Cleared on sign-out so nothing from one person's session carries over to the next.
@Injectable({ providedIn: 'root' })
export class Store {
  /** undefined: still checking, null: signed out */
  readonly user = signal<any | null | undefined>(undefined);
  readonly isAdmin = computed(() => this.user()?.role === 'admin');

  readonly documents = signal<Doc[]>([]);
  readonly schemas = signal<any[]>([]);
  /** The person's folders (whole tree, linked by parent_id) */
  readonly folders = signal<any[]>([]);
  /** Folder open in the Document Hub (null = top level); new uploads go there */
  readonly currentFolder = signal<string | null>(null);
  readonly apiKeys = signal<any[]>([]);
  readonly webhooks = signal<any[]>([]);
  readonly analytics = signal<any | null>(null);
  readonly selectedDoc = signal<Doc | null>(null);
  readonly uploadOpen = signal(false);
  /** Server feature flags ([features] in server.ini) */
  readonly features = signal<{ demo_presets: boolean }>({ demo_presets: false });
  readonly needsReviewCount = computed(() => this.documents().filter((d) => d.status === 'needs_review').length);

  // Settles once the first session check is done, so route guards can wait for it on a page reload
  private resolveReady!: () => void;
  readonly ready = new Promise<void>((r) => (this.resolveReady = r));

  constructor() {
    window.addEventListener('idp:unauthorized', () => this.signedOut());
  }

  async checkSession() {
    auth.config().then((c) => c?.features && this.features.set(c.features)).catch(() => {});
    try {
      this.signedIn(await auth.me());
    } catch {
      this.user.set(null);
    }
    this.resolveReady();
  }

  signedIn(user: any) {
    this.user.set(user);
    // Nothing loads until a temporary password has been replaced (the API refuses it until then)
    if (user && !user.must_change_password) this.loadAll();
  }

  signedOut() {
    this.user.set(null);
    this.documents.set([]);
    this.schemas.set([]);
    this.folders.set([]);
    this.currentFolder.set(null);
    this.apiKeys.set([]);
    this.webhooks.set([]);
    this.analytics.set(null);
    this.selectedDoc.set(null);
    this.uploadOpen.set(false);
  }

  async loadAll() {
    const admin = this.isAdmin();
    try {
      const [docs, schemas, keys, hooks, analytics, folders] = await Promise.all([
        api.getDocuments(),
        api.getSchemas(),
        admin ? api.getApiKeys() : Promise.resolve([]),
        admin ? api.getWebhooks() : Promise.resolve([]),
        api.getAnalytics(),
        api.getFolders(),
      ]);
      this.folders.set(folders);
      this.documents.set(docs);
      this.schemas.set(schemas);
      this.apiKeys.set(keys);
      this.webhooks.set(hooks);
      this.analytics.set(analytics);
      // Review opens on the first document needing review, else the newest
      if (docs.length && !this.selectedDoc()) {
        const first = docs.find((d: Doc) => d.status === 'needs_review') || docs[0];
        this.selectedDoc.set(first);
        // Only if nothing else (e.g. a /review/<id> link) has been opened in the meantime
        api.getDocument(first.id)
          .then((d) => { if (this.selectedDoc()?.id === first.id) this.selectedDoc.set(d); })
          .catch(console.error);
      }
    } catch (err) {
      console.error('Data loading error:', err);
    }
  }

  refreshAnalytics() {
    api.getAnalytics().then((a) => this.analytics.set(a)).catch(console.error);
  }

  async openDocument(id: string) {
    const doc = await api.getDocument(id);
    this.selectedDoc.set(doc);
    return doc;
  }

  documentUpdated(doc: Doc) {
    this.selectedDoc.set(doc);
    this.documents.update((list) => list.map((d) => (d.id === doc.id ? doc : d)));
    this.refreshAnalytics();
  }

  documentAdded(doc: Doc) {
    this.documents.update((list) => [doc, ...list.filter((d) => d.id !== doc.id)]);
    this.selectedDoc.set(doc);
    this.refreshAnalytics();
    if (doc.folder_id) this.refreshFolders();
  }

  documentsDeleted(ids: string[]) {
    this.documents.update((list) => list.filter((d) => !ids.includes(d.id)));
    if (ids.includes(this.selectedDoc()?.id)) this.selectedDoc.set(null);
    this.refreshAnalytics();
    this.refreshFolders();
  }

  refreshFolders() {
    return api.getFolders().then((f) => this.folders.set(f)).catch(console.error);
  }

  /** The folders from the top level down to this one */
  folderPath(id: string | null): any[] {
    const byId = new Map(this.folders().map((f) => [f.id, f]));
    const path: any[] = [];
    let f = id ? byId.get(id) : null;
    while (f && path.length < 50) {
      path.unshift(f);
      f = f.parent_id ? byId.get(f.parent_id) : null;
    }
    return path;
  }

  folderLabel(id: string | null): string {
    return id ? this.folderPath(id).map((f) => f.name).join(' / ') : '';
  }

  async moveDocuments(ids: string[], folderId: string | null) {
    const res: any = await api.moveDocuments(ids, folderId);
    const moved = new Set<string>(res.moved);
    this.documents.update((list) => list.map((d) => (moved.has(d.id) ? { ...d, folder_id: folderId } : d)));
    const sel = this.selectedDoc();
    if (sel && moved.has(sel.id)) this.selectedDoc.set({ ...sel, folder_id: folderId });
    this.refreshFolders();
    return res.moved as string[];
  }

  schemaCreated(s: any) {
    this.schemas.update((list) => [s, ...list]);
  }
}
