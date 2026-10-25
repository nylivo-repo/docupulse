import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AlertCircle, KeyRound, LogIn } from 'lucide';
import { apiUrl, auth } from '../core/api';
import { BRAND, BrandMark } from '../core/brand';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

const LOGIN_ERRORS: Record<string, string> = {
  okta_failed: 'Okta sign-in did not complete. Please try again.',
  okta_token: 'Okta sign-in failed while confirming your identity. Ask an admin to check the Okta settings.',
  no_role: 'Your account is not in any group allowed to use this app. Ask an admin for access.',
  disabled: 'Your account has been disabled. Ask an admin for access.',
};

@Component({
  selector: 'app-login',
  imports: [FormsModule, Icon, BrandMark],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { position: relative; z-index: 1; min-height: 100vh; min-height: 100dvh; display: flex; align-items: center; justify-content: center; padding: 16px; }
    .card { width: 100%; max-width: 380px; padding: 32px; }
    @media (max-width: 480px) { .card { padding: 24px 20px; } }
    .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }
    .brand h2 { font-size: 1.2rem; font-weight: 700; }
    .brand span, .hint { font-size: 0.75rem; color: var(--text-muted); }
    .error { display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; border-radius: var(--radius-sm);
      background: color-mix(in srgb, var(--danger) 12%, transparent); border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent); color: var(--danger-text); font-size: 0.8rem; }
    form { display: flex; flex-direction: column; gap: 10px; }
    .full { width: 100%; justify-content: center; }
    .okta { margin-bottom: 14px; }
    .note { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 14px; }
  `,
  template: `
    <div class="glass-card card">
      <div class="brand">
        <app-brand-mark />
        <div><h2>{{ brand.name }}</h2><span>Sign in to continue</span></div>
      </div>

      @if (error()) {
        <div class="error" role="alert"><app-icon [icon]="AlertCircle" [size]="15" /><span>{{ error() }}</span></div>
      }

      @if (oktaMode()) {
        @if (config()?.okta_available) {
          <a [href]="oktaUrl" class="btn btn-primary full okta"><app-icon [icon]="LogIn" [size]="16" /><span>Sign in with Okta</span></a>
        } @else {
          <div class="note">Okta sign-in is selected but not fully configured. An administrator can sign in locally below to fix it.</div>
        }
      }

      @if (!oktaMode() || showLocal()) {
        <form (ngSubmit)="submit()">
          @if (oktaMode()) { <div class="hint">Local administrator sign-in</div> }
          @if (config()?.mode === 'ldap') { <div class="hint">Use your company (Windows) username and password</div> }
          <input class="field-input" name="username" placeholder="Username" autocomplete="username" [(ngModel)]="username" autofocus />
          <input class="field-input" name="password" placeholder="Password" type="password" autocomplete="current-password" [(ngModel)]="password" />
          <button type="submit" class="btn btn-primary full" [disabled]="busy() || !username || !password">
            <app-icon [icon]="KeyRound" [size]="16" /><span>{{ busy() ? 'Signing in…' : 'Sign in' }}</span>
          </button>
        </form>
      } @else {
        <button type="button" class="btn btn-secondary btn-sm full" (click)="showLocal.set(true)">Administrator? Sign in with a local account</button>
      }
    </div>
  `,
})
export class Login {
  protected readonly AlertCircle = AlertCircle;
  protected readonly LogIn = LogIn;
  protected readonly KeyRound = KeyRound;
  protected readonly oktaUrl = apiUrl('/api/auth/okta/login');
  protected readonly brand = BRAND;
  private readonly store = inject(Store);

  protected readonly config = signal<any>(null);
  protected readonly showLocal = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected username = '';
  protected password = '';
  protected readonly oktaMode = () => this.config()?.mode === 'okta';

  constructor() {
    auth.config().then((c) => this.config.set(c)).catch(() => this.config.set({ mode: 'local', okta_available: false }));
    const code = new URLSearchParams(window.location.search).get('login_error');
    if (code) {
      this.error.set(LOGIN_ERRORS[code] || `Okta sign-in failed (${code}).`);
      window.history.replaceState(null, '', window.location.pathname);
    }
  }

  async submit() {
    if (!this.username || !this.password) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      this.store.signedIn(await auth.login(this.username.trim(), this.password));
    } catch (err: any) {
      this.error.set(err.message);
    } finally {
      this.busy.set(false);
    }
  }
}
