import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AlertCircle, Check, KeyRound, Plus, PlugZap, Shield, Trash2, Users } from 'lucide';
import { admin, serverOrigin } from '../core/api';
import { Icon } from '../core/icon';
import { Store } from '../core/store';

type Msg = [kind: string, text: string] | undefined;

@Component({
  selector: 'app-notice',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .managed-note { font-size: 0.8rem; color: var(--text-secondary); padding: 10px 12px; margin-bottom: 12px; border-radius: var(--radius-sm);
      border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent); background: color-mix(in srgb, var(--primary) 8%, transparent); }
    .managed-note code { overflow-wrap: anywhere; }
    .notice { display: flex; gap: 8px; align-items: center; padding: 8px 12px; border-radius: var(--radius-sm); font-size: 0.8rem;
      background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger-text); min-width: 0; overflow-wrap: anywhere; }
    .notice.ok { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success-text); }
  `,
  template: `
    @if (text()) {
      <div class="notice" [class.ok]="kind() === 'ok'">
        <app-icon [icon]="kind() === 'ok' ? Check : AlertCircle" [size]="14" />
        <span>{{ text() }}</span>
      </div>
    }
  `,
})
export class Notice {
  protected readonly Check = Check;
  protected readonly AlertCircle = AlertCircle;
  readonly kind = input<string | undefined>();
  readonly text = input<string | undefined>();
}

const MODES = [
  { id: 'local', title: 'Local accounts', text: 'Usernames and passwords managed below.' },
  { id: 'okta', title: 'Okta', text: 'Single sign-on through your Okta tenant. Local admins can still sign in as a backup.' },
  { id: 'ldap', title: 'Active Directory / LDAP', text: 'Company username and password, checked by your domain controllers. Works with no internet.' },
];

const LDAP_FIELDS: [string, string, string][] = [
  ['server_url', 'Server', 'ldaps://dc01.corp.local:636'],
  ['user_base_dn', 'Search base', 'DC=corp,DC=local'],
  ['bind_dn', 'Service account (leave empty for anonymous search)', 'CN=svc-idp,OU=Service Accounts,DC=corp,DC=local'],
  ['bind_password', 'Service account password', 'Paste to set or replace'],
  ['user_filter', 'User search filter ({username} = what people type)', '(&(objectClass=user)(sAMAccountName={username}))'],
  ['group_attribute', 'Group attribute', 'memberOf'],
  ['ca_cert_path', 'CA certificate file on this server (optional)', '/etc/ssl/certs/corp-ca.pem'],
];

@Component({
  selector: 'app-admin-settings',
  imports: [FormsModule, Icon, Notice],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
    .card { padding: 24px; display: flex; flex-direction: column; gap: 14px; min-width: 0; }
    h3 { display: flex; gap: 8px; align-items: center; font-size: 1.05rem; }
    .lbl { font-size: 0.75rem; color: var(--text-muted); display: block; margin-bottom: 4px; }
    .modes { display: flex; gap: 10px; flex-wrap: wrap; }
    .mode { flex: 1 1 260px; cursor: pointer; min-width: 0; }
    .mode.on { border-color: var(--primary); }
    .mode-title { display: flex; gap: 8px; align-items: center; font-weight: 600; }
    .mode-text, .help { font-size: 0.78rem; color: var(--text-secondary); }
    .mode-text { margin-top: 4px; }
    .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr)); gap: 12px; }
    .checks { display: flex; gap: 18px; flex-wrap: wrap; font-size: 0.8rem; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .row.wide { gap: 12px; }
    .w170 { width: 170px; } .w180 { width: 180px; } .w200 { width: 200px; } .w110 { width: 110px; } .w140 { width: 140px; }
    .small { font-size: 0.8rem; }
    .muted { font-size: 0.75rem; color: var(--text-muted); }
    .group-row { display: flex; gap: 8px; align-items: center; }
    .group-row .field-input:first-child { flex: 1; min-width: 0; }
    .data-table { font-size: 0.8rem; }
    .u-name { font-weight: 600; }
    .u-sub { color: var(--text-muted); font-size: 0.72rem; overflow-wrap: anywhere; }
    .u-groups { font-size: 0.72rem; color: var(--text-secondary); }
    .role-select { width: 110px; padding: 4px 6px; }
    .role-src { font-size: 0.68rem; color: var(--text-muted); margin-top: 2px; }
    .right { text-align: right; }
    .add-label { font-size: 0.8rem; font-weight: 600; }
    @media (max-width: 640px) {
      .card { padding: 16px; }
      /* Inputs in wrapping rows take the full width on phones instead of overflowing */
      .row .field-input { width: 100%; flex: 1 1 100%; }
      .group-row { flex-wrap: wrap; }
      .group-row .field-input:first-child { flex: 1 1 100%; }
      .group-row select { flex: 1; width: auto; }
    }
  `,
  template: `
    @if (settings(); as s) {
      <!-- Sign-in method -->
      <div class="glass-card card">
        <h3><app-icon [icon]="KeyRound" [size]="18" /> Sign-in method</h3>
        @if (s.managed?.method) {
          <div class="managed-note">Set on the server in <code>{{ s.managed_file }}</code>, read at every start. To change the
            method or its settings, edit that file (secrets in environment variables) and restart the service. The tests below still work.</div>
        }
        <div class="modes">
          @for (m of modes; track m.id) {
            <label class="field-card mode" [class.on]="s.mode === m.id">
              <div class="mode-title">
                <input type="radio" name="mode" [checked]="s.mode === m.id" (change)="s.mode = m.id" [disabled]="s.managed?.method" />
                {{ m.title }}
              </div>
              <div class="mode-text">{{ m.text }}</div>
            </label>
          }
        </div>

        @if (s.mode === 'ldap') {
          <div class="fields">
            @for (f of ldapFields; track f[0]) {
              <div>
                <span class="lbl">{{ f[1] }}</span>
                <input class="field-input" [type]="f[0] === 'bind_password' ? 'password' : 'text'" [placeholder]="f[2]" autocomplete="off"
                  [ngModel]="s.ldap[f[0]] || ''" (ngModelChange)="s.ldap[f[0]] = $event" [disabled]="s.managed?.method" />
              </div>
            }
          </div>
          <div class="checks">
            <label><input type="checkbox" [checked]="!!s.ldap.use_starttls" (change)="s.ldap.use_starttls = $any($event.target).checked" [disabled]="s.managed?.method" /> Use StartTLS (for ldap://)</label>
            <label><input type="checkbox" [checked]="s.ldap.verify_tls !== false" (change)="s.ldap.verify_tls = $any($event.target).checked" [disabled]="s.managed?.method" /> Verify the server certificate</label>
            <label><input type="checkbox" [checked]="!!s.ldap.nested_groups" (change)="s.ldap.nested_groups = $any($event.target).checked" [disabled]="s.managed?.method" /> Include nested AD groups</label>
          </div>
          <div class="row">
            <input class="field-input w170" placeholder="Test username (optional)" [(ngModel)]="ldapTest.username" autocomplete="off" />
            <input class="field-input w170" type="password" placeholder="Their password" [(ngModel)]="ldapTest.password" autocomplete="new-password" />
            <button class="btn btn-secondary btn-sm" (click)="testLdap()" [disabled]="!s.ldap.server_url">
              <app-icon [icon]="PlugZap" [size]="14" /><span>Test directory</span>
            </button>
            @if (ldapResult()?.testing) { <span class="small">Testing…</span> }
            @if (ldapResult(); as r) {
              @if (!r.testing) { <app-notice [kind]="r.ok ? 'ok' : 'err'" [text]="ldapText(r)" /> }
            }
          </div>
        }

        @if (s.mode === 'okta') {
          <div class="fields">
            @for (f of oktaFields; track f[0]) {
              <div>
                <span class="lbl">{{ f[1] }}</span>
                <input class="field-input" [type]="f[0] === 'client_secret' ? 'password' : 'text'" [placeholder]="f[2]"
                  [ngModel]="s.okta[f[0]] || ''" (ngModelChange)="s.okta[f[0]] = $event" autocomplete="off" [disabled]="s.managed?.method" />
              </div>
            }
          </div>
          <div class="muted">
            Okta is a cloud service: this server must be able to reach your Okta address. In Okta, create an OIDC Web application,
            add the redirect URI above, and add a "groups" claim (your AD groups synced to Okta) to the userinfo response.
          </div>
        }
        <div class="row">
          @if (!s.managed?.method) {
            <button class="btn btn-primary btn-sm" (click)="save('auth')">Save sign-in settings</button>
          }
          @if (s.mode === 'okta') {
            <button class="btn btn-secondary btn-sm" (click)="testOkta()" [disabled]="!s.okta.issuer">
              <app-icon [icon]="PlugZap" [size]="14" /><span>Test Okta connection</span>
            </button>
          }
          @if (okta()?.testing) { <span class="small">Testing…</span> }
          @if (okta(); as o) {
            @if (!o.testing) { <app-notice [kind]="o.ok ? 'ok' : 'err'" [text]="o.ok ? 'This server can reach Okta.' : o.error" /> }
          }
        </div>
        <app-notice [kind]="msg()['auth']?.[0]" [text]="msg()['auth']?.[1]" />
      </div>

      <!-- AD group → role -->
      <div class="glass-card card">
        <h3><app-icon [icon]="Shield" [size]="18" /> Group roles</h3>
        <div class="help">
          Map AD group names (from Active Directory directly, or as Okta sends them) to a role. Someone in several groups gets
          the highest role. Roles are refreshed each time a person signs in, unless you set their role by hand below.
        </div>
        @if (s.managed?.group_roles || s.managed?.default_role) {
          <div class="managed-note">{{ s.managed?.group_roles ? 'Group roles are' : 'The role for people in no mapped group is' }}
            set in <code>{{ s.managed_file }}</code> ([roles]) on the server.</div>
        }
        @for (g of s.group_roles; track $index) {
          <div class="group-row">
            <input class="field-input" placeholder="Group name, e.g. IDP-Admins" [(ngModel)]="g.group" [disabled]="s.managed?.group_roles" />
            <select class="field-input w140" [(ngModel)]="g.role" [disabled]="s.managed?.group_roles">
              <option value="admin">Admin</option>
              <option value="user">User</option>
            </select>
            <button class="btn btn-secondary btn-sm" title="Remove" aria-label="Remove" (click)="removeGroup($index)" [disabled]="s.managed?.group_roles">
              <app-icon [icon]="Trash2" [size]="14" />
            </button>
          </div>
        }
        <div class="row wide">
          <button class="btn btn-secondary btn-sm" (click)="addGroup()" [disabled]="s.managed?.group_roles">
            <app-icon [icon]="Plus" [size]="14" /><span>Add group</span>
          </button>
          <span class="small">People in no mapped group:</span>
          <select class="field-input w200" [(ngModel)]="s.default_role" [disabled]="s.managed?.default_role">
            <option value="user">Get the User role</option>
            <option value="none">Are refused</option>
          </select>
          @if (!(s.managed?.group_roles && s.managed?.default_role)) {
            <button class="btn btn-primary btn-sm" (click)="save('groups')">Save group roles</button>
          }
        </div>
        <app-notice [kind]="msg()['groups']?.[0]" [text]="msg()['groups']?.[1]" />
      </div>

      <!-- Users -->
      <div class="glass-card card">
        <h3><app-icon [icon]="Users" [size]="18" /> Users</h3>
        <!-- Scrolls inside its own box on narrow screens, never the page -->
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr><th>User</th><th>Sign-in</th><th>Groups</th><th>Role</th><th>Active</th><th class="right">Password</th></tr>
            </thead>
            <tbody>
              @for (u of users(); track u) {
                <tr>
                  <td>
                    <div class="u-name">{{ u.display_name || u.username }}{{ u.id === me()?.id ? ' (you)' : '' }}</div>
                    <div class="u-sub">{{ u.username }}{{ u.email ? ' · ' + u.email : '' }}</div>
                  </td>
                  <td>{{ sourceLabel(u.auth_source) }}</td>
                  <td class="u-groups">{{ u.groups.join(', ') || '—' }}</td>
                  <td>
                    <select class="field-input role-select" [ngModel]="u.role" (ngModelChange)="changeUser(u, { role: $event })">
                      <option value="admin">Admin</option>
                      <option value="user">User</option>
                    </select>
                    @if (u.auth_source !== 'local') {
                      <div class="role-src">
                        @if (u.role_locked) {
                          Set by hand · <a href="#" (click)="$event.preventDefault(); changeUser(u, { role_locked: false })">use groups</a>
                        } @else { From groups }
                      </div>
                    }
                  </td>
                  <td>
                    <input type="checkbox" [checked]="u.is_active" [disabled]="u.id === me()?.id"
                      (change)="changeUser(u, { is_active: $any($event.target).checked })" aria-label="Active" />
                  </td>
                  <td class="right">
                    @if (u.auth_source === 'local') {
                      <button class="btn btn-secondary btn-sm" (click)="resetPassword(u)">Reset</button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <form (ngSubmit)="addUser()" class="row">
          <span class="add-label">Add a local user:</span>
          <input class="field-input w180" placeholder="Username" name="username" [(ngModel)]="newUser.username" />
          <input class="field-input w200" type="password" placeholder="Password (10+ characters)" autocomplete="new-password"
            name="password" [(ngModel)]="newUser.password" />
          <select class="field-input w110" name="role" [(ngModel)]="newUser.role">
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
          <button class="btn btn-primary btn-sm" type="submit" [disabled]="!newUser.username || !newUser.password">
            <app-icon [icon]="Plus" [size]="14" /><span>Add user</span>
          </button>
        </form>
        <app-notice [kind]="msg()['users']?.[0]" [text]="msg()['users']?.[1]" />
      </div>
    } @else {
      <div class="glass-card card">Loading settings…</div>
      <app-notice [kind]="msg()['auth']?.[0]" [text]="msg()['auth']?.[1]" />
    }
  `,
})
export class AdminSettings implements OnInit {
  protected readonly KeyRound = KeyRound; protected readonly Shield = Shield; protected readonly Users = Users;
  protected readonly Plus = Plus; protected readonly Trash2 = Trash2; protected readonly PlugZap = PlugZap;

