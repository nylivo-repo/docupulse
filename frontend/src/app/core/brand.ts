import { ChangeDetectionStrategy, Component, Injectable, inject, input, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';
import { ShieldCheck } from 'lucide';
import { Icon } from './icon';

// Branding from config.js (window.IDP_CONFIG.brand) and the files in branding/, so a company logo and
// name can be dropped in on the web server without rebuilding (see public/branding/README.txt).
declare global {
  interface Window { IDP_CONFIG?: { apiBaseUrl?: string; brand?: { name?: string; tagline?: string; logo?: string } } }
}
const cfg = window.IDP_CONFIG?.brand || {};
export const BRAND = {
  name: cfg.name || 'IDP',
  tagline: cfg.tagline ?? 'Intelligent Document Processing',
  logo: cfg.logo ?? 'branding/logo.svg',
};

/** The logo: the image from config.js, or the built-in shield in the theme colours if none (or it fails to load) */
@Component({
  selector: 'app-brand-mark',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: inline-flex; flex-shrink: 0; }
    img { width: 38px; height: 38px; object-fit: contain; border-radius: var(--radius-md); display: block; }
  `,
  template: `
    @if (logo && !failed()) {
      <img [src]="logo" [alt]="name" (error)="failed.set(true)" />
    } @else {
      <div class="logo-badge"><app-icon [icon]="ShieldCheck" [size]="22" /></div>
    }
  `,
})
export class BrandMark {
  protected readonly ShieldCheck = ShieldCheck;
  protected readonly logo = BRAND.logo;
  protected readonly name = BRAND.name;
  protected readonly failed = signal(false);
}

/** Browser tab titles: "<page> · <brand name>" */
@Injectable({ providedIn: 'root' })
export class BrandTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  override updateTitle(snapshot: RouterStateSnapshot) {
    const page = this.buildTitle(snapshot);
    this.title.setTitle(page ? `${page} · ${BRAND.name}` : BRAND.name);
  }
}
