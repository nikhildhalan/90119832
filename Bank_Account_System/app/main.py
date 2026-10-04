import logging
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from .db import open_pool, close_pool
from .errors import ApiProblem, api_problem_handler, validation_handler, internal_error_handler
from .events import flush
from .api.routes import router

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
app = FastAPI(title='Horizon Bank Account System', version='1.0.0', description='Capstone account opening, enquiry, transfers and statements API')
app.include_router(router, prefix='/api/v1')
app.add_exception_handler(ApiProblem, api_problem_handler)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(Exception, internal_error_handler)

@app.middleware('http')
async def correlation_middleware(request: Request, call_next):
    supplied = request.headers.get('X-Correlation-Id')
    correlation_id = supplied[:128] if supplied and supplied.strip() else str(uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers['X-Correlation-Id'] = correlation_id
    logging.getLogger('bank.request').info('%s %s -> %s correlation_id=%s', request.method, request.url.path, response.status_code, correlation_id)
    return response

@app.on_event('startup')
def startup():
    open_pool()

@app.on_event('shutdown')
def shutdown():
    flush()
    close_pool()

@app.get('/')
def root():
    return {'service': 'bank-account-service', 'api': '/api/v1', 'docs': '/docs'}
