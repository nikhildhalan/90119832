from datetime import datetime, time, timedelta
import hashlib
import json
from decimal import Decimal
from zoneinfo import ZoneInfo
from psycopg import errors
from ..db import pool
from ..errors import ApiProblem
from ..models import TransferRequest

IST = ZoneInfo('Asia/Kolkata')
DAILY_LIMIT = Decimal('500000.00')

def transfer(req: TransferRequest, key: str) -> tuple[dict, dict, bool]:
    if req.fromAccountNumber == req.toAccountNumber:
        raise ApiProblem(422, 'SAME_ACCOUNT_TRANSFER', 'Sender and receiver accounts must differ')
    if req.amount < Decimal('1.00') or req.amount > Decimal('200000.00'):
        raise ApiProblem(400, 'VALIDATION_ERROR', 'Transfer amount must be between 1.00 and 200000.00', [{'field': 'amount', 'message': 'must be between 1.00 and 200000.00'}])
    today_start = datetime.combine(datetime.now(IST).date(), time.min, IST)
    fingerprint = hashlib.sha256(json.dumps({'from': req.fromAccountNumber, 'to': req.toAccountNumber, 'amount': f'{req.amount:.2f}', 'remarks': req.remarks}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    try:
        with pool.connection() as conn:
            with conn.transaction():
                conn.execute("SET LOCAL lock_timeout = '3s'")
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
                prior = conn.execute('''SELECT t.*, fa.account_number AS from_no, ta.account_number AS to_no,
                    fa.currency, d.balance_after AS from_balance_after
                    FROM fund_transfer t JOIN account fa ON fa.account_id=t.from_account_id
                    JOIN account ta ON ta.account_id=t.to_account_id
                    JOIN account_transaction d ON d.transfer_id=t.transfer_id AND d.txn_type='DEBIT'
                    WHERE t.idempotency_key=%s''', (key,)).fetchone()
                if prior:
                    if prior['request_fingerprint'] and prior['request_fingerprint'].strip() != fingerprint:
                        raise ApiProblem(409, 'IDEMPOTENCY_KEY_REUSED', 'Idempotency-Key was already used with a different request body')
                    result = _response(prior)
                    return result, {}, True
                rows = conn.execute('''SELECT account_id,account_number,balance,status FROM account
                    WHERE account_number = ANY(%s) ORDER BY account_id FOR UPDATE''', ([req.fromAccountNumber, req.toAccountNumber],)).fetchall()
                by_no = {r['account_number']: r for r in rows}
                src, dst = by_no.get(req.fromAccountNumber), by_no.get(req.toAccountNumber)
                if src is None or dst is None:
                    missing = req.fromAccountNumber if src is None else req.toAccountNumber
                    raise ApiProblem(404, 'ACCOUNT_NOT_FOUND', f'Account {missing} not found')
                if src['status'] != 'ACTIVE' or dst['status'] != 'ACTIVE':
                    raise ApiProblem(422, 'ACCOUNT_NOT_ACTIVE', 'Both accounts must be ACTIVE')
                if src['balance'] < req.amount:
                    raise ApiProblem(422, 'INSUFFICIENT_FUNDS', 'The sender has insufficient available funds')
                sent = conn.execute('''SELECT COALESCE(SUM(amount),0) AS total FROM fund_transfer
                    WHERE from_account_id=%s AND status='COMPLETED' AND created_at >= %s AND created_at < %s''',
                    (src['account_id'], today_start, today_start + timedelta(days=1))).fetchone()['total']
                if sent + req.amount > DAILY_LIMIT:
                    raise ApiProblem(422, 'DAILY_LIMIT_EXCEEDED', 'The IST daily outgoing transfer limit would be exceeded')
                t = conn.execute('''INSERT INTO fund_transfer(idempotency_key,request_fingerprint,from_account_id,to_account_id,amount,remarks)
                    VALUES(%s,%s,%s,%s,%s,%s) RETURNING transfer_id,reference_no,created_at''',
                    (key, fingerprint, src['account_id'], dst['account_id'], req.amount, req.remarks)).fetchone()
                from_after = conn.execute('''UPDATE account SET balance=balance-%s,updated_at=now(),version=version+1
                    WHERE account_id=%s RETURNING balance''', (req.amount, src['account_id'])).fetchone()['balance']
                to_after = conn.execute('''UPDATE account SET balance=balance+%s,updated_at=now(),version=version+1
                    WHERE account_id=%s RETURNING balance''', (req.amount, dst['account_id'])).fetchone()['balance']
                suffix = f' - {req.remarks}' if req.remarks else ''
                conn.execute('''INSERT INTO account_transaction(account_id,transfer_id,txn_type,amount,balance_after,description)
                    VALUES (%s,%s,'DEBIT',%s,%s,%s),(%s,%s,'CREDIT',%s,%s,%s)''',
                    (src['account_id'],t['transfer_id'],req.amount,from_after,f'Transfer to {dst["account_number"]}{suffix}',
                     dst['account_id'],t['transfer_id'],req.amount,to_after,f'Transfer from {src["account_number"]}{suffix}'))
        body = {'transferId': str(t['transfer_id']), 'referenceNo': t['reference_no'], 'status': 'COMPLETED',
                'fromAccountNumber': req.fromAccountNumber, 'toAccountNumber': req.toAccountNumber,
                'amount': f'{req.amount:.2f}', 'currency': 'INR', 'remarks': req.remarks,
                'fromBalanceAfter': f'{from_after:.2f}', 'createdAt': t['created_at'].astimezone(IST).isoformat()}
        event = {'transferId': str(t['transfer_id']), 'referenceNo': t['reference_no'],
                 'fromAccountNumber': req.fromAccountNumber, 'toAccountNumber': req.toAccountNumber,
                 'amount': f'{req.amount:.2f}', 'currency': 'INR', 'remarks': req.remarks,
                 'fromBalanceAfter': f'{from_after:.2f}', 'toBalanceAfter': f'{to_after:.2f}'}
        return body, event, False
    except errors.LockNotAvailable as exc:
        raise ApiProblem(503, 'SERVICE_BUSY', 'Account is busy; retry shortly', headers={'Retry-After': '1'}) from exc
    except errors.DeadlockDetected as exc:
        raise ApiProblem(503, 'SERVICE_BUSY', 'Account is busy; retry shortly', headers={'Retry-After': '1'}) from exc

def _response(row) -> dict:
    return {'transferId': str(row['transfer_id']), 'referenceNo': row['reference_no'], 'status': row['status'],
            'fromAccountNumber': row['from_no'], 'toAccountNumber': row['to_no'],
            'amount': f"{row['amount']:.2f}", 'currency': row['currency'].strip(), 'remarks': row['remarks'],
            'fromBalanceAfter': f"{row['from_balance_after']:.2f}", 'createdAt': row['created_at'].astimezone(IST).isoformat()}
