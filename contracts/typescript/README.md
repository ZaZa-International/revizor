# TypeScript-клиент API (сгенерированные типы)

`schema.d.ts` — автоматически сгенерированные типы из OpenAPI-контракта
`contracts/openapi/openapi.json` (инструмент [openapi-typescript](https://openapi-ts.dev)).
Файл **не редактируется вручную**: он перезаписывается генератором.

## Регенерация

```bash
# из корня репозитория (нужен Node.js >= 18 и npx)
make ts-client
# или напрямую
bash scripts/generate_ts_client.sh
```

После любого изменения API-контракта лид перегенерирует `openapi.json`
(`make openapi`), затем `make ts-client`. Проверки целостности контракта:

```bash
make openapi-check     # committed openapi.json == live app.openapi()
make breaking-check    # breaking-изменения относительно origin/main (oasdiff)
```

## Использование с openapi-fetch

Рекомендуемый runtime-клиент — [openapi-fetch](https://openapi-ts.dev/openapi-fetch/)
(типобезопасный fetch без кодогенерации):

```bash
npm install openapi-fetch
npm install -D openapi-typescript
```

```typescript
import createClient from "openapi-fetch";
import type { paths } from "./schema"; // contracts/typescript/schema.d.ts

const client = createClient<paths>({
  baseUrl: "http://localhost:8000",
  headers: {
    Authorization: `Bearer ${accessToken}`, // POST /api/v1/auth/login
  },
});

// Типизированный GET /api/v1/assets: query-параметры и ответ проверяются компилятором
const { data, error, response } = await client.GET("/api/v1/assets", {
  params: {
    query: {
      page: 1,
      page_size: 20,
      sort_by: "current_priority", // только whitelist-поля ресурса
      order: "desc",
      priority_band: "HIGH_PRIORITY",
      bbox: "37.55,55.70,37.70,55.80", // min_lon,min_lat,max_lon,max_lat
    },
  },
});

if (error) {
  // единый конверт ошибки: { error: { code, message, details, request_id } }
  console.error(error.error.code, error.error.request_id);
} else {
  // data: { items: AssetResponse[], total, page, page_size, pages }
  for (const asset of data.items) {
    console.log(asset.id, asset.asset_type, asset.current_priority);
  }
}
```

POST с идемпотентностью:

```typescript
const { data: job } = await client.POST("/api/v1/jobs", {
  headers: { "Idempotency-Key": crypto.randomUUID() },
  body: { upload_id: uploadId },
});
```

## Альтернативы

- `openapi-typescript-codegen` / `orval` — полноценный клиентский код:
  `npx orval --input contracts/openapi/openapi.json --output src/api/client.ts`
- Только типы ответов: `components["schemas"]["AssetResponse"]` и т.п.

## Замечания

- Типы отражают **закоммиченный** контракт. Если `make openapi-check` сообщает
  о drift, сначала перегенерируйте `openapi.json`, затем `schema.d.ts`.
- Бинарные ответы (exports/files) в типах представлены как `string` (binary) —
  для скачивания используйте обычный `fetch`/`axios` с `responseType: "blob"`.
- Координаты во всех GeoJSON-ответах — `[longitude, latitude]` (RFC 7946).

Связанные документы: [../../docs/api/overview.md](../../docs/api/overview.md),
[../../docs/integrations/README.md](../../docs/integrations/README.md),
[../../docs/integrations/frontend-contract.md](../../docs/integrations/frontend-contract.md).
