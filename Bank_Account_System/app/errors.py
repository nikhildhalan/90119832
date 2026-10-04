from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from datetime import datetime
from zoneinfo import ZoneInfo

class ApiProblem(Exception):
    def __init__(self, status: int, code: str, detail: str, errors: list[dict] | None = None, headers: dict | None = None):
        self.status, self.code, self.detail, self.errors, self.headers = status, code, detail, errors or [], headers or {}

def problem_body(request: Request, status: int, code: str, detail: str, errors=None):
    corr = getattr(request.state, 'correlation_id', 'unknown')
    return {'type': f'https://api.horizonbank.example/problems/{code.lower().replace("_", "-")}', 'title': code.replace('_', ' ').title(), 'status': status, 'detail': detail, 'instance': request.url.path, 'errorCode': code, 'correlationId': corr, 'timestamp': datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(), 'errors': errors or []}

async def api_problem_handler(request: Request, exc: ApiProblem):
    return JSONResponse(problem_body(request, exc.status, exc.code, exc.detail, exc.errors), status_code=exc.status, headers=exc.headers, media_type='application/problem+json')

async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{'field': '.'.join(str(x) for x in item.get('loc', ()) if x != 'body'), 'message': item.get('msg', 'Invalid value')} for item in exc.errors()]
    return JSONResponse(problem_body(request, 400, 'VALIDATION_ERROR', f'{len(errors)} field(s) are invalid', errors), status_code=400, media_type='application/problem+json')

async def internal_error_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger(__name__).exception('Unhandled request error correlation_id=%s', getattr(request.state, 'correlation_id', 'unknown'), exc_info=exc)
    return JSONResponse(problem_body(request, 500, 'INTERNAL_ERROR', 'An unexpected error occurred'), status_code=500, media_type='application/problem+json')