  private readonly store = inject(Store);
  protected readonly me = computed(() => this.store.user());
  protected readonly modes = MODES;
  protected readonly ldapFields = LDAP_FIELDS;
  protected readonly oktaFields: [string, string, string][] = [
    ['issuer', 'Issuer URL', 'https://yourcompany.okta.com/oauth2/default'],
    ['client_id', 'Client ID', '0oa…'],
    ['client_secret', 'Client secret', 'Paste to set or replace'],
    ['redirect_uri', 'Redirect URI (add this in Okta)', `${serverOrigin()}/api/auth/okta/callback`],
    ['scopes', 'Scopes', 'openid profile email groups'],
    ['groups_claim', 'Groups claim name', 'groups'],
  ];

  // The settings object is edited in place by the form; replaced whole when loaded or saved
  protected readonly settings = signal<any | null>(null);
  protected readonly users = signal<any[]>([]);
  protected readonly msg = signal<Record<string, Msg>>({});
  protected readonly okta = signal<any | null>(null);
  protected readonly ldapResult = signal<any | null>(null);
  protected ldapTest = { username: '', password: '' };
  protected newUser = { username: '', password: '', role: 'user' };

  ngOnInit() {
    this.load();
  }

  async load() {
    try {
      this.settings.set(await admin.getAuthSettings());
      this.users.set(await admin.listUsers());
    } catch (err: any) {
      this.msg.set({ auth: ['err', err.message] });
    }
  }

