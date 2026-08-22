import { DestroyRef, Directive, Service, TemplateRef, inject, signal } from '@angular/core';

/**
 * Lets a routed page contribute a right-hand rail to the shell layout.
 *
 * The rail has to live *outside* the centre card to match the left
 * sidebar's inset look, but the page that fills it lives inside the
 * router outlet. Rather than thread inputs through the layout, the page
 * declares an `<ng-template appRail>` and the layout renders it.
 */
@Service()
export class Rail {
  readonly template = signal<TemplateRef<unknown> | null>(null);
}

@Directive({ selector: '[appRail]' })
export class RailOutlet {
  constructor() {
    const rail = inject(Rail);
    const template = inject(TemplateRef);
    rail.template.set(template);
    inject(DestroyRef).onDestroy(() => rail.template.set(null));
  }
}
