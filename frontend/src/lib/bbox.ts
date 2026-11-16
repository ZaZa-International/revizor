import type { Observation } from '../api/types';

export interface Bbox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export function getBbox(obs: Pick<Observation, 'bbox'>): Bbox | null {
  const b = obs.bbox as Record<string, unknown> | null | undefined;
  if (!b) return null;
  const vals = [b.x_min, b.y_min, b.x_max, b.y_max].map(Number);
  if (vals.some((v) => Number.isNaN(v))) return null;
  const [x_min, y_min, x_max, y_max] = vals;
  if (x_max <= x_min || y_max <= y_min) return null;
  return { x_min, y_min, x_max, y_max };
}

export function bboxStyle(obs: Observation): React.CSSProperties | null {
  const b = getBbox(obs);
  if (!b || !obs.image_width || !obs.image_height) return null;
  return {
    left: `${(b.x_min / obs.image_width) * 100}%`,
    top: `${(b.y_min / obs.image_height) * 100}%`,
    width: `${((b.x_max - b.x_min) / obs.image_width) * 100}%`,
    height: `${((b.y_max - b.y_min) / obs.image_height) * 100}%`,
  };
}