import { Directive, ElementRef, effect, inject, input, output } from '@angular/core';

// Closes a menu, dropdown, popover or modal when the user clicks/taps anywhere outside the element
// or presses Escape. Use it on every popover in the app so they all behave the same way:
//   <div [appDismiss]="menuOpen()" (dismissed)="menuOpen.set(false)">…button + menu…</div>
@Directive({ selector: '[appDismiss]' })
export class DismissDirective {
  readonly open = input(false, { alias: 'appDismiss' });
  readonly dismissed = output<void>();
  private readonly host = inject(ElementRef<HTMLElement>);

  constructor() {
    effect((onCleanup) => {
      if (!this.open()) return;
      const onPointer = (e: Event) => {
        if (!this.host.nativeElement.contains(e.target as Node)) this.dismissed.emit();
      };
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') this.dismissed.emit();
      };
      // pointerdown covers mouse, touch and pen, and still fires when a drawing surface cancels the
      // mouse events; capture phase so a component that stops propagation cannot keep a menu open.
      // Registered after the click that opened it has finished, so that click does not close it again.
      const timer = setTimeout(() => document.addEventListener('pointerdown', onPointer, true));
      document.addEventListener('keydown', onKey);
      onCleanup(() => {
        clearTimeout(timer);
        document.removeEventListener('pointerdown', onPointer, true);
        document.removeEventListener('keydown', onKey);
      });
    });
  }
}
