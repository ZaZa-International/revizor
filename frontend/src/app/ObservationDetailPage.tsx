import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useObservation, useReviews } from '../data/hooks';
import { Badge, EmptyState, ErrorState, KeyValue, LoadingState, Severity, Status } from '../components/ui';
import { IconChevronLeft, IconExternal } from '../components/icons';
import { dedupTone, label, reviewStatusTone } from '../lib/labels';
import { fmtCoord, fmtDateTime, fmtNumber, fmtPercent } from '../lib/format';
import { bboxStyle } from '../lib/bbox';

export default function ObservationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const obs = useObservation(id);
  const reviews = useReviews({ observation_id: id, page_size: 50 });
  const [imgFailed, setImgFailed] = useState(false);

  if (obs.isPending) return <LoadingState label="Загрузка наблюдения…" />;
  if (obs.error) return <ErrorState error={obs.error} onRetry={() => obs.refetch()} />;
  const o = obs.data!;
  const style = bboxStyle(o);
  const corrected = o.review_status === 'CORRECTED';

  return (
    <div>
      <div className="page-head">
        <div>
          <Link className="link small" to="/app/observations">
            <IconChevronLeft className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} /> Наблюдения
          </Link>
          <h1 style={{ marginTop: 8 }}>
            {label.assetType(o.object_type)} · {label.condition(o.effective_condition ?? o.condition_class)}
          </h1>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            <Status tone={reviewStatusTone[o.review_status] ?? 'neutral'}>{label.reviewStatus(o.review_status)}</Status>
            <Status tone={dedupTone[o.dedup_result ?? ''] ?? 'neutral'} shape="square">{label.dedup(o.dedup_result)}</Status>
            <Badge>{fmtDateTime(o.observed_at)}</Badge>
          </div>
        </div>
        <div className="page-head-actions">
          {o.asset_id && (
            <Link className="btn" to={`/app/assets/${o.asset_id}`}>Паспорт объекта</Link>
          )}
          <Link className="btn btn-primary" to={`/app/reviews?obs=${o.id}`}>К проверке</Link>
        </div>
      </div>

      <div className="detail-grid">
        <section className="panel" aria-label="Кадр наблюдения">
          <div className="panel-head">
            <h2 className="panel-title">Кадр</h2>
            {o.image_url && !imgFailed && (
              <a className="link small" href={o.image_url} target="_blank" rel="noreferrer">
                оригинал <IconExternal className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} />
              </a>
            )}
          </div>
          <div className="panel-body">
            {o.image_url && !imgFailed ? (
              <div className="frame-view">
                <img src={o.image_url} alt={`Кадр наблюдения: ${label.assetType(o.object_type)}`} onError={() => setImgFailed(true)} />
                {style && (
                  <div className="frame-bbox" style={style}>
                    <span className="frame-bbox-label">
                      {o.object_type} {fmtPercent(o.detector_confidence, 0)}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <EmptyState title="Кадр недоступен">
                Presigned-ссылка могла истечь или хранилище недоступно. Метаданные наблюдения сохранены.
              </EmptyState>
            )}
            <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
              {o.image_width && o.image_height ? `${o.image_width}×${o.image_height} px · ` : ''}
              bbox в абсолютных пикселях исходного кадра. Анонимизация в MVP не применяется (privacy filter — NOT_APPLIED); кадр показан как есть.
            </p>
          </div>
        </section>

        <section className="panel" aria-label="Предсказание и проверка">
          <div className="panel-head">
            <h2 className="panel-title">ML → эффективное состояние</h2>
          </div>
          <div className="panel-body">
            <table className="compare-table">
              <thead>
                <tr>
                  <th>Параметр</th>
                  <th>Исходное (ML)</th>
                  <th>Эффективное</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Тип объекта</td>
                  <td>{label.assetType(o.object_type)}</td>
                  <td className={corrected && o.effective_asset_type !== o.object_type ? 'changed' : ''}>
                    {label.assetType(o.effective_asset_type ?? o.object_type)}
                  </td>
                </tr>
                <tr>
                  <td>Состояние</td>
                  <td>{label.condition(o.condition_class)}</td>
                  <td className={corrected && o.effective_condition !== o.condition_class ? 'changed' : ''}>
                    {label.condition(o.effective_condition ?? o.condition_class)}
                  </td>
                </tr>
                <tr>
                  <td>Тяжесть</td>
                  <td><Severity value={o.severity} /></td>
                  <td className={corrected && o.effective_severity !== o.severity ? 'changed' : ''}>
                    <Severity value={o.effective_severity ?? o.severity} />
                  </td>
                </tr>
              </tbody>
            </table>
            <p className="faint small" style={{ margin: '10px 0 16px' }}>
              Исходное предсказание не затирается: исправления оператора хранятся отдельно (append-only review).
            </p>
            <KeyValue
              items={[
                ['Уверенность детектора', <span className="num">{fmtPercent(o.detector_confidence, 1)}</span>],
                ['Уверенность классификатора', <span className="num">{fmtPercent(o.classifier_confidence, 1)}</span>],
                ['Модель', <span className="mono small">{o.model_name} · {o.model_version}</span>],
                ['Дедупликация', label.dedup(o.dedup_result)],
                ['Dedup score', <span className="num">{o.dedup_score != null ? fmtNumber(o.dedup_score, 2) : '—'}</span>],
                ['Координаты', <span className="mono small">{fmtCoord(o.longitude, o.latitude)}</span>],
                ['Геолокация', `${label.geoStatus(o.geolocation_status)}${o.geolocation_source ? ` · ${o.geolocation_source}` : ''}`],
                ['Задача', o.processing_job_id ? <Link className="link mono small" to={`/app/jobs/${o.processing_job_id}`}>{o.processing_job_id.slice(0, 8)}</Link> : '—'],
                ['Инференс', fmtDateTime(o.detected_at)],
              ]}
            />
            {o.dedup_explanation && Object.keys(o.dedup_explanation).length > 0 && (
              <>
                <hr className="divider" />
                <p className="eyebrow" style={{ marginBottom: 8 }}>Объяснение дедупликации</p>
                <KeyValue
                  items={Object.entries(o.dedup_explanation as Record<string, unknown>)
                    .filter(([k]) => k !== 'demo')
                    .map(([k, v]) => [k, <span className="mono small">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>])}
                />
              </>
            )}
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 'var(--sp-5)' }} aria-label="История проверки">
        <div className="panel-head">
          <h2 className="panel-title">История проверки</h2>
          <Badge>append-only</Badge>
        </div>
        {reviews.isPending && <LoadingState />}
        {reviews.data && reviews.data.items.length === 0 && (
          <EmptyState title="Решений пока нет">Наблюдение ожидает проверки оператором.</EmptyState>
        )}
        {reviews.data && reviews.data.items.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Время</th>
                  <th>Решение</th>
                  <th>Исправления</th>
                  <th>Комментарий</th>
                </tr>
              </thead>
              <tbody>
                {reviews.data.items.map((r) => (
                  <tr key={r.id}>
                    <td className="muted">{fmtDateTime(r.reviewed_at ?? r.created_at)}</td>
                    <td>
                      <Status tone={r.decision === 'CONFIRMED' ? 'ok' : r.decision === 'REJECTED' ? 'neutral' : r.decision === 'CORRECTED' ? 'accent' : 'warn'}>
                        {label.reviewDecision(r.decision)}
                      </Status>
                    </td>
                    <td className="small">
                      {[
                        r.corrected_asset_type && `тип → ${label.assetType(r.corrected_asset_type)}`,
                        r.corrected_condition && `состояние → ${label.condition(r.corrected_condition)}`,
                        r.corrected_severity && `тяжесть → S${r.corrected_severity}`,
                        r.corrected_defect_type && `дефект → ${label.defectType(r.corrected_defect_type)}`,
                      ].filter(Boolean).join('; ') || '—'}
                    </td>
                    <td className="muted small">{r.comment ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}