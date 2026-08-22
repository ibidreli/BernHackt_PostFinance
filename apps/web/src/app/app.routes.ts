import { Routes } from '@angular/router';

import { DashboardLayout } from './layout/dashboard-layout/dashboard-layout';

export const routes: Routes = [
  {
    path: '',
    component: DashboardLayout,
    children: [
      {
        path: '',
        title: 'Prognose',
        loadComponent: () => import('./pages/forecast/forecast').then((m) => m.ForecastPage),
      },
      {
        path: 'kategorien',
        title: 'Kategorien',
        loadComponent: () => import('./pages/explorer/explorer').then((m) => m.ExplorerPage),
      },
      {
        path: 'future-me',
        title: 'Future Me',
        loadComponent: () => import('./pages/assistant/assistant').then((m) => m.AssistantPage),
      },
      // Old paths stay reachable - slides and chat history link to them.
      { path: 'forecast', redirectTo: '', pathMatch: 'full' },
      { path: 'assistant', redirectTo: 'future-me' },
      { path: '**', redirectTo: '' },
    ],
  },
];
