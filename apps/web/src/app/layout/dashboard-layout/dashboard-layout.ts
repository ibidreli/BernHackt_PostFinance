import { NgTemplateOutlet } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { LucideChevronRight, LucideMoon, LucidePanelLeft, LucideSun } from '@lucide/angular';

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
  }

  private routeTitle(): string {
    let route = this.router.routerState.snapshot.root;
    while (route.firstChild) route = route.firstChild;
    return route.title ?? '';
  }

  protected toggleCollapsed(): void {
    this.collapsed.update((collapsed) => !collapsed);
  }
}
