import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, input } from '@angular/core';
import { createElement, type IconNode } from 'lucide';

// A Lucide icon, bundled with the app (no internet needed). Each page imports only the icons it uses:
//   import { Upload } from 'lucide';  …  <app-icon [icon]="Upload" [size]="16" />
@Component({
  selector: 'app-icon',
  template: '',
  host: { style: 'display:inline-flex;flex-shrink:0;line-height:0', 'aria-hidden': 'true' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Icon {
  readonly icon = input.required<IconNode>();
  readonly size = input(18);
  readonly strokeWidth = input(2);
  private readonly host = inject(ElementRef<HTMLElement>);

  constructor() {
    effect(() => {
      const svg = createElement(this.icon(), {
        width: this.size(),
        height: this.size(),
        'stroke-width': this.strokeWidth(),
      });
      this.host.nativeElement.replaceChildren(svg);
    });
  }
}
