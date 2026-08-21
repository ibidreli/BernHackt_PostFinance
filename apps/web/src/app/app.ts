import { Component, effect, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

function getInitialDarkMode(): boolean {
  const stored = localStorage.getItem('theme');
  if (stored) return stored === 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  protected readonly isDark = signal(getInitialDarkMode());

  constructor() {
    effect(() => {
      const dark = this.isDark();
      document.documentElement.classList.toggle('dark', dark);
      localStorage.setItem('theme', dark ? 'dark' : 'light');
    });
  }

  protected toggleTheme(): void {
    this.isDark.update((dark) => !dark);
  }
}
