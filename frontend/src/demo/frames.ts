/* Синтетические «кадры объезда» для demo-режима: дневная уличная сцена
   (дорога, тротуар, застройка) с объектом инфраструктуры в bbox детекции.
   Честно маркированы как синтетические; реальных кадров обследования в
   репозитории нет. Цвета захардкожены: data-URL SVG не видит CSS-токены. */
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

/* Объект «стоит» на нижней границе bbox: тень + силуэт по типу */
const TYPE_SHAPES: Record<string, (x: number, y: number, w: number, h: number) => string> = {
  telecom_well: (x, y, w, h) => {
    const cx = x + w / 2;
    const cy = y + h * 0.82;
    const rx = w * 0.4;
    const ry = h * 0.13;
    let treads = '';
    for (let i = -2; i <= 2; i++) {
      treads += `<line x1="${cx + i * rx * 0.3}" y1="${cy - ry * 0.7}" x2="${cx + i * rx * 0.3}" y2="${cy + ry * 0.7}" stroke="#3a4244" stroke-width="3"/>`;
    }
    return (
      `<ellipse cx="${cx}" cy="${cy + ry * 0.5}" rx="${rx * 1.15}" ry="${ry * 0.5}" fill="#3a4244" opacity="0.3"/>` +
      `<ellipse cx="${cx}" cy="${cy}" rx="${rx * 1.12}" ry="${ry * 1.25}" fill="#9aa2a0"/>` +
      `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="#4a5456" stroke="#333c3e" stroke-width="4"/>` +
      treads +
      `<ellipse cx="${cx}" cy="${cy}" rx="${rx * 0.3}" ry="${ry * 0.3}" fill="none" stroke="#333c3e" stroke-width="3"/>`
    );
  },
  pole: (x, y, w, h) => {
    const cx = x + w / 2;
    const top = y + h * 0.04;
    const base = y + h * 0.94;
    const bw = w * 0.09;
    return (
      `<ellipse cx="${cx}" cy="${base}" rx="${w * 0.2}" ry="${h * 0.035}" fill="#3a4244" opacity="0.3"/>` +
      `<path d="M${cx - bw} ${base} L${cx - bw * 0.6} ${top} H${cx + bw * 0.6} L${cx + bw} ${base} Z" fill="#b0b6b2"/>` +
      `<path d="M${cx + bw * 0.2} ${base} L${cx + bw * 0.35} ${top} H${cx + bw * 0.6} L${cx + bw} ${base} Z" fill="#8f9794"/>` +
      `<rect x="${cx - w * 0.34}" y="${top + h * 0.08}" width="${w * 0.68}" height="${h * 0.035}" fill="#6e7876" rx="3"/>` +
      `<circle cx="${cx - w * 0.28}" cy="${top + h * 0.075}" r="${w * 0.025}" fill="#4a5456"/>` +
      `<circle cx="${cx + w * 0.28}" cy="${top + h * 0.075}" r="${w * 0.025}" fill="#4a5456"/>` +
      `<path d="M${cx - w * 0.28} ${top + h * 0.08} Q ${cx} ${top + h * 0.2} ${cx + w * 0.28} ${top + h * 0.08}" stroke="#4a5456" stroke-width="3" fill="none"/>`
    );
  },
  telecom_cabinet: (x, y, w, h) => {
    const bx = x + w * 0.18;
    const bw = w * 0.64;
    const top = y + h * 0.1;
    const base = y + h * 0.94;
    const bh = base - top;
    let vents = '';
    for (let i = 0; i < 4; i++) {
      vents += `<rect x="${bx + bw * 0.12}" y="${top + bh * (0.62 + i * 0.07)}" width="${bw * 0.3}" height="${bh * 0.025}" fill="#3d5249" rx="2"/>`;
    }
    return (
      `<ellipse cx="${bx + bw / 2}" cy="${base}" rx="${bw * 0.62}" ry="${h * 0.035}" fill="#3a4244" opacity="0.3"/>` +
      `<rect x="${bx - bw * 0.06}" y="${base - bh * 0.05}" width="${bw * 1.12}" height="${bh * 0.07}" fill="#9aa2a0" rx="3"/>` +
      `<rect x="${bx}" y="${top}" width="${bw}" height="${bh}" fill="#5f7a70" stroke="#42574e" stroke-width="4" rx="6"/>` +
      `<line x1="${bx + bw / 2}" y1="${top + 6}" x2="${bx + bw / 2}" y2="${base - 6}" stroke="#42574e" stroke-width="4"/>` +
      `<rect x="${bx + bw * 0.54}" y="${top + bh * 0.4}" width="${bw * 0.06}" height="${bh * 0.12}" fill="#c8cfca" rx="3"/>` +
      vents +
      `<rect x="${bx + bw * 0.12}" y="${top + bh * 0.1}" width="${bw * 0.3}" height="${bh * 0.16}" fill="#42574e" rx="3"/>`
    );
  },
  cable_line: (x, y, w, h) => {
    const base = y + h * 0.94;
    const top = y + h * 0.12;
    const px1 = x + w * 0.1;
    const px2 = x + w * 0.9;
    const pole = (px: number) =>
      `<rect x="${px - w * 0.02}" y="${top}" width="${w * 0.04}" height="${base - top}" fill="#8f9794"/>` +
      `<rect x="${px - w * 0.07}" y="${top + h * 0.04}" width="${w * 0.14}" height="${h * 0.025}" fill="#6e7876"/>`;
    return (
      `<ellipse cx="${px1}" cy="${base}" rx="${w * 0.08}" ry="${h * 0.025}" fill="#3a4244" opacity="0.3"/>` +
      `<ellipse cx="${px2}" cy="${base}" rx="${w * 0.08}" ry="${h * 0.025}" fill="#3a4244" opacity="0.3"/>` +
      pole(px1) +
      pole(px2) +
      `<path d="M${px1} ${top + h * 0.05} Q ${(px1 + px2) / 2} ${top + h * 0.42} ${px2} ${top + h * 0.05}" stroke="#3a4244" stroke-width="5" fill="none"/>` +
      `<path d="M${px1} ${top + h * 0.1} Q ${(px1 + px2) / 2} ${top + h * 0.5} ${px2} ${top + h * 0.1}" stroke="#4a5456" stroke-width="3.5" fill="none"/>`
    );
  },
};

