import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { createApiClient } from './api/client';
import './tokens.css';

const container = document.getElementById('root');
if (!container) {
  // Failing loudly beats rendering nothing into a page that looks merely empty.
  throw new Error('The root element is missing from index.html');
}

// The token comes from wherever the session was established. An absent one is
// not special cased: the API refuses, and the screens say so with a typed
// cause, which is exactly what they would do for an expired one.
const token = window.localStorage.getItem('meter.token') ?? '';

createRoot(container).render(
  <StrictMode>
    <App client={createApiClient({ token })} />
  </StrictMode>,
);
