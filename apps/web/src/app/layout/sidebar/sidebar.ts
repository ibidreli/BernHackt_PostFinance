import { Component, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import {
  LucideChartLine,
  LucideCircleDot,
  LucideLogOut,
  LucideMessageSquare,
} from '@lucide/angular';

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
  imports: [
    RouterLink,
    RouterLinkActive,
    LucideChartLine,
    LucideCircleDot,
    LucideLogOut,
    LucideMessageSquare,
  ],
  selector: 'app-sidebar',
  templateUrl: './sidebar.html',
})
export class Sidebar {
  readonly collapsed = input(false);

  protected readonly groups: NavGroup[] = [
    {
      label: 'Tools',
      items: [
        { label: 'Kategorien', route: '/', icon: 'explorer' },
        { label: 'Prognose', route: '/forecast', icon: 'forecast' },
        { label: 'Assistenz', route: '/assistant', icon: 'assistant' },
      ],
    },
  ];
}
