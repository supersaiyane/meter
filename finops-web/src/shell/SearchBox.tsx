import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Collection,
  ComboBox,
  Header,
  Input,
  ListBox,
  ListBoxItem,
  ListBoxSection,
  Popover,
  Text,
  type Key,
} from 'react-aria-components';
import { useNavigate, useSearchParams } from 'react-router';

import { ACCOUNT_KEY, keepAccount, useChosenAccount } from '../api/account';
import { useAccountChoices, useResourceSearch, useServiceChoices } from '../api/queries';
import {
  RESOURCE_MATCHES,
  RESOURCE_SEARCH_FROM,
  accountLabel,
  accountSection,
  optionFor,
  resourceSection,
  sectionsFor,
  serviceSection,
  type SearchAction,
  type SearchOption,
  type SearchSection,
} from './searchModel';

/** How long typing must pause before resources are searched on the server. */
const SEARCH_PAUSE_MS = 250;

/** The value once it has stopped changing for a moment, so typing is not a request per key. */
function useSettled(value: string, pause: number): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSettled(value);
    }, pause);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, pause]);
  return settled;
}

/** What failed to load, in words, or null when nothing did. */
function failureOf(accounts: boolean, services: boolean, resources: boolean): string | null {
  const failed = [
    accounts ? 'the accounts' : null,
    services ? 'the services' : null,
    resources ? 'the resources' : null,
  ].filter((part): part is string => part !== null);
  return failed.length === 0 ? null : `Could not read ${failed.join(' or ')}.`;
}

/**
 * The search box in the top bar of every screen, FEAT-075 and the owner's choices of 2026-10-05
 * and 2026-10-06: one box that finds accounts, services and resources. An account narrows every
 * screen, a service opens Cost Explorer filtered to it and a resource opens its page. When nobody
 * is typing in it, the box shows what every screen is narrowed to.
 *
 * Accounts and services are loaded once and searched here, so typing never waits on the network.
 * Resources are searched on the server after a pause, because no browser holds an estate's worth.
 */
export function SearchBox() {
  const chosen = useChosenAccount();
  const [, setParams] = useSearchParams();
  const navigate = useNavigate();
  const focused = useRef(false);
  const [typing, setTyping] = useState(false);
  const [query, setQuery] = useState('');
  const settled = useSettled(query.trim(), SEARCH_PAUSE_MS);

  const accounts = useAccountChoices();
  const services = useServiceChoices();
  const resources = useResourceSearch(
    settled.length >= RESOURCE_SEARCH_FROM ? settled : null,
    RESOURCE_MATCHES,
  );

  const known = useMemo(() => accounts.data?.data ?? [], [accounts.data]);
  const sections = useMemo(
    () =>
      sectionsFor([
        accountSection(known, query),
        serviceSection(services.data?.data ?? [], query),
        // Only what the server found for the text as it stands, never a previous word's.
        resourceSection(settled === query.trim() ? (resources.data?.data.resources ?? []) : []),
      ]),
    [known, query, services.data, resources.data, settled],
  );
  const failure = failureOf(accounts.isError, services.isError, resources.isError);

  const current = known.find((account) => account.account_id === chosen);
  const showing =
    chosen === null ? 'All accounts' : current === undefined ? chosen : accountLabel(current);

  function act(action: SearchAction): void {
    if (action.kind === 'all' || action.kind === 'account') {
      setParams((params) => {
        const next = new URLSearchParams(params);
        if (action.kind === 'all') {
          next.delete(ACCOUNT_KEY);
        } else {
          next.set(ACCOUNT_KEY, action.accountId);
        }
        return next;
      });
      return;
    }
    const to =
      action.kind === 'service'
        ? `/analyze/explorer?${new URLSearchParams({ service: action.service }).toString()}`
        : `/inventory/resources/${action.nodeId}`;
    void navigate(keepAccount(to, chosen));
  }

  function settle(): void {
    setTyping(false);
    setQuery('');
  }

  return (
    <ComboBox
      data-testid="search"
      aria-label="Search accounts, services and resources"
      items={sections}
      inputValue={typing ? query : showing}
      onInputChange={(value) => {
        // The box resets its own text when it loses focus, which is not somebody typing.
        if (!focused.current) {
          return;
        }
        setTyping(true);
        setQuery(value);
      }}
      value={null}
      onChange={(key: Key | null) => {
        const option = optionFor(sections, key);
        if (option !== undefined) {
          act(option.action);
        }
        settle();
      }}
      menuTrigger="focus"
      allowsEmptyCollection
    >
      <Input
        data-testid="search-input"
        placeholder="Search accounts, services, resources"
        onFocus={(event) => {
          focused.current = true;
          event.currentTarget.select();
        }}
        onBlur={() => {
          focused.current = false;
          settle();
        }}
      />
      <Popover data-testid="search-results" placement="bottom start">
        {failure === null ? null : (
          <p data-testid="search-failure" role="status">
            {failure}
          </p>
        )}
        {resources.isFetching ? (
          <p data-testid="search-searching" role="status">
            Searching resources
          </p>
        ) : null}
        <ListBox<SearchSection> data-testid="search-list">
          {(section) => (
            <ListBoxSection id={section.id} data-testid={`search-${section.id}`}>
              <Header data-testid="search-header">{section.name}</Header>
              <Collection items={section.children}>
                {(option: SearchOption) => (
                  <ListBoxItem
                    id={option.id}
                    textValue={option.label}
                    data-testid="search-option"
                  >
                    <Text slot="label" data-testid="search-option-label">
                      {option.label}
                    </Text>
                    <Text slot="description" data-testid="search-option-detail">
                      {option.detail}
                    </Text>
                  </ListBoxItem>
                )}
              </Collection>
            </ListBoxSection>
          )}
        </ListBox>
      </Popover>
    </ComboBox>
  );
}