export function demoFrameSvg(obs: Observation, withBbox = true): string {
  const rnd = seeded(hashSeed(obs.id));
  const w = obs.image_width || 1920;
  const h = obs.image_height || 1080;
  const horizon = h * (0.42 + rnd() * 0.06);
  const vpX = w * (0.46 + rnd() * 0.08);

  const buildings: string[] = [];
  let bx = -20;
  while (bx < w + 40) {
    const bw = 100 + rnd() * 170;
    const bh = 80 + rnd() * (horizon * 0.62);
    const shade = 118 + Math.floor(rnd() * 26);
    buildings.push(
      `<rect x="${bx}" y="${horizon - bh}" width="${bw}" height="${bh}" fill="rgb(${shade},${shade + 8},${shade + 9})"/>`,
    );
    for (let wy = horizon - bh + 16; wy < horizon - 12; wy += 26) {
      for (let wx = bx + 12; wx < bx + bw - 14; wx += 24) {
        if (rnd() > 0.5) {
          buildings.push(`<rect x="${wx}" y="${wy}" width="9" height="12" fill="#c2ccc9" opacity="${0.3 + rnd() * 0.35}"/>`);
        }
      }
    }
    bx += bw + 4 + rnd() * 16;
  }

  const road =
    `<rect y="${horizon}" width="${w}" height="${h - horizon}" fill="#9aa2a0"/>` +
    `<path d="M0 ${h} L${vpX - w * 0.05} ${horizon} L${vpX + w * 0.05} ${horizon} L${w} ${h} Z" fill="#565e60"/>` +
    `<path d="M${w * 0.08} ${h} L${vpX - w * 0.045} ${horizon}" stroke="#c8cfca" stroke-width="5" opacity="0.7"/>` +
    `<path d="M${w * 0.92} ${h} L${vpX + w * 0.045} ${horizon}" stroke="#c8cfca" stroke-width="5" opacity="0.7"/>` +
    `<path d="M${w * 0.5} ${h} L${vpX} ${horizon}" stroke="#cfd4cc" stroke-width="7" stroke-dasharray="46 34" opacity="0.85"/>`;

  const shapeFn = TYPE_SHAPES[obs.object_type] ?? TYPE_SHAPES.telecom_cabinet;
  const bb = getBbox(obs);
  let bboxMarkup = '';
  if (withBbox && bb) {
    const label = `${obs.object_type} ${(obs.detector_confidence ?? 0).toFixed(2)}`;
    const chipW = Math.ceil(label.length * 11.4) + 16;
    const chipX = Math.max(8, Math.min(bb.x_min, w - chipW - 8));
    const chipY = bb.y_min >= 42 ? bb.y_min - 34 : bb.y_min + 8;
    bboxMarkup =
      shapeFn(bb.x_min + 10, bb.y_min + 10, bb.x_max - bb.x_min - 20, bb.y_max - bb.y_min - 20) +
      `<rect x="${bb.x_min}" y="${bb.y_min}" width="${bb.x_max - bb.x_min}" height="${bb.y_max - bb.y_min}" fill="none" stroke="#75d7cc" stroke-width="4"/>` +
      `<rect x="${chipX}" y="${chipY}" width="${chipW}" height="30" fill="#75d7cc"/>` +
      `<text x="${chipX + 8}" y="${chipY + 22}" font-family="monospace" font-size="19" fill="#06231f">${label}</text>`;
  }

  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" role="img" aria-label="Синтетический демо-кадр">` +
    `<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="#b9c6ca"/><stop offset="1" stop-color="#d9ded8"/>` +
    `</linearGradient></defs>` +
    `<rect width="${w}" height="${horizon}" fill="url(#sky)"/>` +
    buildings.join('') +
    road +
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