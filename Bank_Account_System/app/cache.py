import json
import redis
from .config import settings

client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True)

def account_key(number: str) -> str:
    return f'bank:account:{number}'

def statement_version_key(number: str) -> str:
    return f'bank:stmt-ver:{number}'

def statement_key(number: str, version: int, from_date: str, to_date: str, page: int, size: int) -> str:
    return f'bank:stmt:{number}:v{version}:{from_date}:{to_date}:{page}:{size}'

def idempotency_key(key: str) -> str:
    return f'bank:idem:{key}'

def dump(value) -> str:
    return json.dumps(value, default=str, separators=(',', ':'))

def load(value: str):
    return json.loads(value)
