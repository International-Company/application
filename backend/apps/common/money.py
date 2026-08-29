"""أدوات المبالغ — دقة ثابتة وتقريب مصرفي موحّد."""
from decimal import ROUND_HALF_UP, Decimal

MONEY_PLACES = Decimal("0.0001")
DISPLAY_PLACES = Decimal("0.01")


def quantize(amount: Decimal) -> Decimal:
    """تقريب إلى دقة التخزين (4 خانات)."""
    return Decimal(amount).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def to_display(amount: Decimal) -> Decimal:
    """تقريب إلى خانتين للعرض."""
    return Decimal(amount).quantize(DISPLAY_PLACES, rounding=ROUND_HALF_UP)
