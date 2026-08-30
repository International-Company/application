import { useState } from 'react'
import { ApiError } from '../api/client'
import { ErrorNote, Field } from '../components/ui'
import { useAuth, useLang } from '../state/providers'

export default function LoginPage() {
  const { t, lang, toggle } = useLang()
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [needsTotp, setNeedsTotp] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const result = await login(email, password, totp)
      if (result === 'totp_required') {
        setNeedsTotp(true)
        setError('')
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-baseline justify-between">
          <h1 className="text-xl font-bold">{t('login.title')}</h1>
          <button className="text-sm text-muted hover:text-ink" onClick={toggle}>
            {lang === 'ar' ? 'English' : 'العربية'}
          </button>
        </div>

        <form onSubmit={submit} className="space-y-4 rounded border border-line p-5">
          <ErrorNote message={error} />
          <Field
            label={t('login.email')}
            value={email}
            onChange={setEmail}
            type="email"
            required
            autoFocus
          />
          <Field
            label={t('login.password')}
            value={password}
            onChange={setPassword}
            type="password"
            required
          />
          {needsTotp && (
            <div>
              <Field label={t('login.totp')} value={totp} onChange={setTotp} />
              <p className="mt-1 text-xs text-muted">{t('login.totpHint')}</p>
            </div>
          )}
          <button className="btn btn-primary w-full" disabled={busy}>
            {busy ? t('common.loading') : t('login.submit')}
          </button>
        </form>
      </div>
    </div>
  )
}
