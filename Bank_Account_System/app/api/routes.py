import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from .. import cache
from ..config import settings
from ..errors import ApiProblem, problem_body
from ..events import event_envelope, publish
from ..models import AccountOpenRequest, TransferRequest
from ..repositories import accounts, statements, transfers

router = APIRouter()
log = logging.getLogger(__name__)
IST = ZoneInfo('Asia/Kolkata')
IDEM_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')

def account_body(row: dict) -> dict:
    return {'accountNumber': row['account_number'], 'customerName': row['customer_name'], 'accountType': row['account_type'],
            'currency': row['currency'].strip(), 'balance': f"{Decimal(row['balance']):.2f}", 'status': row['status'],
            'openedAt': row['opened_at'].astimezone(IST).isoformat()}

def transfer_lookup_body(row: dict) -> dict:
    return {'transferId': str(row['transfer_id']), 'referenceNo': row['reference_no'], 'status': row['status'],
            'fromAccountNumber': row['from_account_number'], 'toAccountNumber': row['to_account_number'],
            'amount': f"{row['amount']:.2f}", 'currency': row['currency'].strip(), 'remarks': row['remarks'],
            'createdAt': row['created_at'].astimezone(IST).isoformat()}

@router.post('/accounts', status_code=201)
def open_account(req: AccountOpenRequest, request: Request, response: Response):
    body, event_data = accounts.open_account(req)
    publish('bank.account.opened.v1', body['accountNumber'], event_envelope('AccountOpened', request.state.correlation_id, event_data))
    response.headers['Location'] = f"/api/v1/accounts/{body['accountNumber']}"
    return body

@router.get('/accounts/{account_number}')
def get_account(account_number: str, response: Response):
    if not re.fullmatch(r'\d{12}', account_number):
        raise ApiProblem(400, 'VALIDATION_ERROR', 'Account number must be 12 digits', [{'field': 'accountNumber', 'message': 'must be 12 digits'}])
    try:
        cached = cache.client.hgetall(cache.account_key(account_number))
        if cached:
            response.headers['X-Cache'] = 'HIT'
            cached['balance'] = f'{Decimal(cached["balance"]):.2f}'
            return cached
    except RedisError:
        log.warning('Redis account-cache read failed; falling back to PostgreSQL')
    row = accounts.get_account(account_number)
    if row is None:
        raise ApiProblem(404, 'ACCOUNT_NOT_FOUND', 'Account not found')
    body = account_body(row)
    response.headers['X-Cache'] = 'MISS'
    try:
        cache.client.hset(cache.account_key(account_number), mapping=body)
        cache.client.expire(cache.account_key(account_number), settings.account_cache_ttl)
    except RedisError:
        log.warning('Redis account-cache write failed')
    return body

