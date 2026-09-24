import { describe, expect, it } from 'vitest'
import { isAuthFailure } from './feedback'

describe('isAuthFailure', () => {
  it('treats 401 and 403 as auth failures', () => {
    expect(isAuthFailure(401)).toBe(true)
    expect(isAuthFailure(403)).toBe(true)
  })

  it('does not treat other statuses as auth failures', () => {
    expect(isAuthFailure(200)).toBe(false)
    expect(isAuthFailure(400)).toBe(false)
    expect(isAuthFailure(404)).toBe(false)
    expect(isAuthFailure(500)).toBe(false)
    expect(isAuthFailure(0)).toBe(false)
  })
})
