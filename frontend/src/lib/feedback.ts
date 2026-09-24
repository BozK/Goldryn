// Shared vocabulary for the FeedbackToast: what a toast looks like, what each
// save failure says, and the `mutate` wrapper every POST/PATCH/DELETE goes through.

import { ApiError } from '../api/client'

export type ToastTone = 'success' | 'error'

export interface ToastMessage {
  id: number
  tone: ToastTone
  text: string
}

export const SAVED_TEXT = 'Saved'

/** Status-code -> toast copy, per FRONTEND_DESIGN.md. Status 0 is "server unreachable". */
export function saveErrorText(status: number): string {
  if (status === 400 || status === 422) return 'Error Saving — Invalid data'
  if (status === 401 || status === 403) return 'Error Saving — Session Expired, Please Log In'
  return 'Error Saving — Try Again'
}

export function isAuthFailure(status: number): boolean {
  return status === 401 || status === 403
}

/**
 * Runs one mutation and reports it through the toast. Resolves to the call's
 * result on success and `undefined` on failure (the failure is already toasted,
 * so callers only need to decide what to keep).
 */
export type Mutate = <T>(call: () => Promise<T>) => Promise<T | undefined>

/**
 * A client-side validation failure, routed through `mutate` so it gets the same
 * "Invalid data" toast as a backend 400 without a separate inline error.
 */
export function rejectInvalid(reason: string): Promise<never> {
  return Promise.reject(new ApiError(400, reason))
}
