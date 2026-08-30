/** حالة التطبيق: اللغة والاتجاه، والمستخدم الحالي. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import type { AdminUser } from '../api/types'
import { LANG_STORAGE_KEY, translate } from '../i18n'
import type { Lang } from '../i18n'

interface LangContextValue {
  lang: Lang
  dir: 'rtl' | 'ltr'
  t: (key: string) => string
  toggle: () => void
}

const LangContext = createContext<LangContextValue | null>(null)

function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const stored = localStorage.getItem(LANG_STORAGE_KEY)
    return stored === 'en' ? 'en' : 'ar'
  })

  const dir: 'rtl' | 'ltr' = lang === 'ar' ? 'rtl' : 'ltr'

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
    localStorage.setItem(LANG_STORAGE_KEY, lang)
  }, [lang, dir])

  const value = useMemo<LangContextValue>(
    () => ({
      lang,
      dir,
      t: (key: string) => translate(lang, key),
      toggle: () => setLang((current) => (current === 'ar' ? 'en' : 'ar')),
    }),
    [lang, dir],
  )

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>
}

export function useLang(): LangContextValue {
  const value = useContext(LangContext)
  if (!value) throw new Error('useLang خارج المزوّد')
  return value
}

interface AuthContextValue {
  user: AdminUser | null
  loading: boolean
  login: (email: string, password: string, totpCode?: string) => Promise<'ok' | 'totp_required'>
  logout: () => Promise<void>
  /** هل يملك المستخدم صلاحية تحريك المال؟ */
  canMoveMoney: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api
      .ensureCsrf()
      .then(() => api.get<AdminUser>('/admin/auth/me'))
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(
    async (email: string, password: string, totpCode?: string) => {
      await api.ensureCsrf()
      try {
        const me = await api.post<AdminUser>('/admin/auth/login', {
          email,
          password,
          totp_code: totpCode ?? '',
        })
        setUser(me)
        return 'ok' as const
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && error.code === 'http_error') {
          // الخادم يرد totp_required بلا كتلة error عند لزوم الرمز الثنائي
          return 'totp_required' as const
        }
        throw error
      }
    },
    [],
  )

  const logout = useCallback(async () => {
    await api.post('/admin/auth/logout')
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login,
      logout,
      canMoveMoney: user?.role === 'superadmin' || user?.role === 'finance',
    }),
    [user, loading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth خارج المزوّد')
  return value
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <LangProvider>
      <AuthProvider>{children}</AuthProvider>
    </LangProvider>
  )
}
