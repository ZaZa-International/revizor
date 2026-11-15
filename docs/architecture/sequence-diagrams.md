# Sequence-диаграммы ключевых сценариев

Диаграммы отражают фактический поток вызовов в коде. Имена участников сокращены;
соответствие реальным модулям дано в подписях и в [component-diagram.md](component-diagram.md).

## 1. Upload (multipart → валидация → checksum-дедуп → S3 → БД)

Код: `api/v1/uploads.py`, `api/v1/idempotency.py`, `services/uploads.py`,
`infrastructure/storage/s3.py`.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as uploads router
    participant ID as idempotent_post
    participant U as UploadService
    participant S as ObjectStorage (S3)
    participant DB as PostgreSQL

    C->>R: POST /uploads (file, route_id, metadata, Idempotency-Key)
    R->>R: rate limit check (Redis)
    R->>ID: handler + key
    ID->>DB: get_cached(key, user, endpoint)
    alt cached response exists
        DB-->>ID: stored status + body
        ID-->>C: replay JSONResponse
    else no cache
        ID->>U: create_upload(stream, filename, content_type, metadata)
        U->>U: validate extension + declared MIME
        U->>U: stream chunks, size limit, SHA-256, magic bytes
        U->>DB: get_by_checksum(sha256)
        alt upload already exists
            DB-->>U: existing Upload
            U-->>ID: UploadResult(created=False)
            ID-->>C: 200 + existing upload
        else new file
            U->>S: upload_file(uploads/{id}/{name})
            S-->>U: ok
            U->>DB: insert Upload + StoredFile(ORIGINAL) + AuditLog
            DB-->>U: committed
            U-->>ID: UploadResult(created=True)
            ID->>DB: save idempotency record
            ID-->>C: 201 + upload + presigned_url
        end
    end
```

## 2. Processing (API → RQ → worker → pipeline → БД)

Код: `api/v1/jobs.py`, `services/jobs.py`, `infrastructure/queue/rq_queue.py`,
`workers/worker.py`, `workers/tasks/processing.py`, `use_cases/processing/pipeline.py`.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as jobs router
    participant J as JobService
    participant Q as RQJobQueue
    participant RD as Redis
    participant W as RQ Worker
    participant P as ProcessingPipeline
    participant DB as PostgreSQL
    participant S as ObjectStorage
    participant ML as MLProvider

    C->>R: POST /jobs (upload_id, route_id, options)
    R->>J: create_job(...)
    J->>DB: insert ProcessingJob(PENDING), transition to QUEUED
    J->>Q: enqueue_processing(job_id)
    Q->>RD: enqueue task by import-path (Retry max 3)
    RD-->>Q: rq_job_id
    Q-->>J: rq_job_id
    J->>DB: save rq_job_id + AuditLog
    J-->>C: 201 JobResponse(QUEUED)

    RD->>W: dequeue process_upload_task(job_id)
    W->>P: run(job_id) in isolated event loop
    P->>DB: load job, assert transition to PROCESSING
    P->>S: download_to_file(original)
    P->>P: probe_frame_count + extract_frames (OpenCV)
    P->>DB: set total_frames
    loop each frame (cancel check every 10)
        P->>DB: skip if frame already PROCESSED/REJECTED/SKIPPED
        P->>P: quality gate, privacy filter
        P->>S: upload frame jpeg
        P->>ML: infer_image(request)
        ML-->>P: detections
        P->>P: normalize, geolocate, dedup, risk
        P->>DB: persist Observation/Asset/Defect/JobFrame (one tx)
        P->>DB: update progress counters
    end
    P->>DB: finalize status (COMPLETED/PARTIALLY_COMPLETED/FAILED/CANCELLED)
    P-->>W: done
```

## 3. Inference (pipeline → MLProvider → валидация контракта → retries)

Код: `use_cases/processing/pipeline.py::_process_frame`,
`infrastructure/ml/http_provider.py`, `schemas/ml.py`, `core/exceptions.py`.

```mermaid
sequenceDiagram
    autonumber
    participant P as ProcessingPipeline
    participant H as HTTPMLProvider
    participant M as External ML service
    participant DB as PostgreSQL

    P->>H: infer_image(MLInferenceRequest schema 1.0)
    loop attempts = 1 + ml_http_retries
        H->>M: POST /v1/infer (image ref + metadata)
        alt timeout / connect error / HTTP 5xx
            M-->>H: retryable failure
            H->>H: exponential backoff + jitter, retry
        else HTTP 4xx
            M-->>H: error response
            H->>H: raise MLContractError / MLInferenceError (no retry)
        else HTTP 2xx
            M-->>H: JSON response
        end
    end
    H->>H: parse + validate against MLInferenceResponse
    H->>H: check request_id match + bbox within image bounds
    alt contract violation
        H-->>P: MLContractError (not retryable)
    else valid
        H-->>P: MLInferenceResponse(detections)
    end
    alt MLProviderError raised
        P->>DB: JobFrame(FAILED, error_code)
        P->>P: continue with next frame
    else success
        P->>DB: persist detections
    end
```

