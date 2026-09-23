// Shared vocabulary for the FeedbackToast.

export type ToastTone = 'success' | 'error'

export interface ToastMessage {
  id: number
  tone: ToastTone
  text: string
}

export function isAuthFailure(status: number): boolean {
  return status === 401 || status === 403
}
