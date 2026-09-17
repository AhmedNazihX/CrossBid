import type { components } from './api'
import { apiRequest } from './api-client'

export type ProviderKeyResponse = components['schemas']['ProviderKeyResponse']
export type Provider = components['schemas']['Provider']

/**
 * The status the API answers when a company has no usable provider key (S5.4).
 *
 * 402, not 403: the caller is who they say they are and nothing conflicts — what is missing
 * is the means to pay for the work. Every screen that starts work a key pays for reads this
 * one status and sends the bidder to their company profile.
 */
export const NO_PROVIDER_KEY_STATUS = 402

/** The saved key's hint and dates, or `null` when none is saved. */
export async function loadProviderKey(
  signal?: AbortSignal
): Promise<ProviderKeyResponse | null> {
  try {
    return await apiRequest('get', '/companies/me/provider-key', { signal })
  } catch (error) {
    // 404 is the ordinary answer for a company that has not saved one yet, not a failure.
    if (error instanceof Error && 'status' in error && error.status === 404) {
      return null
    }
    throw error
  }
}

/**
 * Sends the key once. The API verifies it with the provider before storing it, so a refusal
 * here means the key itself is wrong — which is worth hearing while the bidder is still
 * looking at the field they pasted it into.
 */
export function saveProviderKey(providerKey: string): Promise<ProviderKeyResponse> {
  return apiRequest('put', '/companies/me/provider-key', {
    body: { provider: 'openrouter', provider_key: providerKey },
  })
}

/** Removes the key. The company cannot upload or run a bid until another one is saved. */
export function deleteProviderKey(): Promise<void> {
  return apiRequest('delete', '/companies/me/provider-key', {})
}
