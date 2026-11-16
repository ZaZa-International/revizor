/* Infrastructure Inspection Walkthrough — презентационный сценарий на DEMO-данных.
   Никаких реальных мутаций: подтверждение на шаге 9 выполняется только по явному
   клику пользователя и только в demo-режиме (локальный demo provider). */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { demoData } from './data';
import { defaultLayers, type MapState, type MapStateApi } from '../geo/state';
import type { InspectionTab } from '../components/map/inspection';
import { Badge, Button } from '../components/ui';
import { IconChevronLeft, IconChevronRight, IconClose } from '../components/icons';

export interface WalkthroughContext {
  mapApi: MapStateApi;
  setTab: (t: InspectionTab) => void;
}

interface Step {
  title: string;
  text: string;
  waitForUser?: boolean;
  run: (ctx: WalkthroughContext) => void;
}

export interface WalkthroughTarget {
  assetId: string;
  currentObsId: string;
  previousObsId: string;
  position: [number, number];
}

export function findWalkthroughTarget(): WalkthroughTarget | null {
  const physical = demoData.history.find((h) => h.is_physical_change);
  if (!physical) return null;
  const asset = demoData.assets.find((a) => a.id === physical.asset_id);
  if (!asset || asset.longitude == null || asset.latitude == null) return null;
  const obs = demoData.observations
    .filter((o) => o.asset_id === asset.id)
    .sort((a, b) => (a.observed_at ?? '').localeCompare(b.observed_at ?? ''));
  if (obs.length < 2) return null;
  return {
    assetId: asset.id,
    previousObsId: obs[0].id,
    currentObsId: obs[obs.length - 1].id,
    position: [asset.longitude, asset.latitude],
  };
}

function buildSteps(target: WalkthroughTarget): Step[] {
  const [lon, lat] = target.position;
  return [
    {
      title: '3D-карта района',
      text: 'Открываем объёмную карту района обследования. Здания — реальные высоты OSM, объекты инфраструктуры геопривязаны к WGS84.',
      run: ({ mapApi, setTab }) => {
        setTab('overview');
        mapApi.update({
          mode: '3d',
          view: 'infrastructure',
          selection: null,
          camera: { center: [lon, lat], zoom: 15.3, pitch: 55, bearing: -15 },
        });
      },
    },
    {
      title: 'Инфраструктурные объекты',
      text: 'Слой активов: цвет — полоса приоритета, форма и текст в панели — тип и состояние. Объекты без GPS на карту не попадают.',
      run: ({ mapApi }) => {
        mapApi.update({ layers: { ...defaultLayers('infrastructure'), assets: true, observations: true } });
      },
    },
    {
      title: 'Слой дефектов',
      text: 'Включаем дефекты: кольцо вокруг точки объекта, цвет — тяжесть S4+ (красный) или S1–3 (янтарный).',
      run: ({ mapApi }) => {
        mapApi.update({
          layers: { ...defaultLayers('infrastructure'), assets: true, observations: true, defects: true },
          camera: { center: [lon, lat], zoom: 15.8, pitch: 55, bearing: -15 },
        });
      },
    },
    {
      title: 'Приближение к объекту',
      text: 'Камера приближается к колодцу с ухудшением состояния. Выбор объекта синхронизирован с панелью и URL.',
      run: ({ mapApi, setTab }) => {
        setTab('overview');
        mapApi.update({
          selection: { layer: 'assets', id: target.assetId },
          camera: { center: [lon, lat], zoom: 17, pitch: 60, bearing: -25 },
        });
      },
    },
    {
      title: 'Паспорт объекта',
      text: 'Контекстная панель показывает паспорт: состояние, приоритет, GPS-точность, связанные наблюдения и дефекты.',
      run: ({ mapApi, setTab }) => {
        setTab('overview');
        mapApi.select({ layer: 'assets', id: target.assetId });
      },
    },
    {
      title: 'Наблюдение',
      text: 'Открываем последнее наблюдение: кадр объезда, координаты, время, confidence модели и решение оператора — раздельно.',
      run: ({ mapApi, setTab }) => {
        setTab('overview');
        mapApi.select({ layer: 'observations', id: target.currentObsId });
      },
    },
    {
      title: 'Сравнение объездов',
      text: 'Сравниваем текущее и предыдущее наблюдение одного объекта: исходные ML-предсказания двух обследований.',
      run: ({ mapApi, setTab }) => {
        mapApi.select({ layer: 'assets', id: target.assetId });
        setTab('compare');
      },
    },
    {
      title: 'Физическое изменение',
      text: 'История состояния фиксирует переход damaged_cover → missing_cover между объездами. Запись помечена как физическое изменение.',
      run: ({ setTab }) => {
        setTab('history');
      },
    },
    {
      title: 'Подтверждение оператором',
      text: 'Нажмите «Подтвердить наблюдение (DEMO)» в панели наблюдения. Это локальная demo-операция; реальные данные не изменяются.',
      waitForUser: true,
      run: ({ mapApi, setTab }) => {
        setTab('overview');
        mapApi.select({ layer: 'observations', id: target.currentObsId });
      },
    },
    {
      title: 'История обновлена',
      text: 'Решение оператора зафиксировано в append-only журнале review, статус наблюдения обновлён. История состояния пополняется записью HUMAN_REVIEW при изменении состояния или приоритета объекта.',
      run: ({ mapApi, setTab }) => {
        mapApi.select({ layer: 'assets', id: target.assetId });
        setTab('history');
      },
    },
  ];
}

