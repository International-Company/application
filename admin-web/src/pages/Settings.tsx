import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { FeeSchedule, FxRate } from '../api/types'
import { Empty, ErrorNote, Field, PageTitle, Select, formatDate } from '../components/ui'
import { useAuth, useLang } from '../state/providers'

interface FeeResponse {
  results: FeeSchedule[]
  active: FeeSchedule | null
}
interface FxResponse {
  results: FxRate[]
  latest: FxRate | null
}

export default function SettingsPage() {
  const { t, lang } = useLang()
  const { canMoveMoney } = useAuth()
  const [fees, setFees] = useState<FeeResponse | null>(null)
  const [rates, setRates] = useState<FxResponse | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([
      api.get<FeeResponse>('/admin/fee-schedules'),
      api.get<FxResponse>('/admin/fx-rates'),
    ])
      .then(([feeData, rateData]) => {
        setFees(feeData)
        setRates(rateData)
        setError('')
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : t('err.generic')))
  }, [t])

  useEffect(load, [load])

  return (
    <div className="space-y-8">
      <PageTitle title={t('nav.settings')} />
      <ErrorNote message={error} />

      <section>
        <h2 className="mb-3 font-bold">{t('set.fees')}</h2>
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="overflow-x-auto rounded border border-line">
            <table className="w-full min-w-[600px] text-sm">
              <thead>
                <tr>
                  <th className="th">{t('set.name')}</th>
                  <th className="th">{t('set.percent')}</th>
                  <th className="th">{t('set.fixed')}</th>
                  <th className="th">{t('set.activeFrom')}</th>
                  <th className="th">{t('set.active')}</th>
                </tr>
              </thead>
              <tbody>
                {(fees?.results ?? []).map((fee) => (
                  <tr key={fee.id}>
                    <td className="td">{fee.name}</td>
                    <td className="td tabular">{fee.percent}</td>
                    <td className="td tabular">{fee.fixed_amount}</td>
                    <td className="td text-xs text-muted">
                      {formatDate(fee.effective_from, lang)}
                    </td>
                    <td className="td">{fee.is_active ? '✓' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {fees?.results.length === 0 && <Empty text={t('common.empty')} />}
          </div>
          {canMoveMoney && <FeeForm onDone={load} />}
        </div>
      </section>

      <section>
        <h2 className="mb-3 font-bold">{t('set.fx')}</h2>
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="overflow-x-auto rounded border border-line">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr>
                  <th className="th">{t('set.rate')}</th>
                  <th className="th">{t('set.source')}</th>
                  <th className="th">{t('set.activeFrom')}</th>
                </tr>
              </thead>
              <tbody>
                {(rates?.results ?? []).map((rate) => (
                  <tr key={rate.id}>
                    <td className="td tabular">{rate.rate}</td>
                    <td className="td">{rate.source}</td>
                    <td className="td text-xs text-muted">{formatDate(rate.effective_at, lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rates?.results.length === 0 && <Empty text={t('common.empty')} />}
          </div>
          {canMoveMoney && <FxForm onDone={load} />}
        </div>
      </section>
    </div>
  )
}

function FeeForm({ onDone }: { onDone: () => void }) {
  const { t } = useLang()
  const [name, setName] = useState('')
  const [percent, setPercent] = useState('5')
  const [fixed, setFixed] = useState('0')
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await api.post('/admin/fee-schedules', {
        name,
        percent,
        fixed_amount: fixed,
        effective_from: new Date().toISOString(),
        is_active: true,
      })
      setName('')
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-3 self-start">
      <ErrorNote message={error} />
      <Field label={t('set.name')} value={name} onChange={setName} required />
      <Field label={t('set.percent')} value={percent} onChange={setPercent} required />
      <Field label={t('set.fixed')} value={fixed} onChange={setFixed} />
      <button className="btn btn-primary w-full">{t('common.create')}</button>
    </form>
  )
}

function FxForm({ onDone }: { onDone: () => void }) {
  const { t } = useLang()
  const [rate, setRate] = useState('')
  const [source, setSource] = useState('manual')
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await api.post('/admin/fx-rates', {
        rate,
        source,
        effective_at: new Date().toISOString(),
      })
      setRate('')
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-3 self-start">
      <ErrorNote message={error} />
      <Field label={t('set.rate')} value={rate} onChange={setRate} required />
      <Select
        label={t('set.source')}
        value={source}
        onChange={setSource}
        options={[
          { value: 'manual', label: 'Manual' },
          { value: 'tiktok', label: 'TikTok' },
          { value: 'bank', label: 'Bank' },
        ]}
      />
      <button className="btn btn-primary w-full">{t('common.create')}</button>
    </form>
  )
}
