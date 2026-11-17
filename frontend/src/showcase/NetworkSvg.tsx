/* Схематичная сеть городской инфраструктуры: улицы-трассы, узлы-объекты,
   зоны обследования. Прогресс 0..1 управляет прорисовкой (scrub-/load-анимация).
   Это схема, а не географическая карта — подписано в сценах. */

interface Node {
  x: number;
  y: number;
  kind: 'well' | 'cabinet' | 'pole';
  defect?: boolean;
  at: number;
}

interface Edge {
  d: string;
  at: number;
}

const NODES: Node[] = [
  { x: 150, y: 140, kind: 'cabinet', at: 0.3 },
  { x: 380, y: 140, kind: 'well', at: 0.34 },
  { x: 610, y: 140, kind: 'pole', at: 0.38 },
  { x: 840, y: 140, kind: 'well', defect: true, at: 0.42 },
  { x: 1070, y: 140, kind: 'cabinet', at: 0.46 },
  { x: 150, y: 300, kind: 'well', at: 0.4 },
  { x: 380, y: 300, kind: 'pole', at: 0.44 },
  { x: 610, y: 300, kind: 'well', defect: true, at: 0.48 },
  { x: 840, y: 300, kind: 'cabinet', at: 0.52 },
  { x: 1070, y: 300, kind: 'well', at: 0.56 },
  { x: 150, y: 460, kind: 'pole', at: 0.5 },
  { x: 380, y: 460, kind: 'well', at: 0.54 },
  { x: 610, y: 460, kind: 'cabinet', at: 0.58 },
  { x: 840, y: 460, kind: 'well', at: 0.62 },
  { x: 1070, y: 460, kind: 'pole', at: 0.66 },
  { x: 150, y: 620, kind: 'well', defect: true, at: 0.6 },
  { x: 380, y: 620, kind: 'cabinet', at: 0.64 },
  { x: 610, y: 620, kind: 'well', at: 0.68 },
  { x: 840, y: 620, kind: 'pole', at: 0.72 },
  { x: 1070, y: 620, kind: 'well', at: 0.76 },
];

const EDGES: Edge[] = [
  { d: 'M150 140 H1070', at: 0.16 },
  { d: 'M150 300 H1070', at: 0.22 },
  { d: 'M150 460 H1070', at: 0.28 },
  { d: 'M150 620 H1070', at: 0.34 },
  { d: 'M150 140 V620', at: 0.2 },
  { d: 'M380 140 V620', at: 0.26 },
  { d: 'M610 140 V620', at: 0.32 },
  { d: 'M840 140 V620', at: 0.38 },
  { d: 'M1070 140 V620', at: 0.44 },
  { d: 'M60 760 L1140 60', at: 0.5 },
];

const ZONES = [
  { x: 330, y: 250, w: 330, h: 260, label: 'ЗОНА ОБСЛЕДОВАНИЯ А', at: 0.66 },
  { x: 790, y: 410, w: 330, h: 260, label: 'ЗОНА ОБСЛЕДОВАНИЯ Б', at: 0.74 },
];

function nodeShape(n: Node, opacity: number) {
  const color = n.defect ? 'var(--crit)' : n.kind === 'cabinet' ? 'var(--ink)' : 'var(--accent)';
  const common = { opacity, style: { transition: 'opacity 200ms linear' } };
  if (n.kind === 'well') {
    return (
      <g {...common}>
        <circle cx={n.x} cy={n.y} r={7} fill="var(--bg)" stroke={color} strokeWidth={2.4} />
        <circle cx={n.x} cy={n.y} r={2.4} fill={color} />
      </g>
    );
  }
  if (n.kind === 'cabinet') {
    return (
      <g {...common}>
        <rect x={n.x - 6.5} y={n.y - 6.5} width={13} height={13} fill="var(--bg)" stroke={color} strokeWidth={2.4} rx={2} />
        <line x1={n.x} y1={n.y - 4} x2={n.x} y2={n.y + 4} stroke={color} strokeWidth={1.6} />
      </g>
    );
  }
  return (
    <g {...common}>
      <path d={`M${n.x} ${n.y - 8} L${n.x + 7.5} ${n.y + 6} L${n.x - 7.5} ${n.y + 6} Z`} fill="var(--bg)" stroke={color} strokeWidth={2.4} strokeLinejoin="round" />
    </g>
  );
}

export default function NetworkSvg({ progress, className }: { progress: number; className?: string }) {
  const p = Math.max(0, Math.min(1, progress));
  return (
    <svg className={className} viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice" aria-hidden>
      {EDGES.map((e, i) => {
        const local = Math.max(0, Math.min(1, (p - e.at) / 0.22));
        return (
          <path
            key={i}
            d={e.d}
            fill="none"
            stroke="var(--accent-dim)"
            strokeWidth={i === EDGES.length - 1 ? 3 : 1.8}
            strokeDasharray={i === EDGES.length - 1 ? '10 8' : undefined}
            pathLength={1}
            strokeDashoffset={i === EDGES.length - 1 ? undefined : 1 - local}
            opacity={i === EDGES.length - 1 ? local * 0.6 : 0.85}
            style={i === EDGES.length - 1 ? undefined : { strokeDasharray: 1 }}
          />
        );
      })}
      {ZONES.map((z, i) => {
        const local = Math.max(0, Math.min(1, (p - z.at) / 0.16));
        return (
          <g key={i} opacity={local}>
            <rect x={z.x} y={z.y} width={z.w} height={z.h} fill="var(--accent)" fillOpacity={0.05} stroke="var(--accent)" strokeWidth={1.2} strokeDasharray="6 6" rx={4} />
            <text x={z.x + 10} y={z.y + 22} fontFamily="var(--font-mono)" fontSize={13} fill="var(--accent)" letterSpacing="0.1em">
              {z.label}
            </text>
          </g>
        );
      })}
      {NODES.map((n, i) => {
        const local = Math.max(0, Math.min(1, (p - n.at) / 0.1));
        return <g key={i}>{nodeShape(n, local)}</g>;
      })}
      {NODES.filter((n) => n.defect).map((n, i) => {
        const local = Math.max(0, Math.min(1, (p - n.at - 0.12) / 0.12));
        return <circle key={`d${i}`} cx={n.x} cy={n.y} r={15} fill="none" stroke="var(--crit)" strokeWidth={1.6} opacity={local * 0.9} strokeDasharray="4 4" />;
      })}
    </svg>
  );
}