@router.post('/transfers', status_code=201)
def make_transfer(req: TransferRequest, request: Request, response: Response,
                  idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    if not idempotency_key or not IDEM_RE.fullmatch(idempotency_key):
        raise ApiProblem(400, 'MISSING_IDEMPOTENCY_KEY', 'Idempotency-Key is required and must be 1-64 letters, digits, hyphens or underscores')
    redis_key = cache.idempotency_key(idempotency_key)
    fingerprint = hashlib.sha256(json.dumps({'from': req.fromAccountNumber, 'to': req.toAccountNumber, 'amount': f'{req.amount:.2f}', 'remarks': req.remarks}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    redis_claimed = False
    try:
        stored = cache.client.get(redis_key)
        if stored:
            if stored == 'PENDING':
                raise ApiProblem(409, 'REQUEST_IN_PROGRESS', 'A request with this idempotency key is still processing')
            cached_result = cache.load(stored)
            if cached_result.get('fingerprint') != fingerprint:
                raise ApiProblem(409, 'IDEMPOTENCY_KEY_REUSED', 'Idempotency-Key was already used with a different request body')
            response.headers['Idempotent-Replayed'] = 'true'
            if cached_result['status'] >= 400:
                return JSONResponse(cached_result['body'], status_code=cached_result['status'], media_type='application/problem+json', headers={'Idempotent-Replayed':'true'})
            response.status_code = cached_result['status']
            return cached_result['body']
        redis_claimed = bool(cache.client.set(redis_key, 'PENDING', nx=True, ex=120))
        if not redis_claimed:
            stored = cache.client.get(redis_key)
            if stored == 'PENDING':
                raise ApiProblem(409, 'REQUEST_IN_PROGRESS', 'A request with this idempotency key is still processing')
            if stored:
                cached_result = cache.load(stored)
                if cached_result.get('fingerprint') != fingerprint:
                    raise ApiProblem(409, 'IDEMPOTENCY_KEY_REUSED', 'Idempotency-Key was already used with a different request body')
                response.headers['Idempotent-Replayed'] = 'true'
                response.status_code = cached_result['status']
                return cached_result['body']
    except RedisError:
        log.warning('Redis idempotency unavailable; relying on PostgreSQL unique key')

    try:
        body, event_data, replayed = transfers.transfer(req, idempotency_key)
    except ApiProblem as exc:
        if redis_claimed and exc.status in {400, 404, 409, 422}:
            try:
                problem = problem_body(request, exc.status, exc.code, exc.detail, exc.errors)
                cache.client.set(redis_key, cache.dump({'status': exc.status, 'body': problem, 'fingerprint': fingerprint}), ex=settings.idempotency_ttl)
            except RedisError:
                pass
        elif redis_claimed:
            try:
                cache.client.delete(redis_key)
            except RedisError:
                pass
        raise
    if replayed:
        response.headers['Idempotent-Replayed'] = 'true'
        return body
    response.headers['Location'] = f"/api/v1/transfers/{body['referenceNo']}"
    try:
        cache.client.delete(cache.account_key(req.fromAccountNumber), cache.account_key(req.toAccountNumber))
        cache.client.incr(cache.statement_version_key(req.fromAccountNumber))
        cache.client.incr(cache.statement_version_key(req.toAccountNumber))
    except RedisError:
        log.warning('Redis post-transfer cache invalidation failed; database remains authoritative')
    try:
        cache.client.set(redis_key, cache.dump({'status': 201, 'body': body, 'fingerprint': fingerprint}), ex=settings.idempotency_ttl)
    except RedisError:
        log.warning('Redis idempotency result write failed; PostgreSQL unique key remains authoritative')
    public_data = dict(event_data)
    event = event_envelope('TransferCompleted', request.state.correlation_id, public_data)
    publish('bank.transfer.completed.v1', req.fromAccountNumber, event)
    return body

@router.get('/transfers/{reference_no}')
def get_transfer(reference_no: str):
    row = accounts.lookup_transfer(reference_no)
    if row is None:
        raise ApiProblem(404, 'TRANSFER_NOT_FOUND', 'Transfer reference not found')
    return transfer_lookup_body(row)

@router.get('/accounts/{account_number}/statement')
def get_statement(account_number: str, response: Response,
                  from_date: date | None = Query(default=None, alias='fromDate'),
                  to_date: date | None = Query(default=None, alias='toDate'),
                  page: int = Query(default=0, ge=0), size: int = Query(default=20, ge=1, le=100)):
    if not re.fullmatch(r'\d{12}', account_number):
        raise ApiProblem(400, 'VALIDATION_ERROR', 'Account number must be 12 digits', [{'field':'accountNumber','message':'must be 12 digits'}])
    today = datetime.now(IST).date()
    end_date = to_date or today
    start_date = from_date or (end_date - timedelta(days=29))
    if start_date > end_date:
        raise ApiProblem(400, 'VALIDATION_ERROR', 'fromDate must not be after toDate', [{'field':'fromDate','message':'must be on or before toDate'}])
    if end_date > today:
        raise ApiProblem(400, 'VALIDATION_ERROR', 'toDate cannot be in the future', [{'field':'toDate','message':'must not be in the future'}])
    if (end_date - start_date).days > 89:
        raise ApiProblem(400, 'VALIDATION_ERROR', 'Statement period must be at most 90 days', [{'field':'toDate','message':'date range must be at most 90 days'}])
    try:
        version = int(cache.client.get(cache.statement_version_key(account_number)) or '0')
        key = cache.statement_key(account_number, version, start_date.isoformat(), end_date.isoformat(), page, size)
        cached = cache.client.get(key)
        if cached:
            response.headers['X-Cache'] = 'HIT'
            return cache.load(cached)
    except RedisError:
        key = None
        log.warning('Redis statement-cache read failed; falling back to PostgreSQL')
    result = statements.statement(account_number, start_date, end_date, page, size)
    if result is None:
        raise ApiProblem(404, 'ACCOUNT_NOT_FOUND', 'Account not found')
    response.headers['X-Cache'] = 'MISS'
    if key:
        try:
            cache.client.set(key, cache.dump(result), ex=settings.statement_cache_ttl)
        except RedisError:
            log.warning('Redis statement-cache write failed')
    return result

@router.get('/health')
def health():
    checks = {}
    try:
        with __import__('app.db', fromlist=['pool']).pool.connection() as conn:
            conn.execute('SELECT 1')
        checks['postgres'] = 'UP'
    except Exception:
        checks['postgres'] = 'DOWN'
    try:
        cache.client.ping()
        checks['redis'] = 'UP'
    except Exception:
        checks['redis'] = 'DOWN'
    try:
        from confluent_kafka.admin import AdminClient
        AdminClient({'bootstrap.servers': settings.kafka_bootstrap_servers, 'socket.timeout.ms': 1000}).list_topics(timeout=1.5)
        checks['kafka'] = 'UP'
    except Exception:
        checks['kafka'] = 'DOWN'
    healthy = all(value == 'UP' for value in checks.values())
    return JSONResponse({'status': 'UP' if healthy else 'DOWN', 'dependencies': checks}, status_code=200 if healthy else 503)
