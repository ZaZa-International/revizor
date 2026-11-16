/* Русские подписи доменных справочников. Зеркалят backend taxonomy/enums;
   неизвестные ключи показываются как есть (контракт допускает расширение). */

const ASSET_TYPES: Record<string, string> = {
  telecom_well: 'Кабельный колодец',
  pole: 'Опора',
  telecom_cabinet: 'Телеком-шкаф',
  cable_line: 'Кабельная линия',
  other: 'Прочий объект',
};

const ASSET_TYPES_SHORT: Record<string, string> = {
  telecom_well: 'Колодец',
  pole: 'Опора',
  telecom_cabinet: 'Шкаф',
  cable_line: 'Кабель',
  other: 'Прочее',
};

const CONDITIONS: Record<string, string> = {
  ok: 'Исправен',
  damaged: 'Повреждение',
  damaged_cover: 'Повреждена крышка',
  missing_cover: 'Нет крышки',
  door_open: 'Открыта дверца',
  tilted: 'Наклон',
  subsided: 'Просадка',
  cable_sag: 'Провисание',
  cable_break: 'Обрыв кабеля',
  unknown: 'Не определено',
};

const DEFECT_TYPES: Record<string, string> = {
  missing_cover: 'Отсутствующая крышка колодца',
  damaged_cover: 'Повреждённая крышка колодца',
  well_subsidence: 'Просадка колодца',
  cabinet_damage: 'Повреждение корпуса шкафа',
  cabinet_door_open: 'Открытая дверца шкафа',
  pole_tilt: 'Наклон опоры',
  pole_damage: 'Повреждение опоры',
  cable_break: 'Обрыв кабеля',
  cable_sag: 'Провисание кабельной линии',
  other: 'Прочий дефект',
};

const PRIORITY_BANDS: Record<string, string> = {
  HIGH_PRIORITY: 'Высокий приоритет',
  MEDIUM_PRIORITY: 'Средний приоритет',
  LOW_PRIORITY: 'Низкий приоритет',
  NEEDS_REVIEW: 'Требует проверки',
};

const LIFECYCLE: Record<string, string> = {
  ACTIVE: 'В работе',
  INACTIVE: 'Неактивен',
  RETIRED: 'Выведен',
  UNKNOWN: 'Неизвестно',
};

const GEO_STATUS: Record<string, string> = {
  CONFIRMED: 'Подтверждена',
  ESTIMATED: 'Оценочная',
  UNAVAILABLE: 'Нет GPS',
  INVALID: 'Некорректная',
};

const JOB_STATUS: Record<string, string> = {
  PENDING: 'Ожидает',
  QUEUED: 'В очереди',
  PROCESSING: 'Обработка',
  COMPLETED: 'Завершена',
  PARTIALLY_COMPLETED: 'Частично завершена',
  FAILED: 'Ошибка',
  CANCELLED: 'Отменена',
};

const JOB_STAGES: Record<string, string> = {
  VALIDATION: 'Валидация',
  STORAGE: 'Сохранение',
  FRAME_EXTRACTION: 'Извлечение кадров',
  QUALITY_GATE: 'Контроль качества',
  PRIVACY_FILTER: 'Приватность',
  INFERENCE: 'Инференс ML',
  NORMALIZATION: 'Нормализация',
  TRACKING: 'Трекинг',
  GEOLOCATION: 'Геопривязка',
  DEDUPLICATION: 'Дедупликация',
  RISK_SCORING: 'Оценка риска',
  PERSISTENCE: 'Сохранение результатов',
  COMPLETED: 'Завершено',
};

const DEDUP: Record<string, string> = {
  MATCHED: 'Совпал с объектом',
  NEW_ASSET: 'Новый объект',
  POSSIBLE_MATCH: 'Возможное совпадение',
  AMBIGUOUS: 'Неоднозначно',
};

const REVIEW_STATUS: Record<string, string> = {
  UNREVIEWED: 'Не проверено',
  CONFIRMED: 'Подтверждено',
  REJECTED: 'Отклонено',
  CORRECTED: 'Скорректировано',
  NEEDS_MORE_INFORMATION: 'Нужны данные',
};

const REVIEW_DECISIONS: Record<string, string> = {
  CONFIRMED: 'Подтвердить',
  REJECTED: 'Отклонить',
  CORRECTED: 'Скорректировать',
  NEEDS_MORE_INFORMATION: 'Нужны данные',
};

const DEFECT_STATUS: Record<string, string> = {
  OPEN: 'Открыт',
  CONFIRMED: 'Подтверждён',
  IN_PROGRESS: 'В работе',
  RESOLVED: 'Устранён',
  REJECTED: 'Отклонён',
};

const FRAME_STATUS: Record<string, string> = {
  PROCESSED: 'Обработан',
  REJECTED: 'Отклонён',
  FAILED: 'Ошибка',
  SKIPPED: 'Пропущен',
};

