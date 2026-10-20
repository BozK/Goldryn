import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { isAuthFailure, loginErrorText, rejectInvalid, saveErrorText } from './feedback'

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

describe('saveErrorText', () => {
  it('calls out invalid data for 400 and 422', () => {
    expect(saveErrorText(400)).toMatch(/invalid data/i)
    expect(saveErrorText(422)).toMatch(/invalid data/i)
  })

  it('calls out an expired session for 401 and 403', () => {
    expect(saveErrorText(401)).toMatch(/session expired/i)
    expect(saveErrorText(403)).toMatch(/session expired/i)
  })

  it('names the upload limit for 413', () => {
    expect(saveErrorText(413)).toMatch(/too large \(max 50 MB\)/i)
  })

  it('falls back to a generic retry message otherwise', () => {
    expect(saveErrorText(500)).toMatch(/try again/i)
    expect(saveErrorText(0)).toMatch(/try again/i)
  })
})

describe('loginErrorText', () => {
  it('calls out bad credentials for 400 and 401', () => {
    expect(loginErrorText(400)).toBe('Invalid username or password')
    expect(loginErrorText(401)).toBe('Invalid username or password')
  })

  it('rounds the Retry-After wait up to whole minutes for 429', () => {
    expect(loginErrorText(429, 1)).toMatch(/wait 1 minute$/)
    expect(loginErrorText(429, 60)).toMatch(/wait 1 minute$/)
    expect(loginErrorText(429, 61)).toMatch(/wait 2 minutes$/)
    expect(loginErrorText(429, 900)).toMatch(/wait 15 minutes$/)
  })

  it('still explains a 429 without Retry-After', () => {
    expect(loginErrorText(429)).toMatch(/too many attempts/i)
  })

  it('falls back to a generic retry message otherwise', () => {
    expect(loginErrorText(500)).toBe('Try again')
    expect(loginErrorText(0)).toBe('Try again')
  })
})

describe('rejectInvalid', () => {
  it('rejects with a 400 ApiError carrying the given reason', async () => {
    await expect(rejectInvalid('Cadence must be a whole number of days')).rejects.toMatchObject({
      status: 400,
      message: 'Cadence must be a whole number of days',
    })
  })

  it('rejects with an instance of ApiError', async () => {
    await expect(rejectInvalid('bad input')).rejects.toBeInstanceOf(ApiError)
  })
})
