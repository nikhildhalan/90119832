import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class CustomerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    fullName: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=3, max_length=150)
    phone: str
    dateOfBirth: date
    pan: str

    @field_validator('fullName')
    @classmethod
    def name_shape(cls, value: str) -> str:
        if not (3 <= len(value) <= 100) or any(not (character.isalpha() or character in " .'") for character in value):
            raise ValueError('must contain only letters, spaces, periods and apostrophes')
        return value

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.lower()
        if len(value) > 150 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError('must be a valid email address')
        return value

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not re.fullmatch(r'[6-9][0-9]{9}', value):
            raise ValueError('must be a 10-digit Indian mobile number beginning 6-9')
        return value

    @field_validator('pan')
    @classmethod
    def normalize_pan(cls, value: str) -> str:
        value = value.upper()
        if not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', value):
            raise ValueError('must match AAAAA9999A')
        return value

class AccountOpenRequest(BaseModel):
    customer: CustomerInput
    accountType: str
    initialDeposit: Decimal

    @field_validator('accountType')
    @classmethod
    def account_type_valid(cls, value: str) -> str:
        value = value.upper()
        if value not in {'SAVINGS', 'CURRENT'}:
            raise ValueError('must be SAVINGS or CURRENT')
        return value

    @field_validator('initialDeposit', mode='before')
    @classmethod
    def deposit_is_decimal_string(cls, value):
        if not isinstance(value, str):
            raise ValueError('amount must be a decimal string')
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError('must be a valid decimal amount') from exc
        if not amount.is_finite() or amount.as_tuple().exponent < -2:
            raise ValueError('must have at most two decimal places')
        return amount

    @field_validator('initialDeposit')
    @classmethod
    def deposit_range(cls, value: Decimal) -> Decimal:
        if value > Decimal('1000000.00'):
            raise ValueError('must not exceed 1000000.00')
        return value

class TransferRequest(BaseModel):
    fromAccountNumber: str
    toAccountNumber: str
    amount: Decimal
    remarks: str | None = Field(default=None, max_length=100)

    @field_validator('fromAccountNumber', 'toAccountNumber')
    @classmethod
    def account_no_valid(cls, value: str) -> str:
        if not re.fullmatch(r'\d{12}', value):
            raise ValueError('must be a 12-digit account number')
        return value

    @field_validator('amount', mode='before')
    @classmethod
    def amount_string(cls, value):
        if not isinstance(value, str):
            raise ValueError('amount must be a decimal string')
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError('must be a valid decimal amount') from exc
        if not result.is_finite() or result.as_tuple().exponent < -2:
            raise ValueError('must have at most two decimal places')
        return result

    @field_validator('remarks')
    @classmethod
    def remarks_strip(cls, value):
        return value.strip() if value else value
