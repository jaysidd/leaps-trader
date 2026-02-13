/**
 * Smoke test: App renders without crashing.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from '../App';

// Mock components that rely on external APIs or complex rendering
vi.mock('../components/command-center', () => ({
  NewsTicker: () => <div data-testid="news-ticker">NewsTicker</div>,
}));

vi.mock('../pages/CommandCenter', () => ({
  default: () => <div data-testid="page-command-center">CommandCenter</div>,
}));

vi.mock('../pages/Screener', () => ({
  default: () => <div>Screener</div>,
}));

vi.mock('../pages/Settings', () => ({
  default: () => <div>Settings</div>,
}));

vi.mock('../pages/SignalQueue', () => ({
  default: () => <div>SignalQueue</div>,
}));

vi.mock('../pages/HeatMap', () => ({
  default: () => <div>HeatMap</div>,
}));

vi.mock('../pages/SavedScans', () => ({
  default: () => <div>SavedScans</div>,
}));

vi.mock('../pages/Portfolio', () => ({
  default: () => <div>Portfolio</div>,
}));

vi.mock('../pages/MacroIntelligence', () => ({
  default: () => <div>MacroIntelligence</div>,
}));

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />);
    expect(document.body).toBeTruthy();
  });

  it('renders the navigation bar with app title', () => {
    render(<App />);
    expect(screen.getByText('LEAPS Trader')).toBeInTheDocument();
  });

  it('renders all navigation links', () => {
    render(<App />);
    expect(screen.getByText('Command Center')).toBeInTheDocument();
    expect(screen.getByText('Screener')).toBeInTheDocument();
    expect(screen.getByText('Saved Scans')).toBeInTheDocument();
    expect(screen.getByText('Signals')).toBeInTheDocument();
    expect(screen.getByText('Portfolio')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('does NOT render the removed test route', () => {
    render(<App />);
    // MacroOverlayTest page was removed - verify it's gone
    expect(screen.queryByText('MacroOverlayTest')).not.toBeInTheDocument();
  });
});
