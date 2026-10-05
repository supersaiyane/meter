import type { ApiExplore } from '../api/types';
import {
  COLUMNS,
  COLUMN_NAMES,
  METRIC_NAMES,
  PRESETS,
  chipsOf,
  groupingChange,
  groupingValue,
  type ExploreChange,
  type ExploreValues,
} from './exploreModel';

/**
 * Cost Explorer's controls, FEAT-065. Every control writes the address rather than local
 * state, so the view a reader builds is the view a link to it opens, and the back button walks
 * back through the views they chose.
 */
interface ExploreControlsProps {
  readonly values: ExploreValues;
  /** The last answer, for the tag keys and the measures this period offers. */
  readonly explore: ApiExplore | undefined;
  readonly update: (changes: ExploreChange) => void;
}

interface Option {
  readonly value: string;
  readonly label: string;
  readonly title?: string;
}

const TAG_PREFIX = 'tag:';

function tagOption(value: string): Option {
  return { value, label: `Tag: ${value.slice(TAG_PREFIX.length)}` };
}

function optionsFor(tagKeys: readonly string[], chosen: readonly string[]): readonly Option[] {
  const columns = COLUMNS.map((column) => ({
    value: column,
    label: COLUMN_NAMES[column].name,
    title: `FOCUS ${COLUMN_NAMES[column].focus}`,
  }));
  const tags = tagKeys.map((key) => tagOption(`${TAG_PREFIX}${key}`));
  const known = new Set([...columns, ...tags].map((option) => option.value));
  // A view linked from another period can name a tag key this one does not offer. It stays in
  // the list, so the select says what the address asks for and the answer says why not.
  const missing = chosen
    .filter((value) => value.startsWith(TAG_PREFIX) && !known.has(value))
    .map(tagOption);
  return [...columns, ...tags, ...missing];
}

function choices(options: readonly Option[]) {
  return options.map((option) => (
    <option key={option.value} value={option.value} title={option.title}>
      {option.label}
    </option>
  ));
}

export function ExploreControls({ values, explore, update }: ExploreControlsProps) {
  const first = groupingValue(
    values.group_by === '' ? 'service' : values.group_by,
    values.group_by_tag,
  );
  const second = values.then_by === '' ? '' : groupingValue(values.then_by, values.then_by_tag);
  const options = optionsFor(explore?.tag_keys ?? [], [first, second]);
  const period = values.period === '' ? 'mtd' : values.period;
  const granularity = values.granularity === '' ? 'daily' : values.granularity;
  const metric = values.metric === '' ? 'effective_cost' : values.metric;
  const metrics = [...new Set([metric, ...(explore?.metrics_available ?? [])])];

  const chooseFirst = (value: string): void => {
    // Grouping by one thing twice is refused, so the second grouping makes way for the first.
    const change = groupingChange('group_by', value);
    update(value === second ? { ...change, then_by: '', then_by_tag: '' } : change);
  };
  const chooseSecond = (value: string): void => {
    update(value === '' ? { then_by: '', then_by_tag: '' } : groupingChange('then_by', value));
  };
  const choosePeriod = (value: string): void => {
    // A custom period starts as the window on screen, so choosing it never asks for a view
    // the route would refuse for want of dates.
    update(
      value === 'custom'
        ? {
            period: value,
            start: explore?.current.start ?? '',
            end: explore?.current.end ?? '',
          }
        : { period: value, start: '', end: '' },
    );
  };

  return (
    <form
      data-testid="explore-controls"
      aria-label="Cost Explorer view"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <label>
        Group by
        <select
          value={first}
          onChange={(event) => {
            chooseFirst(event.target.value);
          }}
        >
          {choices(options)}
        </select>
      </label>
      <label>
        Then by
        <select
          value={second}
          onChange={(event) => {
            chooseSecond(event.target.value);
          }}
        >
          <option value="">Nothing</option>
          {choices(options.filter((option) => option.value !== first))}
        </select>
      </label>
      <fieldset>
        <legend>Granularity</legend>
        {(['daily', 'monthly'] as const).map((value) => (
          <label key={value}>
            <input
              type="radio"
              name="granularity"
              value={value}
              checked={granularity === value}
              onChange={() => {
                update({ granularity: value });
              }}
            />
            {value === 'daily' ? 'Daily' : 'Monthly'}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Period</legend>
        {PRESETS.map((preset) => (
          <label key={preset.value}>
            <input
              type="radio"
              name="period"
              value={preset.value}
              checked={period === preset.value}
              onChange={() => {
                choosePeriod(preset.value);
              }}
            />
            {preset.name}
          </label>
        ))}
      </fieldset>
      {period === 'custom' ? (
        <>
          <label>
            From
            <input
              type="date"
              value={values.start}
              onChange={(event) => {
                update({ start: event.target.value });
              }}
            />
          </label>
          <label>
            To
            <input
              type="date"
              value={values.end}
              onChange={(event) => {
                update({ end: event.target.value });
              }}
            />
          </label>
        </>
      ) : null}
      <label>
        Measure
        <select
          value={metric}
          onChange={(event) => {
            update({ metric: event.target.value });
          }}
        >
          {metrics.map((value) => (
            <option key={value} value={value}>
              {METRIC_NAMES[value] ?? value}
            </option>
          ))}
        </select>
      </label>
    </form>
  );
}

interface ExploreFiltersProps {
  readonly values: ExploreValues;
  readonly update: (changes: ExploreChange) => void;
}

/** The filters in force, each a chip that takes itself away. */
export function ExploreFilters({ values, update }: ExploreFiltersProps) {
  const chips = chipsOf(values);
  return (
    <div data-testid="explore-filters" role="group" aria-label="Filters">
      {chips.length === 0 ? (
        <p>No filters. Choose a value in the table to filter by it.</p>
      ) : (
        <ul>
          {chips.map((chip) => (
            <li key={chip.label}>
              <button
                type="button"
                aria-label={`Remove the filter ${chip.label}`}
                onClick={() => {
                  update(chip.clear);
                }}
              >
                {chip.label}
                <span aria-hidden="true"> ×</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
