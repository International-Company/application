/** مكوّنات مشتركة: بلا زخرفة، أبيض، وتباين عالٍ. */
import type { ReactNode } from 'react'
import { useEffect, useRef } from 'react'
import { useLang } from '../state/providers'
import type { WithdrawalStatus } from '../api/types'

export function PageTitle({ title, extra }: { title: string; extra?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
      <h1 className="text-xl font-bold">{title}</h1>
      {extra}
    </div>
  )
}

export function Field({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  required,
  autoFocus,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  placeholder?: string
  required?: boolean
  autoFocus?: boolean
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input
        className="field"
        type={type}
        value={value}
        placeholder={placeholder}
        required={required}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <select className="field" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

/** ألوان الحالة دلالية فقط: لا زخرفة ولا تدرجات. */
const STATUS_STYLE: Record<WithdrawalStatus, string> = {
  initiated: 'bg-gray-100 text-gray-800',
  tiktok_processing: 'bg-gray-100 text-gray-800',
  tiktok_sent: 'bg-amber-50 text-amber-800 border-amber-200',
  received_eg: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  paid: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  tiktok_rejected: 'bg-red-50 text-red-800 border-red-200',
  not_received: 'bg-red-50 text-red-800 border-red-200',
  cancelled: 'bg-gray-100 text-gray-500',
}

export function StatusBadge({ status }: { status: WithdrawalStatus }) {
  const { t } = useLang()
  return (
    <span
      className={`inline-block whitespace-nowrap rounded border border-transparent px-2 py-0.5 text-xs ${STATUS_STYLE[status]}`}
    >
      {t(`status.${status}`)}
    </span>
  )
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const { t } = useLang()
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4 pt-24">
      <div className="w-full max-w-md rounded border border-line bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-bold">{title}</h2>
          <button className="text-sm text-muted hover:text-ink" onClick={onClose}>
            {t('common.close')}
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  if (!message) return null
  return (
    <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </div>
  )
}

export function Empty({ text }: { text: string }) {
  return <div className="px-3 py-8 text-center text-sm text-muted">{text}</div>
}

/** صيغة زمنية مختصرة للمدة المنقضية. */
export function elapsedLabel(seconds: number, lang: 'ar' | 'en'): string {
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return lang === 'ar' ? `${minutes} د` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return lang === 'ar' ? `${hours} س` : `${hours}h`
  const days = Math.floor(hours / 24)
  return lang === 'ar' ? `${days} ي` : `${days}d`
}

export function formatDate(value: string | null, lang: 'ar' | 'en'): string {
  if (!value) return '—'
  return new Date(value).toLocaleString(lang === 'ar' ? 'ar-EG' : 'en-GB', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

/** استدعاء دوري: يستدعي الدالة فورًا ثم كل فترة، بلا إعادة جدولة عند كل رسم. */
export function usePolling(callback: () => void, intervalMs: number, enabled = true) {
  const saved = useRef(callback)
  useEffect(() => {
    saved.current = callback
  })
  useEffect(() => {
    saved.current()
    if (!enabled) return
    const id = window.setInterval(() => saved.current(), intervalMs)
    return () => window.clearInterval(id)
  }, [enabled, intervalMs])
}
