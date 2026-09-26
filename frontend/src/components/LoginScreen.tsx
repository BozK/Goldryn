import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from '../api/client'

interface LoginScreenProps {
  onLoggedIn: () => void
  onError: (text: string) => void
}

export function LoginScreen({ onLoggedIn, onError }: LoginScreenProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setIsSubmitting(true)
    try {
      await api.login({ username, password })
      onLoggedIn()
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0
      onError(status === 400 || status === 401 ? 'Invalid username or password' : 'Try again')
      setIsSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="mb-8 text-center text-5xl font-bold tracking-tight text-gold">Goldryn</h1>
        <input
          type="text"
          placeholder="Username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="field-input"
          disabled={isSubmitting}
          autoFocus
        />
        <input
          type="password"
          placeholder="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="field-input"
          disabled={isSubmitting}
        />
        <button type="submit" className="btn-gold w-full" disabled={isSubmitting || !username || !password}>
          {isSubmitting ? 'Logging in...' : 'Log in'}
        </button>
      </form>
    </main>
  )
}
