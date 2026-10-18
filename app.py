import os, threading, logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
from graphql import build_schema,graphql_sync
import core

Mode=Literal['lambda','kappa']
stop=threading.Event()
worker_error=None

def consume():
    global worker_error
    while not stop.is_set():
        try:
            worked=sum(core.step(m) for m in core.MODES)
            if not worked:stop.wait(.05)
        except Exception as exc:
            worker_error=str(exc);logging.exception('Consumer failed');stop.set()

@asynccontextmanager
async def lifespan(app):
    core.init();stop.clear();t=None
    if os.getenv('WORKERS','1')=='1':
        t=threading.Thread(target=consume,daemon=True);t.start()
    yield
    stop.set()
    if t:t.join(timeout=10)

app=FastAPI(title='Laboratorio BI de combustible',version='1.0.0',lifespan=lifespan)

class Event(BaseModel):
    event_id:str=Field(min_length=1,max_length=100)
    plate:str=Field(pattern=r'^[A-Z0-9]{3}-[0-9]{3}$')
    day:date
    odometer:int=Field(ge=0)
    gallons_milli:int=Field(gt=0)
    cost_cents:int=Field(ge=0)

class Batch(BaseModel):
    events:list[Event]=Field(min_length=1,max_length=1000)

class GraphRequest(BaseModel):
    query:str=Field(max_length=10000)
    variables:dict|None=None
    operationName:str|None=None

@app.get('/health')
def health():
    if worker_error:raise HTTPException(503,'Error del consumidor; revisar logs')
    return {'status':'ok','database':core.engine.dialect.name,'consumers':os.getenv('WORKERS','1')=='1'}

@app.post('/events',status_code=202)
def ingest(batch:Batch):
    rows=[dict(e.model_dump(),day=e.day.isoformat()) for e in batch.events]
    return {'received':len(rows),'inserted':core.append(rows),'note':'Consulta eventualmente consistente; ID repetido conserva el primer registro.'}

def query_totals(mode,plate=None,start=None,end=None):
    if start:date.fromisoformat(start)
    if end:date.fromisoformat(end)
    if start and end and start>end:raise ValueError('Inicio posterior al fin')
    return core.totals(mode,plate,start,end)

@app.get('/rest/summary')
def rest_summary(mode:Mode='kappa',plate:str|None=None,start:date|None=None,end:date|None=None):
    try:return {'summary':query_totals(mode,plate,str(start) if start else None,str(end) if end else None)}
    except ValueError as e:raise HTTPException(422,str(e))

schema=build_schema('''
 enum Architecture { lambda kappa }
 type Summary { plate: String!, records: Int!, gallonsMilli: Float!, costCents: Float! }
 type Query { summary(mode: Architecture! = kappa, plate: String, start: String, end: String): [Summary!]! }
''')
schema.get_type('Query').fields['summary'].resolve=lambda obj,info,mode='kappa',plate=None,start=None,end=None:query_totals(mode,plate,start,end)

@app.post('/graphql')
def graphql_api(body:GraphRequest):
    result=graphql_sync(schema,body.query,variable_values=body.variables,operation_name=body.operationName)
    response={'data':result.data}
    if result.errors:response['errors']=[{'message':e.message} for e in result.errors]
    return response

@app.get('/',response_class=HTMLResponse)
def index():
    return '''<!doctype html><html lang="es"><meta charset="utf-8"><title>Laboratorio BI</title>
    <style>body{font:18px system-ui;max-width:850px;margin:60px auto;padding:24px;color:#18283a}a{color:#126099}li{margin:16px 0}code{background:#eef2f5;padding:4px}</style>
    <h1>Laboratorio BI de combustible</h1><p>Demostración educativa con datos ficticios. Lambda y Kappa procesan un log duradero; REST y GraphQL consultan sus resultados.</p>
    <ol><li>Verifica el servidor en <a href="/health">/health</a>.</li><li>Abre <a href="/docs">la consola interactiva</a> para ingresar eventos y ejecutar consultas.</li><li>Compara <a href="/rest/summary?mode=lambda">Lambda</a> y <a href="/rest/summary?mode=kappa">Kappa</a>.</li></ol>
    <p>El benchmark se ejecuta desde la terminal, con consumidores detenidos. Consulta README.md y docs/GUIA_PASO_A_PASO.md.</p></html>'''

@app.get('/internal/metrics',include_in_schema=False)
def internal_metrics():
    if os.getenv('BENCHMARK_METRICS')!='1':raise HTTPException(404)
    from metrics import snapshot
    return snapshot()
