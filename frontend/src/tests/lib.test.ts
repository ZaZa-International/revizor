import { describe, expect, it } from 'vitest';
import { fmtBytes, fmtConfidence, fmtCoord, fmtDistance, fmtNumber, fmtPercent, plural, shortId } from '../lib/format';
import { getBbox, bboxStyle } from '../lib/bbox';
import { label, conditionTone, severityTone, bandTone } from '../lib/labels';
import type { Observation } from '../api/types';

describe('format', () => {
  it('отсутствующие данные — прочерк, не ноль', () => {
    expect(fmtNumber(null)).toBe('—');
    expect(fmtNumber(undefined)).toBe('—');
    expect(fmtCoord(null, null)).toBe('нет координат');
    expect(fmtDistance(null)).toBe('—');
    expect(fmtBytes(undefined)).toBe('—');
    expect(fmtConfidence(null)).toBe('—');
  });

  it('числа и проценты', () => {
    expect(fmtNumber(1234)).toBe('1\u00A0234');
    expect(fmtPercent(0.1515, 1)).toBe('15,2%');
    expect(fmtConfidence(0.92)).toBe('92%');
  });

  it('координаты: широта, долгота (не перепутаны)', () => {
    expect(fmtCoord(37.6173, 55.7558)).toBe('55.75580, 37.61730');
  });

  it('единицы размера файла и дистанции', () => {
    expect(fmtBytes(2048)).toBe('2.0 КБ');
    expect(fmtBytes(5 * 1024 ** 3)).toBe('5.00 ГБ');
    expect(fmtDistance(950)).toBe('950 м');
    expect(fmtDistance(2400)).toBe('2.4 км');
  });

  it('русские склонения', () => {
    expect(plural(1, 'объект', 'объекта', 'объектов')).toBe('объект');
    expect(plural(2, 'объект', 'объекта', 'объектов')).toBe('объекта');
    expect(plural(5, 'объект', 'объекта', 'объектов')).toBe('объектов');
    expect(plural(11, 'объект', 'объекта', 'объектов')).toBe('объектов');
    expect(plural(21, 'объект', 'объекта', 'объектов')).toBe('объект');
  });

  it('shortId', () => {
    expect(shortId('f47ac10b-58cc-4372-a567-0e02b2c3d479')).toBe('f47ac10b');
    expect(shortId(null)).toBe('—');
  });
});

describe('bbox', () => {
  const obs = {
    bbox: { x_min: 100, y_min: 200, x_max: 500, y_max: 600 },
    image_width: 1920,
    image_height: 1080,
  } as unknown as Observation;

  it('валидный bbox парсится', () => {
    expect(getBbox(obs)).toEqual({ x_min: 100, y_min: 200, x_max: 500, y_max: 600 });
  });

  it('невалидный bbox (max<=min) отклоняется', () => {
    expect(getBbox({ bbox: { x_min: 500, y_min: 0, x_max: 100, y_max: 10 } } as unknown as Observation)).toBeNull();
    expect(getBbox({ bbox: null } as unknown as Observation)).toBeNull();
  });

  it('стиль overlay в процентах от кадра', () => {
    const s = bboxStyle(obs)!;
    expect(s.left).toBe(`${(100 / 1920) * 100}%`);
    expect(s.width).toBe(`${(400 / 1920) * 100}%`);
    expect(s.height).toBe(`${(400 / 1080) * 100}%`);
  });

  it('без размеров кадра overlay не строится', () => {
    expect(bboxStyle({ ...obs, image_width: null } as Observation)).toBeNull();
  });
});

describe('labels и семантика', () => {
  it('русские подписи доменных справочников', () => {
    expect(label.assetType('telecom_well')).toBe('Кабельный колодец');
    expect(label.condition('missing_cover')).toBe('Нет крышки');
    expect(label.defectType('pole_tilt')).toBe('Наклон опоры');
    expect(label.jobStatus('PARTIALLY_COMPLETED')).toBe('Частично завершена');
    expect(label.reviewDecision('CORRECTED')).toBe('Скорректировать');
  });

  it('неизвестный ключ показывается как есть (расширяемость контракта)', () => {
    expect(label.assetType('future_type')).toBe('future_type');
    expect(label.condition(null)).toBe('—');
  });

  it('тяжесть и приоритет — разные семантики', () => {
    expect(severityTone(5)).toBe('crit');
    expect(severityTone(3)).toBe('warn');
    expect(severityTone(1)).toBe('ok');
    expect(bandTone.NEEDS_REVIEW).toBe('accent');
    expect(bandTone.LOW_PRIORITY).toBe('ok');
  });

  it('состояние ok не трактуется как дефект', () => {
    expect(conditionTone('ok')).toBe('ok');
    expect(conditionTone('unknown')).toBe('neutral');
    expect(conditionTone('missing_cover')).toBe('crit');
    expect(conditionTone('door_open')).toBe('warn');
  });
});