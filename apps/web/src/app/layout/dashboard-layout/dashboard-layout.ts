import { NgTemplateOutlet } from '@angular/common';
import {
  Component,
  ElementRef,
  afterRenderEffect,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import {
  LucideChevronRight,
  LucideMoon,
  LucidePanelLeft,
  LucideSettings2,
  LucideSun,
} from '@lucide/angular';

import { Rail } from '../../core/rail';
import { Theme } from '../../core/theme';
import { Sidebar } from '../sidebar/sidebar';

@Component({
  imports: [
    NgTemplateOutlet,
    RouterOutlet,
    Sidebar,
    LucidePanelLeft,
    LucideChevronRight,
    LucideSettings2,
    LucideSun,
    LucideMoon,
  ],
  selector: 'app-dashboard-layout',
  templateUrl: './dashboard-layout.html',
})
export class DashboardLayout {
  protected readonly theme = inject(Theme);
  protected readonly rail = inject(Rail);
  protected readonly collapsed = signal(false);
  /** Below `lg` the rail renders as a bottom sheet behind this flag. */
  protected readonly railOpen = signal(false);

  private readonly router = inject(Router);

  /** The active route's own `title`. Read off the router snapshot rather
      than the document title: this component is created *during* the
      first navigation, so it would miss that NavigationEnd. */
  protected readonly pageTitle = signal(this.routeTitle());

  constructor() {
    this.router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.pageTitle.set(this.routeTitle()));

    // Navigation swaps (or removes) the rail template - a sheet left
    // open would show the previous page's controls for a beat.
    effect(() => {
      this.rail.template();
      this.railOpen.set(false);
    });

    // Dialog semantics: focus starts on the sheet's close button.
    afterRenderEffect({
      write: () => {
        if (this.railOpen()) this.sheetClose()?.nativeElement.focus();
      },
    });
  }

  private readonly sheetClose = viewChild<ElementRef<HTMLButtonElement>>('sheetClose');

  private routeTitle(): string {
    let route = this.router.routerState.snapshot.root;
    while (route.firstChild) route = route.firstChild;
    return route.title ?? '';
  }

  protected toggleCollapsed(): void {
    this.collapsed.update((collapsed) => !collapsed);
  }
}
