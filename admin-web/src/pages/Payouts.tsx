import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { PayoutMethod, PayoutQueue, Withdrawal } from '../api/types'
import { Empty, ErrorNote, Field, Modal, PageTitle, Select, formatDate } from '../components/ui'
import { useAuth, useLang } from '../state/providers'

export default function PayoutsPage() {
  const { t, lang } = useLang()
  const { canMoveMoney } = useAuth()
  const [queue, setQueue] = useState<PayoutQueue | null>(null)
  const [error, setError] = useState('')
  const [paying, setPaying] = useState<Withdrawal | null>(null)

  const load = useCallback(() => {
    api
      .get<PayoutQueue>('/admin/payouts')
      .then((result) => {
        setQueue(result)
        setError('')
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : t('err.generic')))
  }, [t])

  useEffect(load, [load])

  const rows = queue?.results ?? []

  return (
    <div>
      <PageTitle title={t('nav.payouts')} />
      <ErrorNote message={error} />

      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr>
              <th className="th">{t('wd.code')}</th>
              <th className="th">{t('wd.creator')}</th>
              <th className="th">{t('wd.egp')}</th>
              <th className="th">{t('wd.fee')}</th>
              <th className="th">{t('wd.net')}</th>
              <th className="th">{t('set.activeFrom')}</th>
              <th className="th">{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const gross = Number(row.amount_egp ?? 0)
              const fee = Number(row.fee_egp ?? 0)
              return (
                <tr key={row.code} className="hover:bg-gray-50">
                  <td className="td font-mono">{row.code}</td>
                  <td className="td">
                    <div>{row.creator_name || '—'}</div>
                    <div className="text-xs text-muted">{row.creator_phone}</div>
                  </td>
                  <td className="td tabular">{row.amount_egp ?? '—'}</td>
                  <td className="td tabular">{row.fee_egp}</td>
                  <td className="td tabular font-semibold">{(gross - fee).toFixed(4)}</td>
                  <td className="td text-xs text-muted">{formatDate(row.approved_at, lang)}</td>
                  <td className="td">
                    {canMoveMoney && (
                      <button className="btn btn-primary" onClick={() => setPaying(row)}>
                        {t('pay.execute')}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <Empty text={queue ? t('pay.queueEmpty') : t('common.loading')} />
        )}
      </div>

      {paying && (
        <ExecuteModal
          row={paying}
          methods={queue?.methods ?? []}
          onClose={() => setPaying(null)}
          onDone={() => {
            setPaying(null)
            load()
          }}
        />
      )}
    </div>
  )
}

function ExecuteModal({
  row,
  methods,
  onClose,
  onDone,
}: {
  row: Withdrawal
  methods: PayoutMethod[]
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useLang()
  const [methodId, setMethodId] = useState(methods[0]?.id ?? '')
  const [reference, setReference] = useState('')
  const [destination, setDestination] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post(`/admin/payouts/${row.code}/execute`, {
        method_id: methodId,
        reference,
        destination,
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={`${t('pay.execute')} — ${row.code}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <ErrorNote message={error} />
        <Select
          label={t('pay.method')}
          value={methodId}
          onChange={setMethodId}
          options={methods.map((method) => ({ value: method.id, label: method.name }))}
        />
        <Field
          label={t('pay.reference')}
          value={reference}
          onChange={setReference}
          required
          autoFocus
        />
        <Field label={t('pay.destination')} value={destination} onChange={setDestination} />
        <button className="btn btn-primary w-full" disabled={busy || !reference || !methodId}>
          {t('common.confirm')}
        </button>
      </form>
    </Modal>
  )
}
