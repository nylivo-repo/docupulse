import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Store } from './core/store';
import { ThemeService } from './core/theme';
import { ChangePassword } from './shell/change-password';
import { Login } from './shell/login';
import { Shell } from './shell/shell';

// Shows the login page until someone is signed in; signing out or an expired session returns to it
@Component({
  selector: 'app-root',
  imports: [Login, Shell, ChangePassword],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (store.user() === null) {
      <div class="bg-glow-mesh"></div>
      <app-login />
    } @else if (store.user()?.must_change_password) {
      <div class="bg-glow-mesh"></div>
      <app-change-password />
    } @else if (store.user()) {
      <app-shell />
    }
  `,
})
export class App {
  protected readonly store = inject(Store);

  constructor() {
    inject(ThemeService); // applies the saved theme, also on the sign-in page
    this.store.checkSession();
  }
}
