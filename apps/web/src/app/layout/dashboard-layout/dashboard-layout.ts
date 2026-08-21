import { Component, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { LucideChevronRight, LucideMoon, LucidePanelLeft, LucideSun } from '@lucide/angular';

import { Theme } from '../../core/theme';
import { Sidebar } from '../sidebar/sidebar';

@Component({
  imports: [RouterOutlet, Sidebar, LucidePanelLeft, LucideChevronRight, LucideSun, LucideMoon],
  selector: 'app-dashboard-layout',
  templateUrl: './dashboard-layout.html',
})
export class DashboardLayout {
  protected readonly theme = inject(Theme);
  protected readonly collapsed = signal(false);

  protected toggleCollapsed(): void {
    this.collapsed.update((collapsed) => !collapsed);
  }
}
