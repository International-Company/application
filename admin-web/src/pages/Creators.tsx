import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Creator } from '../api/types'
import { Empty, ErrorNote, PageTitle } from '../components/ui'
import { useLang } from '../state/providers'

export default function CreatorsPage() {
  const { t } = useLang()
  const [creators, setCreators] = useState<Creator[] | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    const params = new URLSearchParams()
    if (query) params.set('q', query)
    api
      .get<Creator[]>(`/admin/creators?${params.toString()}`)
      .then((list) => {
        setCreators(list)
        setError('')
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : t('err.generic')))
  }, [query, t])

  useEffect(() => {
    const timer = window.setTimeout(load, 250)
    return () => window.clearTimeout(timer)
  }, [load])

  return (
    <div>
      <PageTitle
        title={t('nav.creators')}
        extra={
          <input
            className="field w-64"
            placeholder={t('common.search')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        }
      />
      <ErrorNote message={error} />

      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr>
              <th className="th">{t('cr.name')}</th>
              <th className="th">{t('cr.phone')}</th>
              <th className="th">{t('cr.tiktok')}</th>
              <th className="th">{t('wd.account')}</th>
              <th className="th">{t('cr.setup')}</th>
              <th className="th">{t('cr.balance')}</th>
              <th className="th">{t('cr.requests')}</th>
              <th className="th">{t('wd.status')}</th>
            </tr>
          </thead>
          <tbody>
            {(creators ?? []).map((creator) => (
              <tr key={creator.id} className="hover:bg-gray-50">
                <td className="td">{creator.display_name || '—'}</td>
                <td className="td font-mono">{creator.phone || '—'}</td>
                <td className="td">{creator.tiktok_name || '—'}</td>
                <td className="td">{creator.receiving_account || '—'}</td>
                <td className="td">
                  <span className={creator.setup_completed ? 'text-emerald-700' : 'text-muted'}>
                    {t(creator.setup_completed ? 'cr.ready' : 'cr.notReady')}
                  </span>
                </td>
                <td className="td tabular">{creator.balance_egp}</td>
                <td className="td tabular">{creator.withdrawals_count}</td>
                <td className="td">{creator.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {creators?.length === 0 && <Empty text={t('common.empty')} />}
        {creators === null && <Empty text={t('common.loading')} />}
      </div>
    </div>
  )
}
