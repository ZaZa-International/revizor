/* Синтетические «кадры камеры» для demo-режима: схематичная SVG-сцена
   с bbox детекции. Честно маркированы как синтетические. */
import type { Observation } from '../api/types';
import { getBbox } from '../lib/bbox';

function hashSeed(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function seeded(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const TYPE_SHAPES: Record<string, (x: number, y: number, w: number, h: number) => string> = {
  telecom_well: (x, y, w, h) =>
    `<ellipse cx="${x + w / 2}" cy="${y + h * 0.72}" rx="${w * 0.42}" ry="${h * 0.16}" fill="#3a4a52" stroke="#55707a" stroke-width="3"/>` +
    `<ellipse cx="${x + w / 2}" cy="${y + h * 0.7}" rx="${w * 0.3}" ry="${h * 0.11}" fill="#22333c"/>`,
  pole: (x, y, w, h) =>
    `<rect x="${x + w * 0.44}" y="${y}" width="${w * 0.12}" height="${h}" fill="#4a5a62" rx="3"/>` +
    `<path d="M${x + w * 0.1} ${y + h * 0.12} H${x + w * 0.9}" stroke="#55707a" stroke-width="4"/>` +
    `<path d="M${x + w * 0.15} ${y + h * 0.12} q ${w * 0.35} ${h * 0.1} ${w * 0.7} 0" stroke="#6e868c" stroke-width="2" fill="none"/>`,
  telecom_cabinet: (x, y, w, h) =>
    `<rect x="${x + w * 0.15}" y="${y + h * 0.1}" width="${w * 0.7}" height="${h * 0.85}" fill="#3d5a52" stroke="#55707a" stroke-width="3" rx="4"/>` +
    `<line x1="${x + w * 0.5}" y1="${y + h * 0.14}" x2="${x + w * 0.5}" y2="${y + h * 0.9}" stroke="#22333c" stroke-width="3"/>` +
    `<rect x="${x + w * 0.55}" y="${y + h * 0.45}" width="${w * 0.06}" height="${h * 0.1}" fill="#75d7cc" opacity="0.7"/>`,
  cable_line: (x, y, w, h) =>
    `<path d="M${x} ${y + h * 0.3} Q ${x + w / 2} ${y + h * 0.75} ${x + w} ${y + h * 0.28}" stroke="#6e868c" stroke-width="5" fill="none"/>` +
    `<path d="M${x} ${y + h * 0.42} Q ${x + w / 2} ${y + h * 0.9} ${x + w} ${y + h * 0.4}" stroke="#4a5a62" stroke-width="3" fill="none"/>`,
};

export function demoFrameSvg(obs: Observation, withBbox = true): string {
  const rnd = seeded(hashSeed(obs.id));
  const w = obs.image_width || 1920;
  const h = obs.image_height || 1080;
  const horizon = h * (0.42 + rnd() * 0.08);
  const buildings: string[] = [];
  let bx = -20;
  while (bx < w + 40) {
    const bw = 90 + rnd() * 160;
    const bh = 90 + rnd() * (horizon * 0.7);
    const shade = 24 + Math.floor(rnd() * 18);
    buildings.push(
      `<rect x="${bx}" y="${horizon - bh}" width="${bw}" height="${bh}" fill="rgb(${shade},${shade + 10},${shade + 14})"/>`,
    );
    for (let wy = horizon - bh + 18; wy < horizon - 14; wy += 26) {
      for (let wx = bx + 12; wx < bx + bw - 14; wx += 24) {
        if (rnd() > 0.62) {
          buildings.push(`<rect x="${wx}" y="${wy}" width="9" height="12" fill="#5a6a58" opacity="${0.25 + rnd() * 0.4}"/>`);
        }
      }
    }
    bx += bw + 6 + rnd() * 20;
  }
  const shapeFn = TYPE_SHAPES[obs.object_type] ?? TYPE_SHAPES.telecom_cabinet;
  const bb = getBbox(obs);
  const bboxMarkup =
    withBbox && bb
      ? `<rect x="${bb.x_min}" y="${bb.y_min}" width="${bb.x_max - bb.x_min}" height="${bb.y_max - bb.y_min}" fill="none" stroke="#75d7cc" stroke-width="4"/>` +
        `<rect x="${bb.x_min}" y="${bb.y_min - 34}" width="${(obs.object_type.length * 9 + 130)}" height="30" fill="#75d7cc"/>` +
        `<text x="${bb.x_min + 8}" y="${bb.y_min - 12}" font-family="monospace" font-size="19" fill="#06231f">${obs.object_type} ${(obs.detector_confidence ?? 0).toFixed(2)}</text>` +
        shapeFn(bb.x_min + 10, bb.y_min + 10, bb.x_max - bb.x_min - 20, bb.y_max - bb.y_min - 20)
      : '';
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" role="img" aria-label="Синтетический демо-кадр">` +
    `<rect width="${w}" height="${h}" fill="#101c24"/>` +
    `<rect width="${w}" height="${horizon}" fill="#16242e"/>` +
    buildings.join('') +
    `<rect y="${horizon}" width="${w}" height="${h - horizon}" fill="#1a262e"/>` +
    `<path d="M0 ${h} L${w * 0.42} ${horizon} L${w * 0.58} ${horizon} L${w} ${h} Z" fill="#222e36"/>` +
    `<path d="M${w * 0.5} ${h} L${w * 0.5} ${horizon}" stroke="#3a4a52" stroke-width="6" stroke-dasharray="40 30"/>` +
    `<rect x="${w * 0.02}" y="${horizon}" width="${w * 0.16}" height="${h - horizon}" fill="#243038" opacity="0.7"/>` +
    bboxMarkup +
    `<rect x="0" y="${h - 46}" width="${w}" height="46" fill="#091318" opacity="0.82"/>` +
    `<text x="20" y="${h - 16}" font-family="monospace" font-size="21" fill="#a0b3b5">DEMO · СИНТЕТИЧЕСКИЙ КАДР · ${obs.model_name ?? 'mock'} ${obs.model_version ?? ''}</text>` +
    `<text x="${w - 320}" y="${h - 16}" font-family="monospace" font-size="21" fill="#75d7cc">${(obs.observed_at ?? '').replace('T', ' ').slice(0, 19)}</text>` +
    `</svg>`;
  return svg;
}

export function demoFrameDataUrl(obs: Observation, withBbox = true): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(demoFrameSvg(obs, withBbox))}`;
}