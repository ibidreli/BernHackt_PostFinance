import { Component, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { LucideChartLine, LucideCircleDot, LucideMessageSquare } from '@lucide/angular';

interface NavItem {
  label: string;
  route: string;
  icon: 'explorer' | 'forecast' | 'assistant';
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

@Component({
  imports: [RouterLink, RouterLinkActive, LucideChartLine, LucideCircleDot, LucideMessageSquare],
  selector: 'app-sidebar',
  templateUrl: './sidebar.html',
})
export class Sidebar {
  readonly collapsed = input(false);

  protected readonly groups: NavGroup[] = [
    {
      label: 'Tools',
      items: [
        { label: 'Prognose', route: '/', icon: 'forecast' },
        { label: 'Kategorien', route: '/kategorien', icon: 'explorer' },
        { label: 'Future Me', route: '/future-me', icon: 'assistant' },
      ],
    },
  ];
}
