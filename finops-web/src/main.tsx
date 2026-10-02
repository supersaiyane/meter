import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { createApiClient } from './api/client';
import { readStored } from './storage';
// Latin only, self hosted. The file declares every weight but a browser
// fetches only the ones the stylesheet actually uses.
import '@fontsource/ibm-plex-sans/latin.css';
import '@fontsource/ibm-plex-mono/latin.css';
import './tokens.css';
import './layout.css';

const container = document.getElementById('root');
if (!container) {
  // Failing loudly beats rendering nothing into a page that looks merely empty.
  throw new Error('The root element is missing from index.html');
}

// The token comes from wherever the session was established. An absent one is
// not special cased: the API refuses, and the screens say so with a typed
// cause, which is exactly what they would do for an expired one. A browser that
// refuses to answer about stored data is the same case, and read through
// readStored it stays that case rather than stopping the application starting.
const token = readStored('meter.token') ?? '';

createRoot(container).render(
  <StrictMode>
    <App client={createApiClient({ token })} />
  </StrictMode>,
);
