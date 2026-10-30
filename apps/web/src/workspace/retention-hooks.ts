import { useRef } from 'react';
import { post, jobKey } from './api';
import { useAction } from './queries';
export function useAIAction<T>(path: string) {
  const prior = useRef({ signature: '', key: jobKey() });
  return useAction<T, Record<string, unknown>>((body) => {
    const signature = JSON.stringify(body);
    if (prior.current.signature !== signature)
      prior.current = { signature, key: jobKey() };
    return post<T>(path, {
      ...body,
      provider_consent: true,
      idempotency_key: prior.current.key,
    });
  });
}
