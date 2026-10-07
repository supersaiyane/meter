import { useEffect, useRef, useState } from 'react';

import { useApi } from '../api/apiContext';
import { withFormat, type ExportFormat, type ExportView } from '../api/exportViews';
import { saveFile } from './saveFile';

/**
 * Export, beside the title of every screen that reads a view the API exports. FEAT-067.
 *
 * Each view the screen is showing, as a workbook or as a CSV. The workbook carries an About sheet
 * saying what it is, scope, filters, period and failures among it, and stops at a row limit; the
 * CSV holds every row. Both are written by the server from the screen's own query, behind the
 * same guard as the screen, so the file is the screen's rows and the browser assembles nothing.
 *
 * A disclosure rather than a custom menu, because `summary` carries its own expanded state and
 * keyboard handling, for the reason the navigation gives.
 */

const FORMATS: readonly { readonly format: ExportFormat; readonly label: string }[] = [
  { format: 'xlsx', label: 'Excel workbook' },
  { format: 'csv', label: 'CSV, every row' },
];

export interface ExportMenuProps {
  readonly views: readonly ExportView[];
  /**
   * Open as the screen arrives, because the reader came from the report library's Export,
   * FEAT-068, and the file they asked for should be one choice of format away.
   */
  readonly openOnArrival?: boolean;
}

export function ExportMenu({ views, openOnArrival = false }: ExportMenuProps) {
  // Nothing on this screen is a table the API exports, a map or one resource's page, and a
  // control that can only fail is worse than none. Decided before anything reaches for the
  // client, so a shell with nothing to export needs none.
  return views.length === 0 ? null : <Offered views={views} openOnArrival={openOnArrival} />;
}

function Offered({ views, openOnArrival = false }: ExportMenuProps) {
  const client = useApi();
  const menu = useRef<HTMLDetailsElement>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  // Once, when the menu first has something to offer, and never again on its own: a reader who
  // closes it has answered, and a menu that reopened itself would be arguing with them.
  useEffect(() => {
    if (openOnArrival && menu.current !== null) {
      menu.current.open = true;
    }
  }, [openOnArrival]);

  async function download(view: ExportView, format: ExportFormat): Promise<void> {
    setWorking(`${view.path} ${format}`);
    setFailure(null);
    try {
      const file = await client.getFile(withFormat(view.path, format));
      if (!saveFile(file.name, file.body)) {
        setFailure('This browser cannot save a file a page made. Ask the API for it directly.');
      } else if (menu.current !== null) {
        menu.current.open = false;
      }
    } catch (error) {
      // Said, not swallowed. A button that silently does nothing is one a reader presses four
      // times and then distrusts the whole screen.
      setFailure(error instanceof Error ? error.message : 'The export could not be made.');
    } finally {
      setWorking(null);
    }
  }

  return (
    <details ref={menu} data-testid="export-menu">
      <summary>Export</summary>
      <div data-testid="export-views">
        {views.map((view) => (
          <div key={view.path} role="group" aria-label={view.title} data-testid="export-view">
            <p>{view.title}</p>
            <div>
              {FORMATS.map(({ format, label }) => (
                <button
                  key={format}
                  type="button"
                  data-testid={`export-${format}`}
                  disabled={working !== null}
                  onClick={() => {
                    void download(view, format);
                  }}
                >
                  {working === `${view.path} ${format}` ? 'Preparing' : label}
                </button>
              ))}
            </div>
          </div>
        ))}
        <p data-testid="export-note">
          A workbook says what it is on its About sheet and stops at the row limit. A CSV holds
          every row.
        </p>
        {failure === null ? null : (
          <p role="alert" data-testid="export-failure" className="meter-failure">
            {failure}
          </p>
        )}
      </div>
    </details>
  );
}
