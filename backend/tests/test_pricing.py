"""الرسوم وسعر الصرف."""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def test_percentage_fee(fee_schedule):
    assert fee_schedule.compute_fee(Decimal("4850")) == Decimal("242.5000")


def test_fee_respects_minimum(fee_schedule):
    fee_schedule.min_fee = Decimal("50")
    assert fee_schedule.compute_fee(Decimal("100")) == Decimal("50.0000")


def test_fee_respects_maximum(fee_schedule):
    fee_schedule.max_fee = Decimal("100")
    assert fee_schedule.compute_fee(Decimal("10000")) == Decimal("100.0000")


def test_fx_conversion(fx_rate):
    assert fx_rate.convert(Decimal("100")) == Decimal("4850.0000")
