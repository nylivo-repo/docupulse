import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AlertCircle, KeyRound, LogOut } from 'lucide';
import { auth } from '../core/api';
import { BrandMark } from '../core/brand';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

// Shown instead of the app while the signed-in person has a temporary password (first sign-in on a new
// server, or a password an administrator set): nothing else is usable until they choose their own.
@Component({
  selector: 'app-change-password',
  imports: [FormsModule, Icon, BrandMark],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { position: relative; z-index: 1; min-height: 100vh; min-height: 100dvh; display: flex; align-items: center; justify-content: center; padding: 16px; }
    .card { width: 100%; max-width: 420px; padding: 32px; }
    @media (max-width: 480px) { .card { padding: 24px 20px; } }
    .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
    .brand h2 { font-size: 1.15rem; font-weight: 700; }
    p { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 16px; }
    form { display: flex; flex-direction: column; gap: 10px; }
    .full { width: 100%; justify-content: center; }
    .error { display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; border-radius: var(--radius-sm); font-size: 0.8rem;
      background: color-mix(in srgb, var(--danger) 12%, transparent); border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent); color: var(--danger-text); }
    .hint { font-size: 0.75rem; color: var(--text-muted); }
  `,
  template: `
    <div class="glass-card card">
      <div class="brand">
        <app-brand-mark />
        <h2>Choose your own password</h2>
      </div>
      <p>Hello {{ store.user()?.display_name || store.user()?.username }}. You signed in with a temporary password. Set a new one to continue.</p>
      <form (ngSubmit)="submit()">
        <input class="field-input" name="current" type="password" placeholder="Temporary (current) password" autocomplete="current-password" [(ngModel)]="current" />
        <input class="field-input" name="next" type="password" placeholder="New password" autocomplete="new-password" [(ngModel)]="next" />
        <input class="field-input" name="repeat" type="password" placeholder="Repeat the new password" autocomplete="new-password" [(ngModel)]="repeat" />
        <div class="hint">At least 12 characters, not containing your username.</div>
        @if (error()) { <div class="error" role="alert"><app-icon [icon]="AlertCircle" [size]="15" /><span>{{ error() }}</span></div> }
        <button type="submit" class="btn btn-primary full" [disabled]="busy() || !current || !next || !repeat">
          <app-icon [icon]="KeyRound" [size]="16" /><span>{{ busy() ? 'Saving…' : 'Set password and continue' }}</span>
        </button>
        <button type="button" class="btn btn-secondary btn-sm full" (click)="signOut()"><app-icon [icon]="LogOut" [size]="14" /><span>Sign out</span></button>
      </form>
    </div>
  `,
})
export class ChangePassword {
  protected readonly KeyRound = KeyRound;
  protected readonly AlertCircle = AlertCircle; protected readonly LogOut = LogOut;
  protected readonly store = inject(Store);
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected current = '';
  protected next = '';
  protected repeat = '';

  async submit() {
    if (this.next !== this.repeat) {
      this.error.set('The new passwords do not match.');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      await auth.changePassword(this.current, this.next);
      this.store.signedIn({ ...this.store.user(), must_change_password: false });
    } catch (err: any) {
      this.error.set(err.message);
    } finally {
      this.busy.set(false);
    }
  }

  async signOut() {
    try {
      await auth.logout();
    } finally {
      this.store.signedOut();
    }
  }
}
