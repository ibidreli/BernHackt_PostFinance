import { Routes } from '@angular/router';

import { DashboardLayout } from './layout/dashboard-layout/dashboard-layout';

export const routes: Routes = [
  {
    path: '',
    component: DashboardLayout,
    children: [
      {
        path: '',
        title: 'Kategorien',
        loadComponent: () => import('./pages/explorer/explorer').then((m) => m.ExplorerPage),
      },
      {
        path: 'forecast',
        title: 'Prognose',
        loadComponent: () => import('./pages/forecast/forecast').then((m) => m.ForecastPage),
      },
      {
        path: 'assistant',
        title: 'Assistenz',
        loadComponent: () => import('./pages/assistant/assistant').then((m) => m.AssistantPage),
      },
    ],
  },
];
