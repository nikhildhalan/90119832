from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from psycopg import errors
from ..db import pool
from ..errors import ApiProblem
from ..models import AccountOpenRequest


def age_on(born: date, on: date) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def open_account(req: AccountOpenRequest) -> tuple[dict, dict]:
    customer = req.customer
    today = datetime.now(ZoneInfo('Asia/Kolkata')).date()
    if age_on(customer.dateOfBirth, today) < 18:
        raise ApiProblem(400, 'VALIDATION_ERROR', 'Customer must be at least 18 years old', [{'field': 'customer.dateOfBirth', 'message': 'must be at least 18 years ago'}])
    minimum = Decimal('1000.00') if req.accountType == 'SAVINGS' else Decimal('5000.00')
    if req.initialDeposit < minimum:
        raise ApiProblem(400, 'VALIDATION_ERROR', f'{req.accountType} initial deposit must be at least {minimum:.2f}', [{'field': 'initialDeposit', 'message': f'must be at least {minimum:.2f}'}])
    try:
        with pool.connection() as conn:
            with conn.transaction():
                row = conn.execute('SELECT customer_id, full_name FROM customer WHERE pan=%s FOR UPDATE', (customer.pan,)).fetchone()
                new_customer = row is None
                if new_customer:
                    row = conn.execute('''INSERT INTO customer(full_name,email,phone,date_of_birth,pan)
                      VALUES (%s,%s,%s,%s,%s) ON CONFLICT (pan) DO NOTHING
                      RETURNING customer_id, full_name''', (customer.fullName, customer.email, customer.phone, customer.dateOfBirth, customer.pan)).fetchone()
                    if row is None:
                        row = conn.execute('SELECT customer_id, full_name FROM customer WHERE pan=%s FOR UPDATE', (customer.pan,)).fetchone()
                        new_customer = False
                account = conn.execute('''INSERT INTO account(customer_id,account_type,balance)
                    VALUES (%s,%s,%s) RETURNING account_id,account_number,account_type,currency,balance,status,opened_at''',
                    (row['customer_id'], req.accountType, req.initialDeposit)).fetchone()
                conn.execute('''INSERT INTO account_transaction(account_id,txn_type,amount,balance_after,description)
                    VALUES (%s,'CREDIT',%s,%s,'Initial deposit')''', (account['account_id'], req.initialDeposit, req.initialDeposit))
        response = {'accountNumber': account['account_number'], 'customerId': row['customer_id'], 'customerName': row['full_name'], 'newCustomer': new_customer, 'accountType': account['account_type'], 'currency': account['currency'].strip(), 'balance': f"{account['balance']:.2f}", 'status': account['status'], 'openedAt': account['opened_at'].isoformat()}
        event_data = {'accountNumber': account['account_number'], 'customerId': row['customer_id'], 'customerName': row['full_name'], 'accountType': account['account_type'], 'currency': account['currency'].strip(), 'initialDeposit': f'{req.initialDeposit:.2f}', 'phone': customer.phone, 'email': customer.email}
        return response, event_data
    except errors.UniqueViolation as exc:
        constraint = getattr(exc.diag, 'constraint_name', '')
        if constraint == 'uq_account_customer_type':
            raise ApiProblem(409, 'DUPLICATE_ACCOUNT_TYPE', 'Customer already has an account of this type') from exc
        if constraint in {'customer_email_key', 'customer_phone_key'}:
            raise ApiProblem(409, 'CUSTOMER_CONFLICT', 'Email or phone belongs to another customer') from exc
        raise


def get_account(account_number: str) -> dict | None:
    with pool.connection() as conn:
        return conn.execute('''SELECT a.account_number,c.full_name AS customer_name,a.account_type,a.currency,a.balance,a.status,a.opened_at
          FROM account a JOIN customer c USING(customer_id) WHERE a.account_number=%s''', (account_number,)).fetchone()


def lookup_transfer(reference_no: str):
    with pool.connection() as conn:
        return conn.execute('''SELECT t.transfer_id,t.reference_no,t.status,fa.account_number AS from_account_number,
          ta.account_number AS to_account_number,t.amount,fa.currency,t.remarks,t.created_at
          FROM fund_transfer t JOIN account fa ON fa.account_id=t.from_account_id
          JOIN account ta ON ta.account_id=t.to_account_id WHERE t.reference_no=%s''', (reference_no,)).fetchone()
