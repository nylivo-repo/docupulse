import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import {
  CheckSquare, Code2, ExternalLink, FileText, Key, KeyRound, Layers, LayoutDashboard, LogOut, Menu,
  Monitor, Moon, Settings, Sun, UploadCloud, UserCircle2, Webhook, X,
} from 'lucide';
import { apiUrl, auth } from '../core/api';
import { DismissDirective } from '../core/dismiss.directive';
import { BRAND, BrandMark } from '../core/brand';
import { Icon } from '../core/icon';
import { Store } from '../core/store';
import { Mode, THEMES, ThemeService } from '../core/theme';
import { UploadModal } from '../pages/upload-modal';

// Sidebar, header and the page area. Below 900px wide the sidebar becomes a slide-out menu.
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon, DismissDirective, UploadModal, BrandMark],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .user-name { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .menu-head { padding: 6px 8px 8px; font-size: 0.78rem; border-bottom: 1px solid var(--border-color); margin-bottom: 6px; }
    .menu-head div:first-child { font-weight: 600; }
    .menu-head div:last-child { color: var(--text-muted); }
    .docs-tag { margin-left: auto; font-size: 0.68rem; color: var(--accent-cyan); }
    .close-nav { display: none; margin-left: auto; }
    @media (max-width: 900px) { .close-nav { display: inline-flex; } }
    @media (max-width: 640px) { .user-name { display: none; } }
    .popover-menu.user-menu { min-width: 260px; }
    .menu-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); font-weight: 700; padding: 4px 8px; }
    .modes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; padding: 0 4px 8px; }
    .popover-menu .modes .btn { width: auto; justify-content: center; margin-top: 0; padding: 6px 4px; }
    .modes .btn.on { border-color: var(--primary); color: var(--text-primary); background: color-mix(in srgb, var(--primary) 14%, transparent); }
    .swatches { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; padding: 2px 8px 10px; }
    .swatch { width: 30px; height: 30px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; padding: 0;
      box-shadow: inset 0 0 0 2px var(--bg-card-elevated); }
    .swatch.on { border-color: var(--text-primary); }
    .theme-name { font-size: 0.72rem; color: var(--text-secondary); padding: 0 8px 8px; }
    .menu-sep { border-top: 1px solid var(--border-color); margin: 2px 0 6px; }
  `,
  template: `
    <div class="app-container">
      <div class="bg-glow-mesh"></div>
      <div class="sidebar-scrim" [class.open]="navOpen()" (click)="navOpen.set(false)"></div>

      <aside class="sidebar" [class.open]="navOpen()" [appDismiss]="navOpen()" (dismissed)="navOpen.set(false)">
        <div class="sidebar-header">
          <app-brand-mark />
          <div class="logo-text"><h2>{{ brand.name }}</h2><span>{{ brand.tagline }}</span></div>
          <button class="btn btn-secondary btn-sm icon-btn close-nav" (click)="navOpen.set(false)" aria-label="Close menu">
            <app-icon [icon]="X" [size]="16" />
          </button>
        </div>
        <nav class="sidebar-nav" (click)="navOpen.set(false)">
          <div class="nav-section-title">Core Operations</div>
          <a class="nav-item" routerLink="/dashboard" routerLinkActive="active"><app-icon [icon]="LayoutDashboard" /><span>Dashboard</span></a>
          <a class="nav-item" routerLink="/documents" routerLinkActive="active"><app-icon [icon]="FileText" /><span>Document Hub</span></a>
          <a class="nav-item" routerLink="/review" routerLinkActive="active">
            <app-icon [icon]="CheckSquare" /><span>Review Studio</span>
            @if (store.needsReviewCount()) { <span class="nav-badge warning">{{ store.needsReviewCount() }}</span> }
          </a>
          @if (store.isAdmin()) {
            <div class="nav-section-title">Admin Settings</div>
            <a class="nav-item" routerLink="/admin" routerLinkActive="active"><app-icon [icon]="Settings" /><span>Users &amp; Sign-in</span></a>
            <a class="nav-item" routerLink="/templates" routerLinkActive="active"><app-icon [icon]="Layers" /><span>Templates</span></a>
            <a class="nav-item" routerLink="/api-keys" routerLinkActive="active"><app-icon [icon]="Key" /><span>API Keys</span></a>
            <a class="nav-item" routerLink="/webhooks" routerLinkActive="active"><app-icon [icon]="Webhook" /><span>Webhooks</span></a>
            <a class="nav-item" routerLink="/api-console" routerLinkActive="active"><app-icon [icon]="Code2" /><span>API Developer Portal</span></a>
            <a class="nav-item" [href]="docsUrl" target="_blank" rel="noreferrer">
              <app-icon [icon]="ExternalLink" /><span>Documentation</span><span class="docs-tag">/docs</span>
            </a>
          }
        </nav>
      </aside>

      <div class="main-viewport">
        <header class="top-navbar">
          <div class="header-left">
            <button class="btn btn-secondary btn-sm icon-btn menu-toggle" (click)="navOpen.set(true)" aria-label="Open menu">
              <app-icon [icon]="Menu" [size]="18" />
            </button>
            <div class="header-title-wrapper" style="min-width:0">
              <h1>{{ page().title }}</h1>
              <div class="header-subtitle">{{ page().subtitle }}</div>
            </div>
          </div>
          <div class="header-right">
            <button class="btn btn-primary" (click)="store.uploadOpen.set(true)" title="Upload Document">
              <app-icon [icon]="UploadCloud" [size]="16" /><span class="hide-sm">Upload Document</span>
            </button>
            <div style="position:relative" [appDismiss]="menuOpen()" (dismissed)="menuOpen.set(false)">
              <button class="btn btn-secondary btn-sm" (click)="menuOpen.set(!menuOpen())" aria-haspopup="menu"
                [attr.aria-expanded]="menuOpen()" [title]="userName() + ' (' + user().role + ')'">
                <app-icon [icon]="UserCircle2" [size]="16" /><span class="user-name">{{ userName() }}</span>
              </button>
              @if (menuOpen()) {
                <div class="popover-menu user-menu" role="menu">
                  <div class="menu-head">
                    <div>{{ userName() }}</div>
                    <div>{{ user().role === 'admin' ? 'Administrator' : 'User' }} · {{ source() }}</div>
                  </div>
                  <div class="menu-label">Appearance</div>
                  <div class="modes" role="group" aria-label="Light or dark">
                    @for (m of modes; track m.id) {
                      <button class="btn btn-secondary btn-sm" [class.on]="theme.mode() === m.id" (click)="theme.setMode(m.id)"
                        [attr.aria-pressed]="theme.mode() === m.id" [title]="m.title">
                        <app-icon [icon]="m.icon" [size]="14" /><span>{{ m.label }}</span>
                      </button>
                    }
                  </div>
                  <div class="swatches" role="group" aria-label="Theme">
                    @for (t of themes; track t.id) {
                      <button class="swatch" [class.on]="theme.theme() === t.id" (click)="theme.setTheme(t.id)" [title]="t.name"
                        [attr.aria-label]="t.name" [attr.aria-pressed]="theme.theme() === t.id"
                        [style.background]="'linear-gradient(135deg, ' + t.swatch[0] + ' 50%, ' + t.swatch[1] + ' 50%)'"></button>
                    }
                  </div>
                  <div class="theme-name">{{ themeName() }}</div>
                  <div class="menu-sep"></div>
                  @if (user().auth_source === 'local') {
                    <button class="btn btn-secondary btn-sm" (click)="changePassword()"><app-icon [icon]="KeyRound" [size]="14" /><span>Change password</span></button>
                  }
                  <button class="btn btn-secondary btn-sm" (click)="signOut()"><app-icon [icon]="LogOut" [size]="14" /><span>Sign out</span></button>
                </div>
              }
            </div>
          </div>
        </header>

        <main class="page-container"><router-outlet /></main>
      </div>
    </div>

    @if (store.uploadOpen()) { <app-upload-modal /> }
  `,
})
export class Shell {
  protected readonly X = X; protected readonly Menu = Menu;
  protected readonly LayoutDashboard = LayoutDashboard; protected readonly FileText = FileText;
  protected readonly CheckSquare = CheckSquare; protected readonly Settings = Settings; protected readonly Layers = Layers;
  protected readonly Key = Key; protected readonly Webhook = Webhook; protected readonly Code2 = Code2;
  protected readonly ExternalLink = ExternalLink; protected readonly UploadCloud = UploadCloud;
  protected readonly UserCircle2 = UserCircle2; protected readonly KeyRound = KeyRound; protected readonly LogOut = LogOut;

  protected readonly brand = BRAND;
  protected readonly store = inject(Store);
  protected readonly theme = inject(ThemeService);
  protected readonly themes = THEMES;
  protected readonly modes: { id: Mode; label: string; title: string; icon: typeof Sun }[] = [
    { id: 'light', label: 'Light', title: 'Always light', icon: Sun },
    { id: 'dark', label: 'Dark', title: 'Always dark', icon: Moon },
    { id: 'auto', label: 'Auto', title: "Follow this device's setting", icon: Monitor },
  ];
  protected readonly themeName = computed(() => THEMES.find((t) => t.id === this.theme.theme())?.name ?? '');
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  protected readonly docsUrl = apiUrl('/docs');
  protected readonly navOpen = signal(false);
  protected readonly menuOpen = signal(false);
  protected readonly user = computed(() => this.store.user());
  protected readonly userName = computed(() => this.user().display_name || this.user().username);
  protected readonly source = computed(() =>
    ({ okta: 'Okta', ldap: 'Active Directory' } as Record<string, string>)[this.user().auth_source] || 'Local account');

  // Header title and subtitle come from the current route's title and data
  protected readonly page = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => this.current()),
    ),
    { initialValue: this.current() },
  );

  private current() {
    let r = this.route.snapshot;
    while (r.firstChild) r = r.firstChild;
    return { title: (r.title as string) || 'Dashboard', subtitle: (r.data['subtitle'] as string) || '' };
  }

  async signOut() {
    try {
      await auth.logout();
    } finally {
      this.store.signedOut();
    }
  }

  async changePassword() {
    this.menuOpen.set(false);
    const current = prompt('Current password:');
    if (!current) return;
    const next = prompt('New password (at least 10 characters):');
    if (!next) return;
    try {
      await auth.changePassword(current, next);
      alert('Password changed.');
    } catch (err: any) {
      alert(err.message);
    }
  }
}
