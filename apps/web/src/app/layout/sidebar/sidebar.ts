import { Component, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import {
  LucideChartLine,
  LucideLayoutGrid,
  LucideLogOut,
  LucideMessageSquare,
} from '@lucide/angular';

interface NavItem {
  label: string;
  route: string;
  icon: 'overview' | 'forecast' | 'assistant';
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
    LucideLayoutGrid,
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
        { label: 'Overview', route: '/', icon: 'overview' },
        { label: 'Prognose', route: '/forecast', icon: 'forecast' },
        { label: 'Assistenz', route: '/assistant', icon: 'assistant' },
      ],
    },
  ];
}
