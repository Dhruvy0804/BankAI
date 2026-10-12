import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import App from './App';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('reports backend failure without pretending the database is connected and can retry', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  expect(await screen.findByText(/Start the FastAPI backend/)).toBeInTheDocument();
  fetchMock.mockImplementation((url: string) => Promise.resolve({
    ok: true, json: async () => ({ status: url.endsWith('health') ? 'ok' : 'ready' }),
  }));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh status' }));
  expect(await screen.findAllByText('Connected')).toHaveLength(2);
  expect(screen.queryByText(/Start the FastAPI backend/)).not.toBeInTheDocument();
});

test('distinguishes database outage from process health', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve({
    ok: url.endsWith('health'), json: async () => ({ status: 'ok' }),
  })));
  render(<App />);
  expect(await screen.findByText(/Start the PostgreSQL service/)).toBeInTheDocument();
});