  sourceLabel(src: string) {
    return ({ okta: 'Okta', ldap: 'AD / LDAP' } as Record<string, string>)[src] || 'Local';
  }

  ldapText(r: any) {
    if (!r.ok) return r.error;
    return r.user
      ? `Signed in ${r.user.display_name}: groups ${r.user.groups.join(', ') || 'none'} → role ${r.user.role}.`
      : 'Connected and the service account works.';
  }

  async testLdap() {
    this.ldapResult.set({ testing: true });
    try {
      this.ldapResult.set(await admin.testLdap({ ldap: this.settings().ldap, ...this.ldapTest }));
    } catch (err: any) {
      this.ldapResult.set({ ok: false, error: err.message });
    }
  }

  addGroup() {
    const s = this.settings();
    this.settings.set({ ...s, group_roles: [...s.group_roles, { group: '', role: 'user' }] });
  }

  removeGroup(i: number) {
    const s = this.settings();
    this.settings.set({ ...s, group_roles: s.group_roles.filter((_: any, j: number) => j !== i) });
  }

  async save(section: string) {
    try {
      this.settings.set(await admin.saveAuthSettings(this.settings()));
      this.msg.set({ [section]: ['ok', 'Saved.'] });
    } catch (err: any) {
      this.msg.set({ [section]: ['err', err.message] });
    }
  }

  async testOkta() {
    this.okta.set({ testing: true });
    try {
      this.okta.set(await admin.testOkta(this.settings().okta));
    } catch (err: any) {
      this.okta.set({ ok: false, error: err.message });
    }
  }

  async changeUser(u: any, changes: any) {
    try {
      const updated = await admin.updateUser(u.id, changes);
      this.users.update((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
      this.msg.set({ users: ['ok', `Updated ${u.username}.`] });
    } catch (err: any) {
      this.msg.set({ users: ['err', err.message] });
      // Redraw the row so its controls show the saved values again
      this.users.update((prev) => prev.map((x) => (x.id === u.id ? { ...x } : x)));
    }
  }

  async resetPassword(u: any) {
    const pw = prompt(`New password for ${u.username} (at least 10 characters):`);
    if (pw) await this.changeUser(u, { password: pw });
  }

  async addUser() {
    try {
      const created = await admin.createUser(this.newUser);
      this.users.update((prev) => [...prev, created]);
      this.newUser = { username: '', password: '', role: 'user' };
      this.msg.set({ users: ['ok', `Created ${created.username}.`] });
    } catch (err: any) {
      this.msg.set({ users: ['err', err.message] });
    }
  }
}
