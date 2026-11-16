import { getSession, newIdempotencyKey, ApiError } from './client';
import type { UploadCreate } from './types';

/* Загрузка с реальным прогрессом (XHR upload progress events).
   fetch не даёт upload-progress, поэтому multipart идёт через XHR. */
export function uploadWithProgress(
  file: File,
  routeId: string | undefined,
  onProgress: (ratio: number) => void,
): Promise<UploadCreate> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/uploads');
    const session = getSession();
    if (session) xhr.setRequestHeader('Authorization', `Bearer ${session.token}`);
    xhr.setRequestHeader('Idempotency-Key', newIdempotencyKey());
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body as UploadCreate);
        } else {
          const err = body?.error;
          reject(
            new ApiError(
              err?.code ?? 'internal_error',
              err?.message ?? `Ошибка загрузки (${xhr.status})`,
              xhr.status,
              err?.details ?? [],
              err?.request_id ?? null,
            ),
          );
        }
      } catch {
        reject(new ApiError('internal_error', 'Некорректный ответ сервера', xhr.status));
      }
    };
    xhr.onerror = () => reject(new ApiError('network_error', 'Не удалось связаться с сервером.', 0));
    xhr.ontimeout = () => reject(new ApiError('network_error', 'Таймаут загрузки.', 0));
    const form = new FormData();
    form.append('file', file);
    if (routeId) form.append('route_id', routeId);
    xhr.send(form);
  });
}