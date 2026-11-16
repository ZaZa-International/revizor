const dateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

const dateTimeFmt = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const timeFmt = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' });

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : dateFmt.format(d);
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : dateTimeFmt.format(d);
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : timeFmt.format(d);
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return '—';
  const diff = Date.now() - d;
  const min = Math.round(diff / 60_000);
  if (min < 1) return 'только что';
  if (min < 60) return `${min} мин назад`;
  const hours = Math.round(min / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} дн назад`;
  return fmtDate(iso);
}

export function fmtNumber(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function fmtPercent(ratio: number | null | undefined, digits = 1): string {
  if (ratio == null || Number.isNaN(ratio)) return '—';
  return `${fmtNumber(ratio * 100, digits)}%`;
}

export function fmtConfidence(value: number | null | undefined): string {
  if (value == null) return '—';
  return fmtNumber(value * 100, 0) + '%';
}

export function fmtCoord(lon: number | null | undefined, lat: number | null | undefined): string {
  if (lon == null || lat == null) return 'нет координат';
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

export function fmtLonLat(lon: number, lat: number): string {
  return `${lon.toFixed(5)}, ${lat.toFixed(5)}`;
}

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} КБ`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} МБ`;
  return `${(bytes / 1024 ** 3).toFixed(2)} ГБ`;
}

export function fmtDistance(meters: number | null | undefined): string {
  if (meters == null) return '—';
  if (meters < 1000) return `${Math.round(meters)} м`;
  return `${(meters / 1000).toFixed(1)} км`;
}

export function shortId(id: string | null | undefined): string {
  if (!id) return '—';
  return id.slice(0, 8);
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}