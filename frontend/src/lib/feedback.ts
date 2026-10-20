// Shared vocabulary for the FeedbackToast: what a toast looks like, what each
// save failure says, and the `mutate` wrapper every POST/PATCH/DELETE goes through.

import { ApiError } from '../api/client'
import { MAX_UPLOAD_MB } from './attachments'

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
  if (status === 413) return `Error Saving — File Too Large (max ${MAX_UPLOAD_MB} MB)`
  return 'Error Saving — Try Again'
}

/** Login-screen toast copy. `retryAfter` is in seconds, from a 429's Retry-After header. */
export function loginErrorText(status: number, retryAfter?: number): string {
  if (status === 400 || status === 401) return 'Invalid username or password'
  if (status === 429) {
    if (!retryAfter) return 'Too many attempts — wait a few minutes'
    const minutes = Math.ceil(retryAfter / 60)
    return `Too many attempts — wait ${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
  }
  return 'Try again'
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

/** Same idea for a file over the upload limit: the "File Too Large" toast, without sending it. */
export function rejectTooLarge(filename: string): Promise<never> {
  return Promise.reject(new ApiError(413, `${filename} is over ${MAX_UPLOAD_MB} MB`))
}
