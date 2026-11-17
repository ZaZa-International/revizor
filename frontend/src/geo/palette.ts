/* Семантическая палитра карты. Цвет дублирует токены дизайн-системы (tokens.css):
   crit/warn/ok/accent. Цвет — не единственный носитель состояния (форма + текст в панелях). */

export const BAND_COLORS: Record<string, string> = {
  HIGH_PRIORITY: '#E66C61',
  MEDIUM_PRIORITY: '#F0A45C',
  LOW_PRIORITY: '#9DBFA8',
  NEEDS_REVIEW: '#75D7CC',
};

export const GEO_COLORS = {
  accent: '#75D7CC',
  accentDim: '#3D8A81',
  accentHeat: 'rgba(117,215,204,0.55)',
  accentSoft: 'rgba(117,215,204,0.14)',
  warn: '#F0A45C',
  crit: '#E66C61',
  ok: '#9DBFA8',
  ink: '#E9EEE9',
  bg: '#091318',
  raised: '#1C3038',
  control: '#55707A',
  coverageLow: '#2A4550',
  coverageHigh: '#75D7CC',
} as const;

export const DEFECT_RING_SEVERITY_MIN = 4;
