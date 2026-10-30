export const number = (n: number) => Intl.NumberFormat().format(n);
export const amount = (n: number) =>
  Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
export const metric = (n: number | null | undefined) =>
  n == null ? '—' : n.toFixed(3);
export const percent = (n: number) => `${(n * 100).toFixed(1)}%`;
export const date = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
export const day = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
export const model = (name: string) =>
  ({
    dummy_prior: 'Baseline',
    logistic_regression: 'Logistic regression',
    random_forest: 'Random forest',
    xgboost: 'XGBoost',
  })[name] ?? name;
/** Display label for a user-chosen column: known acronyms upper-cased, snake_case spaced. */
export const column = (name: string) => {
  const text = name.replaceAll('_', ' ');
  return /^(mrr|arr|acv|ltv|nps)$/i.test(text)
    ? text.toUpperCase()
    : text[0].toUpperCase() + text.slice(1);
};
/**
 * Average precision only means something next to its chance level (the churn rate):
 * a random ranking scores the positive rate. Lift = AP / chance.
 */
export function quality(
  ap: number | null | undefined,
  chance: number | null | undefined,
) {
  if (ap == null || !chance) return null;
  const lift = ap / chance;
  const band =
    lift >= 3
      ? 'Strong'
      : lift >= 2
        ? 'Useful'
        : lift >= 1.3
          ? 'Weak'
          : 'Not useful';
  const tone =
    lift >= 3
      ? 'success'
      : lift >= 2
        ? 'brand'
        : lift >= 1.3
          ? 'warning'
          : 'danger';
  return { lift, band, tone, chance } as const;
}
