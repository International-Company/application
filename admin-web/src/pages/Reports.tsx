import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Reports } from '../api/types'
import { Empty, ErrorNote, PageTitle } from '../components/ui'
import { useLang } from '../state/providers'

export default function ReportsPage() {
  const { t } = useLang()
  const [data, setData] = useState<Reports | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get<Reports>('/admin/reports')
      .then(setData)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : t('err.generic')))
  }, [t])

  if (!data) {
    return (
      <div>
        <PageTitle title={t('nav.reports')} />
        <ErrorNote message={error} />
        {!error && <Empty text={t('common.loading')} />}
      </div>
    )
  }

  const balanced = data.unbalanced_transactions.length === 0

  return (
    <div className="space-y-8">
      <PageTitle title={t('nav.reports')} />

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <div className="text-xs text-muted">{t('rep.fees')}</div>
          <div className="mt-1 text-2xl font-bold tabular">{data.fees_collected_egp}</div>
        </div>
        <div className="card">
          <div className="text-xs text-muted">{t('rep.outstanding')}</div>
          <div className="mt-1 text-2xl font-bold tabular">
            {data.outstanding_creator_balances_egp}
          </div>
        </div>
        <div className={`card ${balanced ? '' : 'border-red-300 bg-red-50'}`}>
          <div className="text-xs text-muted">{t('rep.unbalanced')}</div>
          <div className={`mt-1 text-2xl font-bold ${balanced ? 'text-emerald-700' : 'text-red-700'}`}>
            {balanced ? '✓' : data.unbalanced_transactions.length}
          </div>
          <div className="mt-1 text-xs text-muted">{balanced ? t('rep.balanced') : ''}</div>
        </div>
      </div>

      <section>
        <h2 className="mb-3 font-bold">{t('rep.ledger')}</h2>
        <div className="overflow-x-auto rounded border border-line">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr>
                <th className="th">{t('rep.type')}</th>
                <th className="th">{t('rep.debit')}</th>
                <th className="th">{t('rep.credit')}</th>
                <th className="th">{t('rep.balance')}</th>
              </tr>
            </thead>
            <tbody>
              {data.ledger.map((row) => (
                <tr key={`${row.type}-${row.currency}`}>
                  <td className="td">{row.type}</td>
                  <td className="td tabular">{row.debit}</td>
                  <td className="td tabular">{row.credit}</td>
                  <td className="td tabular font-semibold">{row.balance}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.ledger.length === 0 && <Empty text={t('common.empty')} />}
        </div>
      </section>

      <section>
        <h2 className="mb-3 font-bold">{t('rep.daily')}</h2>
        <div className="overflow-x-auto rounded border border-line">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr>
                <th className="th">{t('rep.date')}</th>
                <th className="th">{t('rep.count')}</th>
                <th className="th">{t('wd.egp')}</th>
              </tr>
            </thead>
            <tbody>
              {data.daily_arrivals.map((row) => (
                <tr key={row.date}>
                  <td className="td font-mono">{row.date}</td>
                  <td className="td tabular">{row.count}</td>
                  <td className="td tabular">{row.total_egp}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.daily_arrivals.length === 0 && <Empty text={t('common.empty')} />}
        </div>
      </section>
    </div>
  )
}
