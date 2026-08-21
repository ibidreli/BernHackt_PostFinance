import { Component } from '@angular/core';

interface Category {
  label: string;
  value: string;
  change: string;
}

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.html',
})
export class Dashboard {
  protected readonly categories: Category[] = [
    { label: 'Transport', value: 'CHF 480.50', change: '+2.4% this month' },
    { label: 'Food', value: 'CHF 731.90', change: '+12 this week' },
    { label: 'Entertainment', value: 'CHF 52.70', change: '2 due soon' },
  ];
}