const CHANGE_SOURCE: Record<string, string> = {
  ML_PREDICTION: 'ML-предсказание',
  HUMAN_REVIEW: 'Проверка оператором',
  MANUAL_EDIT: 'Ручное изменение',
  SYSTEM: 'Система',
};

const ROLES: Record<string, string> = {
  ADMIN: 'Администратор',
  OPERATOR: 'Оператор',
  VIEWER: 'Наблюдатель',
  SERVICE: 'Сервис',
};

function lookup(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return '—';
  return map[key] ?? key;
}

export const label = {
  assetType: (k: string | null | undefined) => lookup(ASSET_TYPES, k),
  assetTypeShort: (k: string | null | undefined) => lookup(ASSET_TYPES_SHORT, k),
  condition: (k: string | null | undefined) => lookup(CONDITIONS, k),
  defectType: (k: string | null | undefined) => lookup(DEFECT_TYPES, k),
  priorityBand: (k: string | null | undefined) => lookup(PRIORITY_BANDS, k),
  lifecycle: (k: string | null | undefined) => lookup(LIFECYCLE, k),
  geoStatus: (k: string | null | undefined) => lookup(GEO_STATUS, k),
  jobStatus: (k: string | null | undefined) => lookup(JOB_STATUS, k),
  jobStage: (k: string | null | undefined) => lookup(JOB_STAGES, k),
  dedup: (k: string | null | undefined) => lookup(DEDUP, k),
  reviewStatus: (k: string | null | undefined) => lookup(REVIEW_STATUS, k),
  reviewDecision: (k: string | null | undefined) => lookup(REVIEW_DECISIONS, k),
  defectStatus: (k: string | null | undefined) => lookup(DEFECT_STATUS, k),
  frameStatus: (k: string | null | undefined) => lookup(FRAME_STATUS, k),
  changeSource: (k: string | null | undefined) => lookup(CHANGE_SOURCE, k),
  role: (k: string | null | undefined) => lookup(ROLES, k),
};

export const assetTypeOptions = Object.entries(ASSET_TYPES).map(([value, name]) => ({ value, name }));
export const conditionOptions = Object.entries(CONDITIONS).map(([value, name]) => ({ value, name }));
export const defectTypeOptions = Object.entries(DEFECT_TYPES).map(([value, name]) => ({ value, name }));
export const defectStatusOptions = Object.entries(DEFECT_STATUS).map(([value, name]) => ({ value, name }));
export const priorityBandOptions = Object.entries(PRIORITY_BANDS).map(([value, name]) => ({ value, name }));
export const lifecycleOptions = Object.entries(LIFECYCLE).map(([value, name]) => ({ value, name }));
export const reviewStatusOptions = Object.entries(REVIEW_STATUS).map(([value, name]) => ({ value, name }));
export const dedupOptions = Object.entries(DEDUP).map(([value, name]) => ({ value, name }));

export type Tone = 'ok' | 'warn' | 'crit' | 'accent' | 'neutral';

export const bandTone: Record<string, Tone> = {
  HIGH_PRIORITY: 'crit',
  MEDIUM_PRIORITY: 'warn',
  LOW_PRIORITY: 'ok',
  NEEDS_REVIEW: 'accent',
};

export const conditionTone = (condition: string | null | undefined): Tone => {
  if (!condition || condition === 'unknown') return 'neutral';
  if (condition === 'ok') return 'ok';
  if (['missing_cover', 'cable_break'].includes(condition)) return 'crit';
  return 'warn';
};

export const defectStatusTone: Record<string, Tone> = {
  OPEN: 'warn',
  CONFIRMED: 'crit',
  IN_PROGRESS: 'accent',
  RESOLVED: 'ok',
  REJECTED: 'neutral',
};

export const jobStatusTone: Record<string, Tone> = {
  PENDING: 'neutral',
  QUEUED: 'neutral',
  PROCESSING: 'accent',
  COMPLETED: 'ok',
  PARTIALLY_COMPLETED: 'warn',
  FAILED: 'crit',
  CANCELLED: 'neutral',
};

export const reviewStatusTone: Record<string, Tone> = {
  UNREVIEWED: 'warn',
  CONFIRMED: 'ok',
  REJECTED: 'neutral',
  CORRECTED: 'accent',
  NEEDS_MORE_INFORMATION: 'warn',
};

export const dedupTone: Record<string, Tone> = {
  MATCHED: 'ok',
  NEW_ASSET: 'accent',
  POSSIBLE_MATCH: 'warn',
  AMBIGUOUS: 'warn',
};

export const geoTone: Record<string, Tone> = {
  CONFIRMED: 'ok',
  ESTIMATED: 'warn',
  UNAVAILABLE: 'neutral',
  INVALID: 'crit',
};

export const severityTone = (severity: number | null | undefined): Tone => {
  if (severity == null) return 'neutral';
  if (severity >= 4) return 'crit';
  if (severity === 3) return 'warn';
  return 'ok';
};