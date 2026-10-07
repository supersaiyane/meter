import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fileNameOf, type ApiClient, type DownloadedFile } from '../../api/client';
import { OPEN_EXPORT, asksForExport, type ExportView } from '../../api/exportViews';
import { violationsIn } from '../../components/__tests__/axe';
import { Harness } from '../../screens/__tests__/Harness';
import { clientReturning } from '../../screens/__tests__/fixtures';
import { ExportMenu } from '../ExportMenu';

/** The Export menu, FEAT-067 and TASK-P8-009: the server's file, under the screen's query. */

const VIEWS: readonly ExportView[] = [
  { title: 'Cost by account', path: '/api/v1/cost/by-account' },
  { title: 'Cost Explorer', path: '/api/v1/cost/explore?group_by=account' },
];

function clientAsking(answer: (path: string) => Promise<DownloadedFile>): {
  readonly client: ApiClient;
  readonly asked: string[];
} {
  const asked: string[] = [];
  const client: ApiClient = {
    ...clientReturning({}),
    getFile: (path: string) => {
      asked.push(path);
      return answer(path);
    },
  };
  return { client, asked };
}

function saved(path: string): Promise<DownloadedFile> {
  return Promise.resolve({ name: fileNameOf(null, path), body: new Blob(['cells']) });
}

/** Object URLs stubbed, and the names of the files the browser was handed. */
function savingBrowser(): string[] {
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:meter'),
    revokeObjectURL: vi.fn(),
  });
  const clicked: string[] = [];
  // Spied rather than stashed and restored by hand. Holding a reference to a prototype method
  // loses its `this`, and vitest puts the real one back.
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function recorded(
    this: HTMLAnchorElement,
  ) {
    clicked.push(this.download);
  });
  return clicked;
}

function renderMenu(client: ApiClient, views: readonly ExportView[] = VIEWS) {
  return render(
    <Harness client={client}>
      <ExportMenu views={views} />
    </Harness>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ExportMenu', () => {
  it('is absent on a screen that reads nothing the API exports', () => {
    renderMenu(clientAsking(saved).client, []);
    expect(screen.queryByTestId('export-menu')).not.toBeInTheDocument();
  });

  it('offers every view on the screen as a workbook and as a CSV', () => {
    renderMenu(clientAsking(saved).client);
    const views = screen.getAllByTestId('export-view');
    expect(views).toHaveLength(2);
    expect(within(views[0] as HTMLElement).getByTestId('export-xlsx')).toHaveTextContent(
      'Excel workbook',
    );
    expect(within(views[0] as HTMLElement).getByTestId('export-csv')).toHaveTextContent(
      'CSV, every row',
    );
  });

  it('asks for the view with its own query and saves the file under the server name', async () => {
    const clicked = savingBrowser();
    const { client, asked } = clientAsking(saved);
    renderMenu(client);
    await userEvent.click(screen.getByText('Export'));
    const explorer = screen.getByRole('group', { name: 'Cost Explorer' });
    await userEvent.click(within(explorer).getByTestId('export-xlsx'));
    await waitFor(() => {
      expect(clicked).toEqual(['meter-export.xlsx']);
    });
    expect(asked).toEqual(['/api/v1/cost/explore?group_by=account&format=xlsx']);
    expect(screen.getByTestId('export-menu')).not.toHaveAttribute('open');
  });

  it('says what failed rather than doing nothing', async () => {
    // A button that silently does nothing is one a reader presses four times and then
    // distrusts the whole screen.
    const { client } = clientAsking(() => Promise.reject(new Error('Not in your scope')));
    renderMenu(client);
    await userEvent.click(screen.getByText('Export'));
    await userEvent.click(screen.getAllByTestId('export-csv')[0] as HTMLElement);
    const failure = await screen.findByTestId('export-failure');
    expect(failure).toHaveAttribute('role', 'alert');
    expect(failure).toHaveTextContent('Not in your scope');
  });

  it('says so when the browser cannot save a file a page made', async () => {
    vi.stubGlobal('URL', { ...URL, createObjectURL: undefined });
    renderMenu(clientAsking(saved).client);
    await userEvent.click(screen.getByText('Export'));
    await userEvent.click(screen.getAllByTestId('export-csv')[0] as HTMLElement);
    expect(await screen.findByTestId('export-failure')).toHaveTextContent(/cannot save/);
  });

  it('holds every button while one file is being made', async () => {
    renderMenu(clientAsking(() => new Promise<never>(() => undefined)).client);
    await userEvent.click(screen.getByText('Export'));
    await userEvent.click(screen.getAllByTestId('export-xlsx')[0] as HTMLElement);
    expect(screen.getAllByTestId('export-xlsx')[0]).toHaveTextContent('Preparing');
    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled();
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = renderMenu(clientAsking(saved).client);
    await userEvent.click(screen.getByText('Export'));
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('the Export menu, opened from the report library, FEAT-068', () => {
  it('opens itself when the reader came from the library to export', async () => {
    const { client } = clientAsking(saved);
    render(
      <Harness client={client}>
        <ExportMenu views={VIEWS} openOnArrival />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('export-menu')).toHaveAttribute('open');
    });
  });

  it('stays closed when the reader arrived any other way', () => {
    const { client } = clientAsking(saved);
    render(
      <Harness client={client}>
        <ExportMenu views={VIEWS} />
      </Harness>,
    );
    expect(screen.getByTestId('export-menu')).not.toHaveAttribute('open');
  });

  it("knows the library's state and nothing else", () => {
    expect(asksForExport(OPEN_EXPORT)).toBe(true);
    for (const state of [null, undefined, 'openExport', {}, { openExport: 'yes' }]) {
      expect(asksForExport(state)).toBe(false);
    }
  });
});
