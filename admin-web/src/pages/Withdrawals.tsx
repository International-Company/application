import { Fragment, useCallback, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Withdrawal, WithdrawalList, WithdrawalStatus } from '../api/types'
import {
  Empty,
  ErrorNote,
  Field,
  Modal,
  PageTitle,
  StatusBadge,
  elapsedLabel,
  formatDate,
  usePolling,
} from '../components/ui'
import { useAuth, useLang } from '../state/providers'

const STATUSES: WithdrawalStatus[] = [
  'initiated',
  'tiktok_processing',
  'tiktok_sent',
  'received_eg',
  'approved',
  'paid',
  'not_received',
  'tiktok_rejected',
  'cancelled',
]

type ActionKind = 'mark_received' | 'approve' | 'cancel'

export default function WithdrawalsPage({ conflictsOnly = false }: { conflictsOnly?: boolean }) {
  const { t, lang } = useLang()
  const { canMoveMoney } = useAuth()
  const [data, setData] = useState<WithdrawalList | null>(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [action, setAction] = useState<{ row: Withdrawal; kind: ActionKind } | null>(null)

  const load = useCallback(() => {
    const params = new URLSearchParams()
    if (conflictsOnly) params.set('conflicts', '1')
    if (status) params.set('status', status)
    if (from) params.set('from', from)
    if (to) params.set('to', to)
    api
      .get<WithdrawalList>(`/admin/withdrawals?${params.toString()}`)
      .then((result) => {
        setData(result)
        setError('')
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : t('err.generic')))
  }, [conflictsOnly, status, from, to, t])

  usePolling(load, 10_000)

  const rows = data?.results ?? []

  return (
    <div>
      <PageTitle
        title={t(conflictsOnly ? 'nav.conflicts' : 'nav.withdrawals')}
        extra={
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{t('common.live')}</span>
            <button className="btn" onClick={load}>
              {t('common.refresh')}
            </button>
          </div>
        }
      />

      <ErrorNote message={error} />

      {!conflictsOnly && (
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="label">{t('wd.status')}</span>
            <select
              className="field min-w-44"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">{t('common.all')}</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {t(`status.${value}`)} ({data?.counts?.[value] ?? 0})
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="label">{t('common.from')}</span>
            <input
              type="date"
              className="field"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="label">{t('common.to')}</span>
            <input
              type="date"
              className="field"
              value={to}
              onChange={(event) => setTo(event.target.value)}
            />
          </label>
        </div>
      )}

      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
            <tr>
              <th className="th">{t('wd.code')}</th>
              <th className="th">{t('wd.creator')}</th>
              <th className="th">{t('wd.account')}</th>
              <th className="th">{t('wd.usd')}</th>
              <th className="th">{t('wd.egp')}</th>
              <th className="th">{t('wd.status')}</th>
              <th className="th">{t('wd.elapsed')}</th>
              <th className="th">{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <Fragment key={row.code}>
                <tr className="hover:bg-gray-50">
                  <td className="td font-mono">
                    <button
                      className="underline-offset-2 hover:underline"
                      onClick={() => setExpanded(expanded === row.code ? null : row.code)}
                    >
                      {row.code}
                    </button>
                  </td>
                  <td className="td">
                    <div>{row.creator_name || '—'}</div>
                    <div className="text-xs text-muted">{row.creator_phone}</div>
                  </td>
                  <td className="td">
                    <div>{row.receiving_label || '—'}</div>
                    <div className="text-xs text-muted">{row.owner_whatsapp}</div>
                  </td>
                  <td className="td tabular">{row.amount_usd ?? '—'}</td>
                  <td className="td tabular">{row.amount_egp ?? '—'}</td>
                  <td className="td">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="td tabular">{elapsedLabel(row.elapsed_seconds, lang)}</td>
                  <td className="td">
                    <div className="flex flex-wrap gap-1">
                      {canMoveMoney && row.status === 'tiktok_sent' && (
                        <button
                          className="btn"
                          onClick={() => setAction({ row, kind: 'mark_received' })}
                        >
                          {t('wd.markReceived')}
                        </button>
                      )}
                      {canMoveMoney && row.status === 'not_received' && (
                        <button
                          className="btn"
                          onClick={() => setAction({ row, kind: 'mark_received' })}
                        >
                          {t('wd.markReceived')}
                        </button>
                      )}
                      {canMoveMoney && row.status === 'received_eg' && (
                        <button
                          className="btn btn-primary"
                          onClick={() => setAction({ row, kind: 'approve' })}
                        >
                          {t('wd.approve')}
                        </button>
                      )}
                      {['initiated', 'tiktok_processing'].includes(row.status) && (
                        <button className="btn" onClick={() => setAction({ row, kind: 'cancel' })}>
                          {t('wd.cancelRequest')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                {expanded === row.code && (
                  <tr>
                    <td className="td bg-gray-50" colSpan={8}>
                      <div className="mb-2 text-xs font-semibold text-muted">
                        {t('wd.evidence')}
                      </div>
                      {row.evidence.length === 0 ? (
                        <div className="text-sm text-muted">{t('wd.noEvidence')}</div>
                      ) : (
                        <ul className="space-y-1 text-sm">
                          {row.evidence.map((item, index) => (
                            <li key={index} className="flex flex-wrap gap-3">
                              <span className="font-mono">{item.source}</span>
                              <span>{item.kind}</span>
                              <span className="tabular">{item.amount ?? '—'}</span>
                              <span className={item.trusted ? 'text-emerald-700' : 'text-red-700'}>
                                {t(item.trusted ? 'wd.trusted' : 'wd.untrusted')}
                              </span>
                              <span className="text-muted">{formatDate(item.at, lang)}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <Empty text={data ? t('common.empty') : t('common.loading')} />}
      </div>

      {action && (
        <ActionModal
          row={action.row}
          kind={action.kind}
          onClose={() => setAction(null)}
          onDone={() => {
            setAction(null)
            load()
          }}
        />
      )}
    </div>
  )
}

function ActionModal({
  row,
  kind,
  onClose,
  onDone,
}: {
  row: Withdrawal
  kind: ActionKind
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useLang()
  const [amount, setAmount] = useState(row.amount_egp ?? '')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const title =
    kind === 'mark_received'
      ? t('wd.markReceived')
      : kind === 'approve'
        ? t('wd.approve')
        : t('wd.cancelRequest')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.patch(`/admin/withdrawals/${row.code}`, {
        action: kind,
        ...(kind === 'mark_received' ? { amount_egp: amount } : {}),
        ...(kind === 'cancel' ? { reason } : {}),
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={`${title} — ${row.code}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <ErrorNote message={error} />
        {kind === 'mark_received' && (
          <Field label={t('wd.amountReceived')} value={amount} onChange={setAmount} required />
        )}
        {kind === 'cancel' && (
          <Field label={t('wd.reason')} value={reason} onChange={setReason} />
        )}
        <div className="flex gap-2">
          <button className="btn btn-primary" disabled={busy}>
            {t('common.confirm')}
          </button>
          <button type="button" className="btn" onClick={onClose}>
            {t('common.cancel')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
