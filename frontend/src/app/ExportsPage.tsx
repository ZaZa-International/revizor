import { useState } from 'react';
import { useDataSource } from '../data/source';
import { getSession, ApiError } from '../api/client';
import { demoData } from '../demo/data';
import { Button, Field, toast } from '../components/ui';
import { IconExport } from '../components/icons';
import { assetTypeOptions, defectStatusOptions, priorityBandOptions, reviewStatusOptions } from '../lib/labels';
import { fmtDateTime } from '../lib/format';

type Entity = 'assets' | 'defects' | 'observations';

const ENTITIES: { id: Entity; name: string; desc: string }[] = [
  { id: 'assets', name: 'Объекты', desc: 'Реестр Asset: тип, состояние, приоритет, координаты, версии.' },
  { id: 'defects', name: 'Дефекты', desc: 'Дефекты с тяжестью, статусом, confidence и геолокацией объекта.' },
  { id: 'observations', name: 'Наблюдения', desc: 'Обнаружения: предсказание ML, эффективное состояние, review.' },
];

function csvEscape(v: unknown): string {
  const s = v == null ? '' : String(v);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function demoCsv(entity: Entity): string {
  if (entity === 'assets') {
    const head = ['id', 'external_id', 'asset_type', 'display_name', 'longitude', 'latitude', 'current_condition', 'current_severity', 'current_priority', 'priority_band', 'lifecycle_status', 'last_observed_at'];
    const rows = demoData.assets.map((a) => head.map((k) => csvEscape((a as Record<string, unknown>)[k])).join(','));
    return [head.join(','), ...rows].join('\n');
  }
  if (entity === 'defects') {
    const head = ['id', 'asset_id', 'defect_type', 'status', 'severity', 'first_detected_at', 'last_detected_at', 'observation_count'];
    const rows = demoData.defects.map((d) => head.map((k) => csvEscape((d as Record<string, unknown>)[k])).join(','));
    return [head.join(','), ...rows].join('\n');
  }
  const head = ['id', 'asset_id', 'object_type', 'condition_class', 'detector_confidence', 'severity', 'review_status', 'dedup_result', 'observed_at', 'longitude', 'latitude'];
  const rows = demoData.observations.map((o) => head.map((k) => csvEscape((o as Record<string, unknown>)[k])).join(','));
  return [head.join(','), ...rows].join('\n');
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export default function ExportsPage() {
  const { isDemo } = useDataSource();
  return (
    <div>
      <div className="page-head">
        <div>
          <p className="eyebrow">Выгрузки</p>
          <h1>Экспорт данных</h1>
          <p className="page-desc">
            Выгрузка реестров для отчётности и внешних систем. CSV — UTF-8 с BOM (Excel-friendly); XLSX формирует backend.
            {isDemo && ' В демо-режиме доступен CSV синтетических данных.'}
          </p>
        </div>
      </div>
      <div className="analytics-grid">
        {ENTITIES.map((e) => (
          <ExportCard key={e.id} entity={e.id} name={e.name} desc={e.desc} />
        ))}
      </div>
    </div>
  );
}

function ExportCard({ entity, name, desc }: { entity: Entity; name: string; desc: string }) {
  const { isDemo } = useDataSource();
  const [format, setFormat] = useState<'csv' | 'xlsx'>('csv');
  const [filter1, setFilter1] = useState('');
  const [filter2, setFilter2] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastExport, setLastExport] = useState<string | null>(null);

  const filterDefs =
    entity === 'assets'
      ? [
          { key: 'asset_type', label: 'Тип объекта', options: assetTypeOptions, value: filter1, set: setFilter1 },
          { key: 'priority_band', label: 'Приоритет', options: priorityBandOptions, value: filter2, set: setFilter2 },
        ]
      : entity === 'defects'
        ? [
            { key: 'status', label: 'Статус', options: defectStatusOptions, value: filter1, set: setFilter1 },
            { key: 'severity_min', label: 'Тяжесть от', options: [3, 4, 5].map((s) => ({ value: String(s), name: `S${s}` })), value: filter2, set: setFilter2 },
          ]
        : [
            { key: 'review_status', label: 'Проверка', options: reviewStatusOptions, value: filter1, set: setFilter1 },
            { key: 'object_type', label: 'Тип объекта', options: assetTypeOptions, value: filter2, set: setFilter2 },
          ];

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const stamp = new Date().toISOString().slice(0, 10);
      if (isDemo) {
        const csv = '\uFEFF' + demoCsv(entity);
        downloadBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `revizor-demo-${entity}-${stamp}.csv`);
        setLastExport(new Date().toISOString());
        toast('success', 'DEMO CSV выгружен (синтетические данные).');
        return;
      }
      const session = getSession();
      const params = new URLSearchParams({ format });
      filterDefs.forEach((f) => {
        if (f.value) params.set(f.key, f.value);
      });
      const res = await fetch(`/api/v1/exports/${entity}?${params}`, {
        headers: session ? { Authorization: `Bearer ${session.token}` } : {},
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new ApiError(body?.error?.code ?? 'internal_error', body?.error?.message ?? `Ошибка экспорта (${res.status})`, res.status);
      }
      const blob = await res.blob();
      const disposition = res.headers.get('Content-Disposition') ?? '';
      const match = disposition.match(/filename="?([^";]+)"?/);
      downloadBlob(blob, match?.[1] ?? `revizor-${entity}-${stamp}.${format}`);
      setLastExport(new Date().toISOString());
      toast('success', `Выгрузка ${name.toLowerCase()} готова.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка экспорта');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel" aria-label={`Экспорт: ${name}`}>
      <div className="panel-head">
        <h2 className="panel-title">{name}</h2>
        <IconExport style={{ color: 'var(--muted)' }} />
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
        <p className="muted small">{desc}</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-3)' }}>
          {filterDefs.map((f) => (
            <Field key={f.key} label={f.label}>
              <select className="select" value={f.value} onChange={(e) => f.set(e.target.value)}>
                <option value="">Все</option>
                {f.options.map((op) => <option key={op.value} value={op.value}>{op.name}</option>)}
              </select>
            </Field>
          ))}
        </div>
        <Field label="Формат">
          <select className="select" value={format} onChange={(e) => setFormat(e.target.value as 'csv' | 'xlsx')} disabled={isDemo}>
            <option value="csv">CSV</option>
            <option value="xlsx">XLSX</option>
          </select>
        </Field>
        {isDemo && <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>XLSX доступен только в live-режиме (формирует backend).</p>}
        {error && <div className="login-error" role="alert">{error}</div>}
        <Button variant="primary" loading={busy} onClick={() => void run()}>
          Скачать {format.toUpperCase()}
        </Button>
        <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>
          Экспорт выполняется с текущими фильтрами; права роли применяются сервером.
          {lastExport && <> Последняя выгрузка: {fmtDateTime(lastExport)}</>}
        </p>
      </div>
    </section>
  );
}