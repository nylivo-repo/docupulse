import { AfterViewInit, Directive, ElementRef, inject, input } from '@angular/core';

// Focuses an input as soon as it appears (React's autoFocus); with appAutoFocus="select" it also selects its text.
@Directive({ selector: '[appAutoFocus]' })
export class AutoFocusDirective implements AfterViewInit {
  readonly mode = input<'' | 'select'>('', { alias: 'appAutoFocus' });
  private readonly host = inject(ElementRef<HTMLInputElement>);

  ngAfterViewInit() {
    const el = this.host.nativeElement;
    el.focus();
    if (this.mode() === 'select') el.select?.();
  }
}
