import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth, useLang } from './state/providers'
import LoginPage from './pages/Login'
import WithdrawalsPage from './pages/Withdrawals'
import AccountsPage from './pages/Accounts'
import CreatorsPage from './pages/Creators'
import PayoutsPage from './pages/Payouts'
import SettingsPage from './pages/Settings'
import ReportsPage from './pages/Reports'

const NAV = [
  { to: '/withdrawals', key: 'nav.withdrawals' },
  { to: '/conflicts', key: 'nav.conflicts' },
  { to: '/accounts', key: 'nav.accounts' },
  { to: '/creators', key: 'nav.creators' },
  { to: '/payouts', key: 'nav.payouts' },
  { to: '/settings', key: 'nav.settings' },
  { to: '/reports', key: 'nav.reports' },
]

function Shell() {
  const { t, lang, toggle } = useLang()
  const { user, logout } = useAuth()

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-e border-line bg-white">
        <div className="border-b border-line px-4 py-4">
          <div className="font-bold">{t('app.title')}</div>
        </div>
        <nav className="p-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block rounded px-3 py-2 text-sm ${
                  isActive ? 'bg-ink text-white' : 'text-ink hover:bg-gray-50'
                }`
              }
            >
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line px-6 py-3">
          <div className="text-sm text-muted">
            {user?.full_name || user?.email}
            {user ? ` — ${t(`role.${user.role}`)}` : ''}
          </div>
          <div className="flex items-center gap-2">
            <button className="btn" onClick={toggle}>
              {lang === 'ar' ? 'English' : 'العربية'}
            </button>
            <button className="btn" onClick={() => void logout()}>
              {t('common.logout')}
            </button>
          </div>
        </header>

        <main className="min-w-0 flex-1 p-6">
          <Routes>
            <Route path="/withdrawals" element={<WithdrawalsPage />} />
            <Route path="/conflicts" element={<WithdrawalsPage conflictsOnly />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/creators" element={<CreatorsPage />} />
            <Route path="/payouts" element={<PayoutsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="*" element={<Navigate to="/withdrawals" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const { user, loading } = useAuth()
  const { t } = useLang()

  if (loading) {
    return <div className="p-10 text-sm text-muted">{t('common.loading')}</div>
  }
  return user ? <Shell /> : <LoginPage />
}
