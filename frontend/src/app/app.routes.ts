import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { Store } from './core/store';

// Admin pages are not reachable for other users (their APIs refuse them too)
const adminOnly = async () => {
  const store = inject(Store);
  await store.ready;
  return store.isAdmin();
};

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: 'dashboard', title: 'Dashboard', data: { subtitle: 'Your documents: throughput, accuracy and what needs review' },
    loadComponent: () => import('./pages/dashboard').then((m) => m.Dashboard) },
  { path: 'documents', title: 'Document Hub', data: { subtitle: 'Your documents and folders, their type and extraction status', browse: true },
    loadComponent: () => import('./pages/document-list').then((m) => m.DocumentList) },
  { path: 'review', title: 'Review Studio', data: { subtitle: 'Check extracted values against the page, fix them, and approve' },
    loadComponent: () => import('./pages/review').then((m) => m.Review) },
  { path: 'review/:id', title: 'Review Studio', data: { subtitle: 'Check extracted values against the page, fix them, and approve' },
    loadComponent: () => import('./pages/review').then((m) => m.Review) },
  { path: 'admin', title: 'Users & Sign-in', canMatch: [adminOnly],
    data: { subtitle: 'Sign-in method (local, Okta or Active Directory), group roles and user accounts' },
    loadComponent: () => import('./pages/admin-settings').then((m) => m.AdminSettings) },
  { path: 'templates', title: 'Templates', canMatch: [adminOnly],
    data: { subtitle: 'Document types, the fields to extract and their validation rules' },
    loadComponent: () => import('./pages/schema-builder').then((m) => m.SchemaBuilder) },
  { path: 'api-keys', title: 'API Keys', canMatch: [adminOnly],
    data: { subtitle: 'Keys for programmatic access, their permissions and usage' },
    loadComponent: () => import('./pages/api-keys').then((m) => m.ApiKeys) },
  { path: 'webhooks', title: 'Webhooks', canMatch: [adminOnly],
    data: { subtitle: 'Notify other systems when documents are processed' },
    loadComponent: () => import('./pages/webhooks').then((m) => m.Webhooks) },
  { path: 'api-console', title: 'API Developer Portal', canMatch: [adminOnly],
    data: { subtitle: 'REST API examples and code snippets' },
    loadComponent: () => import('./pages/api-console').then((m) => m.ApiConsole) },
  { path: '**', redirectTo: 'dashboard' },
];
