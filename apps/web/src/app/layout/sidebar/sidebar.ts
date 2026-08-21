import { Component, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { LucideLayoutGrid, LucideLogOut } from '@lucide/angular';

interface NavItem {
  label: string;
  route: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

@Component({
  imports: [RouterLink, RouterLinkActive, LucideLayoutGrid, LucideLogOut],
  selector: 'app-sidebar',
  templateUrl: './sidebar.html',
})
export class Sidebar {
  readonly collapsed = input(false);

  protected readonly groups: NavGroup[] = [
    { label: 'Tools', items: [{ label: 'Overview', route: '/' }] },
  ];
}
