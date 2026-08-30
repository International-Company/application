/** أنواع البيانات كما يعيدها الخادم. */

export type WithdrawalStatus =
  | 'initiated'
  | 'tiktok_processing'
  | 'tiktok_sent'
  | 'tiktok_rejected'
  | 'received_eg'
  | 'approved'
  | 'paid'
  | 'not_received'
  | 'cancelled'

export type AdminRole = 'superadmin' | 'finance' | 'support' | 'viewer'

export interface AdminUser {
  id: string
  email: string
  full_name: string
  role: AdminRole
  totp_enabled: boolean
}

export interface Evidence {
  source: string
  kind: string
  amount: string | null
  trusted: boolean
  at: string
}

export interface Withdrawal {
  id: string
  code: string
  status: WithdrawalStatus
  creator: string
  creator_name: string
  creator_phone: string
  receiving_label: string
  owner_whatsapp: string
  amount_usd: string | null
  amount_egp: string | null
  fee_egp: string
  net_amount_egp: string
  fx_rate: string | null
  tiktok_txn_id: string | null
  initiated_at: string
  sent_at: string | null
  received_at: string | null
  approved_at: string | null
  paid_at: string | null
  cancel_reason: string
  elapsed_seconds: number
  evidence: Evidence[]
}

export interface WithdrawalList {
  results: Withdrawal[]
  counts: Partial<Record<WithdrawalStatus, number>>
  server_time: string
}

export interface AccountOwner {
  id: string
  full_name: string
  whatsapp_phone: string
  status: string
  accounts_count: number
}

export interface ReceivingAccount {
  id: string
  owner: string
  owner_name: string
  owner_whatsapp: string
  type: 'ipa' | 'mobile' | 'bank'
  identifier: string
  display_label: string
  bank_name: string
  beneficiary_name: string
  daily_limit_egp: string
  monthly_limit_egp: string
  max_creators: number
  status: 'active' | 'full' | 'paused'
  assigned_count: number
  has_capacity: boolean
}

export interface Creator {
  id: string
  display_name: string
  phone: string
  status: string
  risk_score: number
  tiktok_name: string
  receiving_account: string
  setup_completed: boolean
  balance_egp: string
  withdrawals_count: number
}

export interface PayoutMethod {
  id: string
  name: string
  provider: string
}

export interface PayoutQueue {
  results: Withdrawal[]
  methods: PayoutMethod[]
}

export interface FeeSchedule {
  id: string
  name: string
  percent: string
  fixed_amount: string
  currency: string
  min_fee: string
  max_fee: string | null
  effective_from: string
  effective_to: string | null
  is_active: boolean
}

export interface FxRate {
  id: string
  rate: string
  source: string
  effective_at: string
}

export interface Reports {
  ledger: { type: string; currency: string; debit: string; credit: string; balance: string }[]
  fees_collected_egp: string
  outstanding_creator_balances_egp: string
  daily_arrivals: { date: string; count: number; total_egp: string }[]
  status_counts: Partial<Record<WithdrawalStatus, number>>
  unbalanced_transactions: string[]
}