const STEP_DURATION_MS = 8000;

export interface WalkthroughApi {
  active: boolean;
  stepIndex: number;
  stepCount: number;
  playing: boolean;
  step: Step | null;
  start: () => void;
  exit: () => void;
  next: () => void;
  prev: () => void;
  togglePlay: () => void;
  notifyConfirmed: () => void;
}

export function useWalkthrough(ctx: WalkthroughContext, target: WalkthroughTarget | null): WalkthroughApi {
  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const snapshotRef = useRef<MapState | null>(null);
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;

  const steps = useMemo(() => (target ? buildSteps(target) : []), [target]);

  const runStep = useCallback(
    (index: number) => {
      const step = steps[index];
      if (!step) return;
      step.run(ctxRef.current);
      if (step.waitForUser) setPlaying(false);
    },
    [steps],
  );

  const start = useCallback(() => {
    if (!target || steps.length === 0) return;
    snapshotRef.current = ctxRef.current.mapApi.state;
    setActive(true);
    setStepIndex(0);
    setPlaying(true);
    runStep(0);
  }, [target, steps, runStep]);

  const exit = useCallback(() => {
    setActive(false);
    setPlaying(false);
    if (snapshotRef.current) {
      ctxRef.current.mapApi.update(snapshotRef.current);
      snapshotRef.current = null;
    }
  }, []);

  const next = useCallback(() => {
    if (stepIndex >= steps.length - 1) {
      setPlaying(false);
      return;
    }
    const ni = stepIndex + 1;
    setStepIndex(ni);
    runStep(ni);
  }, [stepIndex, steps, runStep]);

  const prev = useCallback(() => {
    if (stepIndex <= 0) return;
    const ni = stepIndex - 1;
    setStepIndex(ni);
    runStep(ni);
  }, [stepIndex, steps, runStep]);

  const togglePlay = useCallback(() => {
    setPlaying((p) => {
      if (!p && steps[stepIndex]?.waitForUser) return p;
      return !p;
    });
  }, [steps, stepIndex]);

  const notifyConfirmed = useCallback(() => {
    if (active && steps[stepIndex]?.waitForUser) next();
  }, [active, steps, stepIndex, next]);

  useEffect(() => {
    if (!active || !playing) return;
    const step = steps[stepIndex];
    if (!step || step.waitForUser) return;
    const timer = setTimeout(() => {
      if (document.hidden) return;
      if (stepIndex >= steps.length - 1) setPlaying(false);
      else next();
    }, STEP_DURATION_MS);
    return () => clearTimeout(timer);
  }, [active, playing, stepIndex, steps, next]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  return {
    active,
    stepIndex,
    stepCount: steps.length,
    playing,
    step: steps[stepIndex] ?? null,
    start,
    exit,
    next,
    prev,
    togglePlay,
    notifyConfirmed,
  };
}

export function WalkthroughPanel({ wt }: { wt: WalkthroughApi }) {
  if (!wt.active || !wt.step) return null;
  const isLast = wt.stepIndex >= wt.stepCount - 1;
  return (
    <div className="walkthrough-panel" role="region" aria-label="Демонстрационный сценарий">
      <div className="walkthrough-head">
        <Badge demo>DEMO</Badge>
        <span className="eyebrow">Infrastructure Inspection Walkthrough</span>
        <span className="num faint">
          {wt.stepIndex + 1}/{wt.stepCount}
        </span>
        <Button variant="ghost" size="sm" onClick={wt.exit} aria-label="Выйти из сценария">
          <IconClose className="icon-sm" />
        </Button>
      </div>
      <div className="walkthrough-progress" aria-hidden>
        <i style={{ width: `${((wt.stepIndex + 1) / wt.stepCount) * 100}%` }} />
      </div>
      <h3 className="walkthrough-title">{wt.step.title}</h3>
      <p className="small muted">{wt.step.text}</p>
      <div className="walkthrough-controls">
        <Button size="sm" variant="ghost" onClick={wt.prev} disabled={wt.stepIndex === 0} aria-label="Предыдущий шаг">
          <IconChevronLeft className="icon-sm" />
        </Button>
        <Button size="sm" onClick={isLast && !wt.playing ? wt.start : wt.togglePlay} disabled={!!wt.step.waitForUser && !wt.playing && !isLast} aria-label={wt.playing ? 'Пауза' : 'Продолжить'}>
          {wt.playing ? 'Пауза' : isLast ? 'Заново' : 'Продолжить'}
        </Button>
        <Button size="sm" variant="ghost" onClick={wt.next} disabled={isLast} aria-label="Следующий шаг">
          <IconChevronRight className="icon-sm" />
        </Button>
        {wt.step.waitForUser && <span className="faint small">Ожидание действия оператора…</span>}
        {isLast && !wt.playing && <span className="faint small">Сценарий завершён</span>}
      </div>
    </div>
  );
}
