from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from ..db import pool
from ..errors import ApiProblem

IST = ZoneInfo('Asia/Kolkata')

def statement(account_number: str, start_date: date, end_date: date, page: int, size: int) -> dict | None:
    start = datetime.combine(start_date, time.min, IST)
    end = datetime.combine(end_date + timedelta(days=1), time.min, IST)
    offset = page * size
    with pool.connection() as conn:
        account = conn.execute('''SELECT account_number, c.full_name AS customer_name, a.currency
          FROM account a JOIN customer c USING(customer_id) WHERE account_number=%s''', (account_number,)).fetchone()
        if account is None:
            return None
        totals = conn.execute('''SELECT
            COALESCE(SUM(amount) FILTER (WHERE txn_time < %s AND txn_type='CREDIT'),0) -
            COALESCE(SUM(amount) FILTER (WHERE txn_time < %s AND txn_type='DEBIT'),0) AS opening_balance,
            COALESCE(SUM(amount) FILTER (WHERE txn_time < %s AND txn_type='CREDIT'),0) -
            COALESCE(SUM(amount) FILTER (WHERE txn_time < %s AND txn_type='DEBIT'),0) AS closing_balance,
            COALESCE(SUM(amount) FILTER (WHERE txn_time >= %s AND txn_time < %s AND txn_type='CREDIT'),0) AS credits,
            COALESCE(SUM(amount) FILTER (WHERE txn_time >= %s AND txn_time < %s AND txn_type='DEBIT'),0) AS debits,
            COUNT(*) FILTER (WHERE txn_time >= %s AND txn_time < %s) AS count
            FROM account_transaction WHERE account_id=(SELECT account_id FROM account WHERE account_number=%s)''',
            (start,start,end,end,start,end,start,end,start,end,account_number)).fetchone()
        # The in-period net movement is added to the opening balance.
        closing = totals['opening_balance'] + totals['credits'] - totals['debits']
        txn_rows = conn.execute('''SELECT l.txn_id,l.txn_time,l.txn_type,l.amount,l.balance_after,l.description,t.reference_no
          FROM account_transaction l LEFT JOIN fund_transfer t USING(transfer_id)
          WHERE l.account_id=(SELECT account_id FROM account WHERE account_number=%s) AND l.txn_time >= %s AND l.txn_time < %s
          ORDER BY l.txn_time DESC,l.txn_id DESC LIMIT %s OFFSET %s''', (account_number,start,end,size,offset)).fetchall()
    count = totals['count']
    return {'accountNumber': account['account_number'], 'customerName': account['customer_name'], 'currency': account['currency'].strip(),
            'fromDate': start_date.isoformat(), 'toDate': end_date.isoformat(),
            'openingBalance': f"{totals['opening_balance']:.2f}", 'closingBalance': f'{closing:.2f}',
            'totalCredits': f"{totals['credits']:.2f}", 'totalDebits': f"{totals['debits']:.2f}",
            'page': page, 'size': size, 'totalElements': count, 'totalPages': (count + size - 1) // size,
            'transactions': [{'txnId': r['txn_id'], 'txnTime': r['txn_time'].astimezone(IST).isoformat(), 'type': r['txn_type'],
                              'amount': f"{r['amount']:.2f}", 'balanceAfter': f"{r['balance_after']:.2f}",
                              'description': r['description'], 'referenceNo': r['reference_no']} for r in txn_rows]}
