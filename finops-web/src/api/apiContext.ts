import { createContext, useContext } from 'react';

import type { ApiClient } from './client';

export const ApiContext = createContext<ApiClient | undefined>(undefined);

export function useApi(): ApiClient {
  const client = useContext(ApiContext);
  if (client === undefined) {
    throw new Error('A screen must be rendered inside ApiProvider');
  }
  return client;
}
