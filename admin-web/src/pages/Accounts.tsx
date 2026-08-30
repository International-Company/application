import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { AccountOwner, Creator, ReceivingAccount } from '../api/types'
import { Empty, ErrorNote, Field, Modal, PageTitle, Select } from '../components/ui'
import { useAuth, useLang } from '../state/providers'

export default function AccountsPage() {
  const { t } = useLang()
  const { canMoveMoney } = useAuth()
  const [accounts, setAccounts] = useState<ReceivingAccount[] | null>(null)
  const [owners, setOwners] = useState<AccountOwner[]>([])
  const [error, setError] = useState('')
  const [showOwner, setShowOwner] = useState(false)
  const [showAccount, setShowAccount] = useState(false)
  const [assigning, setAssigning] = useState<ReceivingAccount | null>(null)

  const load = useCallback(() => {
    Promise.all([
      api.get<ReceivingAccount[]>('/admin/receiving-accounts'),
      api.get<AccountOwner[]>('/admin/account-owners'),
    ])
      .then(([accountList, ownerList]) => {
        setAccounts(accountList)
        setOwners(ownerList)
        setError('')
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : t('err.generic')))
  }, [t])

  useEffect(load, [load])

  async function pause(account: ReceivingAccount) {
    try {
      await api.del(`/admin/receiving-accounts/${account.id}`)
      load()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    }
  }

  return (
    <div>
      <PageTitle
        title={t('nav.accounts')}
        extra={
          canMoveMoney && (
            <div className="flex gap-2">
              <button className="btn" onClick={() => setShowOwner(true)}>
                {t('acc.newOwner')}
              </button>
              <button className="btn btn-primary" onClick={() => setShowAccount(true)}>
                {t('acc.newAccount')}
              </button>
            </div>
          )
        }
      />

      <ErrorNote message={error} />

      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr>
              <th className="th">{t('acc.label')}</th>
              <th className="th">{t('acc.identifier')}</th>
              <th className="th">{t('acc.owner')}</th>
              <th className="th">{t('acc.assigned')}</th>
              <th className="th">{t('wd.status')}</th>
              <th className="th">{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {(accounts ?? []).map((account) => (
              <tr key={account.id} className="hover:bg-gray-50">
                <td className="td">{account.display_label || '—'}</td>
                <td className="td font-mono">{account.identifier}</td>
                <td className="td">
                  <div>{account.owner_name}</div>
                  <div className="text-xs text-muted">{account.owner_whatsapp}</div>
                </td>
                <td className="td tabular">
                  {account.assigned_count} / {account.max_creators}
                </td>
                <td className="td">{account.status}</td>
                <td className="td">
                  {canMoveMoney && (
                    <div className="flex gap-1">
                      <button
                        className="btn"
                        disabled={!account.has_capacity}
                        onClick={() => setAssigning(account)}
                      >
                        {t('acc.assign')}
                      </button>
                      {account.status === 'active' && (
                        <button className="btn" onClick={() => void pause(account)}>
                          {t('acc.pause')}
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {accounts?.length === 0 && <Empty text={t('common.empty')} />}
        {accounts === null && <Empty text={t('common.loading')} />}
      </div>

      {showOwner && (
        <OwnerModal
          onClose={() => setShowOwner(false)}
          onDone={() => {
            setShowOwner(false)
            load()
          }}
        />
      )}
      {showAccount && (
        <AccountModal
          owners={owners}
          onClose={() => setShowAccount(false)}
          onDone={() => {
            setShowAccount(false)
            load()
          }}
        />
      )}
      {assigning && (
        <AssignModal
          account={assigning}
          onClose={() => setAssigning(null)}
          onDone={() => {
            setAssigning(null)
            load()
          }}
        />
      )}
    </div>
  )
}

function OwnerModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useLang()
  const [fullName, setFullName] = useState('')
  const [whatsapp, setWhatsapp] = useState('')
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      await api.post('/admin/account-owners', {
        full_name: fullName,
        whatsapp_phone: whatsapp,
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    }
  }

  return (
    <Modal title={t('acc.newOwner')} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <ErrorNote message={error} />
        <Field label={t('acc.fullName')} value={fullName} onChange={setFullName} required autoFocus />
        <Field
          label={t('acc.whatsapp')}
          value={whatsapp}
          onChange={setWhatsapp}
          placeholder="+2010…"
          required
        />
        <button className="btn btn-primary w-full">{t('common.save')}</button>
      </form>
    </Modal>
  )
}

function AccountModal({
  owners,
  onClose,
  onDone,
}: {
  owners: AccountOwner[]
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useLang()
  const [owner, setOwner] = useState(owners[0]?.id ?? '')
  const [type, setType] = useState('ipa')
  const [identifier, setIdentifier] = useState('')
  const [label, setLabel] = useState('')
  const [beneficiary, setBeneficiary] = useState('')
  const [bank, setBank] = useState('')
  const [maxCreators, setMaxCreators] = useState('1')
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      await api.post('/admin/receiving-accounts', {
        owner,
        type,
        identifier,
        display_label: label,
        beneficiary_name: beneficiary,
        bank_name: bank,
        max_creators: Number(maxCreators),
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    }
  }

  return (
    <Modal title={t('acc.newAccount')} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <ErrorNote message={error} />
        <Select
          label={t('acc.owner')}
          value={owner}
          onChange={setOwner}
          options={owners.map((item) => ({ value: item.id, label: item.full_name }))}
        />
        <Select
          label={t('acc.type')}
          value={type}
          onChange={setType}
          options={[
            { value: 'ipa', label: 'InstaPay' },
            { value: 'mobile', label: 'Mobile wallet' },
            { value: 'bank', label: 'Bank' },
          ]}
        />
        <Field label={t('acc.identifier')} value={identifier} onChange={setIdentifier} required />
        <Field label={t('acc.label')} value={label} onChange={setLabel} />
        <Field label={t('acc.beneficiary')} value={beneficiary} onChange={setBeneficiary} />
        <Field label={t('acc.bank')} value={bank} onChange={setBank} />
        <Field
          label={t('acc.capacity')}
          value={maxCreators}
          onChange={setMaxCreators}
          type="number"
        />
        <button className="btn btn-primary w-full">{t('common.save')}</button>
      </form>
    </Modal>
  )
}

function AssignModal({
  account,
  onClose,
  onDone,
}: {
  account: ReceivingAccount
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useLang()
  const [creators, setCreators] = useState<Creator[]>([])
  const [creatorId, setCreatorId] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get<Creator[]>('/admin/creators')
      .then((list) => {
        setCreators(list)
        setCreatorId(list[0]?.id ?? '')
      })
      .catch(() => setError(t('err.generic')))
  }, [t])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      await api.post(`/admin/receiving-accounts/${account.id}/assign`, { creator_id: creatorId })
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('err.generic'))
    }
  }

  return (
    <Modal title={`${t('acc.assign')} — ${account.identifier}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <ErrorNote message={error} />
        <Select
          label={t('wd.creator')}
          value={creatorId}
          onChange={setCreatorId}
          options={creators.map((creator) => ({
            value: creator.id,
            label: `${creator.display_name || creator.phone} — ${creator.phone}`,
          }))}
        />
        <button className="btn btn-primary w-full" disabled={!creatorId}>
          {t('common.confirm')}
        </button>
      </form>
    </Modal>
  )
}