## 4. Deduplication (PostGIS-кандидаты → политика → решение → explanation)

Код: `services/deduplication.py`, `repositories/assets.py::find_candidates`,
`domain/deduplication/policy.py`.

```mermaid
sequenceDiagram
    autonumber
    participant P as ProcessingPipeline
    participant D as DeduplicationService
    participant AR as AssetRepository
    participant DB as PostgreSQL / PostGIS
    participant POL as domain policy (decide)

    P->>D: match(object_type, point, observed_at, job_id, route_id, tracking_id)
    alt point is None (no GPS)
        D->>DB: find prior observation by tracking_id in same job
        DB-->>D: previous observation or none
        D-->>P: MATCHED (score 1.0) or NEW_ASSET
    else point present
        D->>AR: find_candidates(point, radius, asset_type)
        AR->>DB: ST_DWithin + ST_Distance (GiST, ACTIVE, same type, limit 10)
        DB-->>AR: candidates with distance_m
        AR-->>D: list of (Asset, distance)
        loop each candidate
            D->>DB: hours_since_last_observation, same_route, same_tracking_id
            D->>D: build CandidateEvidence
        end
        D->>POL: decide(evidence, object_type, config)
        POL->>POL: weighted score (spatial .55, type .20, temporal .05, context .15, visual .05)
        alt best >= 0.70 and single strong candidate
            POL-->>D: MATCHED(asset_id, score, explanation)
        else two strong candidates within 0.10
            POL-->>D: AMBIGUOUS(None, score, explanation)
        else best >= 0.45
            POL-->>D: POSSIBLE_MATCH(asset_id, score, explanation)
        else below threshold or no candidates
            POL-->>D: NEW_ASSET(None, score, explanation)
        end
        D-->>P: DeduplicationDecision
    end
    P->>DB: store dedup_result/score/explanation on Observation
```

> Ветви `alt/else` взаимоисключающие: политика выбирает ровно один результат.

## 5. Review (оператор → ReviewService → observation/defect/asset/training/history)

Код: `api/v1/reviews.py`, `services/reviews.py`, `domain/reviews/logic.py`,
`services/risk.py`, `services/history.py`.

```mermaid
sequenceDiagram
    autonumber
    participant O as Operator
    participant R as reviews router
    participant RS as ReviewService
    participant L as reviews/logic
    participant DB as PostgreSQL
    participant RK as RiskScoringService
    participant H as AssetHistoryService

    O->>R: POST /reviews (observation_id/defect_id, decision, corrections)
    R->>RS: create_review(...)
    RS->>DB: load observation / defect (primary defect if needed)
    RS->>L: validate_review(decision, correction, has_defect)
    L-->>RS: ok or ValueError -> 422
    RS->>DB: insert Review (append-only) + AuditLog
    alt observation target
        RS->>L: apply_review(originals, decision, correction)
        L-->>RS: EffectiveObservationState
        RS->>DB: update observation.review_status + effective_*
        alt decision CONFIRMED or CORRECTED
            RS->>DB: upsert TrainingExample(image_key, label)
        end
        alt observation has asset
            RS->>RK: assess(effective type/severity, confidence, decision, dedup)
            RK-->>RS: RiskAssessment(priority, band)
            RS->>H: record_change(source=HUMAN_REVIEW)
            H->>DB: insert AssetConditionHistory
            RS->>DB: update asset current_condition/severity + priority
        end
    end
    alt defect target
        RS->>DB: apply decision to defect status/type/severity
    end
    RS-->>O: 201 ReviewResponse
```

## 6. Export (фильтры → строки → CSV/XLSX)

Код: `api/v1/exports.py`, `services/exports.py`, репозитории, `openpyxl`/`csv`.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as exports router
    participant REPO as Repository (filtered_stmt)
    participant DB as PostgreSQL
    participant E as ExportService
    participant AU as AuditRepository

    C->>R: GET /exports/assets?format=csv&bbox=...&filters
    R->>R: parse_bbox + filters
    R->>REPO: filtered_stmt(asset_type, bbox, priority_band, dates, ...)
    REPO->>DB: SELECT with ST_Intersects for bbox (limit 50000)
    DB-->>REPO: rows
    REPO-->>R: statement
    R->>E: asset_rows(stmt)
    E->>E: map ORM to dict rows (lon/lat via Shapely, ISO dates)
    R->>E: render(rows, columns, format, entity, actor)
    alt format csv
        E->>E: csv.DictWriter, utf-8-sig
    else format xlsx
        E->>E: openpyxl Workbook(write_only)
    end
    E->>AU: record EXPORT (format, rows)
    AU->>DB: insert AuditLog
    E-->>R: content, media_type, filename
    R-->>C: 200 attachment (Content-Disposition)
```

## Связанные документы
- [Обзор системы](system-overview.md) · [Поток данных](data-flow.md) ·
  [Диаграмма компонентов](component-diagram.md) · [Доменная модель](domain-model.md)
