import {
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from 'react';
import { ApiError, errorMessage } from '../api/client';
import type { Tone } from '../lib/labels';
import { fmtNumber, plural } from '../lib/format';
import { IconAlert, IconChevronLeft, IconChevronRight, IconClose, IconSearch } from './icons';

/* ── Button ────────────────────────────────────────── */
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  block?: boolean;
}

export function Button({
  variant = 'default',
  size = 'md',
  loading = false,
  block = false,
  children,
  disabled,
  className = '',
  ...rest
}: ButtonProps) {
  const cls = [
    'btn',
    variant !== 'default' && `btn-${variant}`,
    size !== 'md' && `btn-${size}`,
    block && 'btn-block',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button className={cls} disabled={disabled || loading} {...rest}>
      {loading && <span className="spinner" aria-hidden />}
      {children}
    </button>
  );
}

/* ── Status / Badge / Severity ─────────────────────── */
export function Status({ tone, children, shape }: { tone: Tone; children: ReactNode; shape?: 'square' | 'diamond' }) {
  return (
    <span className={`status status-${tone}${shape ? ` status-${shape}` : ''}`}>{children}</span>
  );
}

export function Badge({
  tone,
  children,
  demo,
}: {
  tone?: 'accent' | 'warn' | 'crit';
  children: ReactNode;
  demo?: boolean;
}) {
  return <span className={`badge${demo ? ' badge-demo' : tone ? ` badge-${tone}` : ''}`}>{children}</span>;
}

export function Severity({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="muted small">—</span>;
  const v = Math.max(1, Math.min(5, Math.round(value)));
  return (
    <span className={`sev sev-${v}`} title={`Тяжесть ${v} из 5`}>
      <span className="sev-bars" aria-hidden>
        {[1, 2, 3, 4, 5].map((i) => (
          <i key={i} className={i <= v ? 'on' : ''} />
        ))}
      </span>
      S{v}
    </span>
  );
}

/* ── Поля ──────────────────────────────────────────── */
export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string | null;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {error ? (
        <span className="field-error" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </label>
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Поиск…',
  ariaLabel = 'Поиск',
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}) {
  return (
    <div className="search">
      <IconSearch className="search-icon" />
      <input
        className="input"
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
    </div>
  );
}

/* ── Состояния ─────────────────────────────────────── */
export function LoadingState({ label = 'Получаем данные…' }: { label?: string }) {
  return (
    <div className="state-block" role="status">
      <span className="spinner" aria-hidden />
      <p>{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="state-block">
      <IconAlert className="state-icon" />
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const isApi = error instanceof ApiError;
  return (
    <div className="state-block state-error" role="alert">
      <IconAlert className="state-icon" />
      <h3>{isApi && error.code === 'network_error' ? 'Сервер недоступен' : 'Ошибка загрузки'}</h3>
      <p>
        {errorMessage(error)}
        {isApi && error.requestId && (
          <>
            <br />
            <span className="mono faint">request_id: {error.requestId}</span>
          </>
        )}
      </p>
      {onRetry && (
        <Button onClick={onRetry} size="sm">
          Повторить
        </Button>
      )}
    </div>
  );
}

export function QueryState<T>({
  query,
  children,
  empty,
}: {
  query: { isPending: boolean; error: unknown; data?: T; refetch: () => void };
  children: (data: T) => ReactNode;
  empty?: ReactNode;
}) {
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (query.data === undefined) return empty ?? <EmptyState title="Нет данных" />;
  return <>{children(query.data)}</>;
}

/* ── Пагинация ─────────────────────────────────────── */
export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
  noun = ['запись', 'записи', 'записей'],
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
  noun?: [string, string, string];
}) {
  if (total === 0) return null;
  return (
    <div className="pagination">
      <span>
        <span className="num">{fmtNumber(total)}</span> {plural(total, ...noun)} · по {pageSize} · стр.{' '}
        <span className="num">
          {page}/{Math.max(1, pages)}
        </span>
      </span>
      <div className="pagination-controls">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Предыдущая страница">
          <IconChevronLeft className="icon-sm" />
        </Button>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Следующая страница">
          <IconChevronRight className="icon-sm" />
        </Button>
      </div>
    </div>
  );
}

/* ── Диалог (нативный) ─────────────────────────────── */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="dialog"
      style={wide ? { width: 'min(860px, calc(100vw - 32px))' } : undefined}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-label={title}
    >
      <div className="dialog-head">
        <h2 className="dialog-title">{title}</h2>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Закрыть">
          <IconClose className="icon-sm" />
        </Button>
      </div>
      <div className="dialog-body">{children}</div>
      {footer && <div className="dialog-foot">{footer}</div>}
    </dialog>
  );
}

/* ── Тосты ─────────────────────────────────────────── */
export interface ToastItem {
  id: number;
  kind: 'success' | 'error' | 'info';
  text: string;
}

let toastId = 0;
type ToastListener = (t: ToastItem) => void;
const listeners = new Set<ToastListener>();

export function toast(kind: ToastItem['kind'], text: string) {
  const item = { id: ++toastId, kind, text };
  listeners.forEach((l) => l(item));
}

export function ToastStack() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => {
    const listener: ToastListener = (t) => {
      setItems((prev) => [...prev.slice(-3), t]);
      setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== t.id)), 5200);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return (
    <div className="toast-stack" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Вкладки ───────────────────────────────────────── */
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          className="tab"
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined && <span className="num muted"> · {t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ── KeyValue / Progress / Legend ──────────────────── */
export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (
        <div key={i} style={{ display: 'contents' }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Progress({ value, tone }: { value: number; tone?: 'warn' | 'crit' }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`progress-fill${tone ? ` ${tone}` : ''}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Legend({ items }: { items: { color: string; label: string }[] }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span key={it.label} className="legend-item">
          <i className="legend-swatch" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/* ── DEMO-маркер ───────────────────────────────────── */
export function DemoBanner({ compact }: { compact?: boolean }) {
  if (compact) return <Badge demo>DEMO</Badge>;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--sp-3)',
        padding: '8px 16px',
        background: 'var(--warn-soft)',
        borderBottom: '1px solid rgba(240,164,92,0.4)',
        color: 'var(--warn)',
        fontSize: 'var(--text-small)',
      }}
      role="note"
    >
      <Badge demo>DEMO</Badge>
      <span>Синтетические данные для демонстрации. Не являются реальными измерениями инфраструктуры.</span>
    </div>
  );
}