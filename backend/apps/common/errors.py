"""أخطاء المجال — تُترجم لاحقًا إلى استجابات API."""


class DomainError(Exception):
    """خطأ في منطق الأعمال."""


class IllegalStateTransition(DomainError):
    """انتقال حالة غير مسموح به في آلة الحالات."""


class UnbalancedTransaction(DomainError):
    """قيد محاسبي غير متوازن — مجموع المدين لا يساوي مجموع الدائن."""


class AppendOnlyViolation(DomainError):
    """محاولة تعديل أو حذف سجل مُلحَق فقط."""


class DuplicateWithdrawal(DomainError):
    """طلب سحب مكرر."""
