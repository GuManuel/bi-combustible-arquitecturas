"""Reproducible benchmark. RESETS only laboratory tables. Stop API consumers first."""
import argparse,asyncio,csv,json,math,os,platform,random,statistics,subprocess,sys,threading,time
from pathlib import Path
from datetime import datetime,timezone
from importlib.metadata import version
import httpx,psutil
import core

OUT=Path('results');OUT.mkdir(exist_ok=True)
def p95(xs):return sorted(xs)[max(0,math.ceil(.95*len(xs))-1)]
def save_csv(path,rows):
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
class Monitor:
    def __init__(self,pid):self.remote=pid!=os.getpid()
    def snap(self):
        if self.remote:
            import urllib.request
            with urllib.request.urlopen('http://127.0.0.1:8019/internal/metrics',timeout=10) as r:return json.load(r)
        from metrics import snapshot
        return snapshot()
    def __enter__(self):
        self.before=self.snap();self.t=time.perf_counter();return self
    def __exit__(self,*a):
        elapsed=time.perf_counter()-self.t;after=self.snap();cpu=after['cpu_seconds']-self.before['cpu_seconds']
        self.result={'app_cpu_seconds':round(cpu,4),'app_cpu_pct_one_core':round(cpu/elapsed*100,2),
                     'app_lifetime_peak_rss_mib':round(after['lifetime_peak_rss_mib'],2)}

def ingestion(repeats,sizes):
    core.init();core.reset();warm=core.generate(1000);core.append(warm)
    for mode in core.MODES:core.drain(mode)
    output=[]
    for n in sizes:
        rows=core.generate(n);truth=core.expected(rows)
        for rep in range(1,repeats+1):
            order=list(core.MODES);random.Random(900+rep+n).shuffle(order)
            for mode in order:
                core.reset();lat=[]
                with Monitor(os.getpid()) as mon:
                    start=time.perf_counter()
                    for i in range(0,n,1000):
                        tick=time.perf_counter();core.append(rows[i:i+1000]);core.drain(mode)
                        lat.append((time.perf_counter()-tick)*1000)
                    elapsed=time.perf_counter()-start
                assert core.totals(mode)==truth,'Incorrect totals'
                tick=time.perf_counter();core.rebuild(mode);replay=time.perf_counter()-tick
                assert core.totals(mode)==truth,'Incorrect replay'
                row=dict(mode=mode,records=n,repeat=rep,seconds=elapsed,records_per_second=n/elapsed,
                    chunk_visible_p95_ms=p95(lat),rebuild_seconds=replay,correct=True,**mon.result)
                output.append(row);print('INGEST',mode,n,rep,round(elapsed,3),flush=True)
                save_csv(OUT/'ingestion.csv',output)
    return output

GQL='query($mode:Architecture!,$plate:String,$start:String,$end:String){summary(mode:$mode,plate:$plate,start:$start,end:$end){plate records gallonsMilli costCents}}'
async def case(client,api,mode,workload,concurrency,count,rep,truth,raw):
    params={'mode':mode}
    if workload=='plate_period':params.update(plate='TST-000',start='2026-10-01',end='2026-10-14')
    async def request():
        if api=='REST':return await client.get('/rest/summary',params=params)
        return await client.post('/graphql',json={'query':GQL,'variables':params})
    for _ in range(10):
        r=await request();r.raise_for_status()
    lat=[];errors=0;payload=[];next_id=0
    async def worker():
        nonlocal errors,next_id
        while next_id<count:
            idx=next_id;next_id+=1;start=time.perf_counter();error='';size=0
            try:
                r=await request();ms=(time.perf_counter()-start)*1000;r.raise_for_status();body=r.json();size=len(r.content)
                if 'errors' in body:raise ValueError(str(body['errors']))
                got=body['summary'] if api=='REST' else body['data']['summary']
                if got!=truth:raise ValueError('Resultado distinto del control')
            except Exception as exc:
                ms=(time.perf_counter()-start)*1000;errors+=1;error=type(exc).__name__+': '+str(exc)
            lat.append(ms);payload.append(size)
            raw.append(dict(api=api,mode=mode,workload=workload,concurrency=concurrency,repeat=rep,request=idx,latency_ms=ms,bytes=size,error=error))
    start=time.perf_counter();await asyncio.gather(*(worker() for _ in range(concurrency)));elapsed=time.perf_counter()-start
    return dict(api=api,mode=mode,workload=workload,concurrency=concurrency,repeat=rep,requests=count,errors=errors,
        seconds=elapsed,successful_rps=(count-errors)/elapsed,median_ms=statistics.median(lat),p95_ms=p95(lat),mean_bytes=statistics.mean(payload))

async def api_bench(repeats,count):
    core.reset();rows=core.generate(100000)
    for i in range(0,len(rows),1000):core.append(rows[i:i+1000])
    for mode in core.MODES:core.drain(mode)
    env={**os.environ,'WORKERS':'0','BENCHMARK_METRICS':'1'}
    log=open(OUT/'api_server.log','w')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','8019','--workers','1','--no-access-log'],env=env,stdout=log,stderr=log)
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8019',timeout=30,limits=httpx.Limits(max_connections=50,max_keepalive_connections=50),trust_env=False) as client:
            for _ in range(100):
                try:
                    r=await client.get('/health')
                    if r.status_code==200:break
                except httpx.ConnectError:pass
                await asyncio.sleep(.1)
            else:raise RuntimeError('API did not start')
            cases=[(api,mode,w,c,r) for r in range(1,repeats+1) for api in ('REST','GraphQL') for mode in core.MODES for w in ('fleet','plate_period') for c in (1,10,30)]
            random.Random(2026).shuffle(cases);out=[];raw=[]
            for api,mode,w,c,rep in cases:
                truth=core.expected(rows) if w=='fleet' else core.expected(rows,'TST-000','2026-10-01','2026-10-14')
                with Monitor(server.pid) as mon:
                    row=await case(client,api,mode,w,c,count,rep,truth,raw)
                row.update(mon.result);out.append(row);save_csv(OUT/'api.csv',out)
                print('API',api,mode,w,c,rep,round(row['p95_ms'],2),'ms',flush=True)
            save_csv(OUT/'requests.csv',raw)
            assert not sum(r['errors'] for r in out),'Benchmark includes errors'
            return out
    finally:
        server.terminate();server.wait(timeout=15);log.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--repeats',type=int,default=3);p.add_argument('--requests',type=int,default=200);args=p.parse_args()
    if args.repeats<1 or args.requests<30:p.error('repeats >= 1 and requests >= 30')
    core.init()
    with core.engine.connect() as c:
        from sqlalchemy import text
        dbversion=c.execute(text('select sqlite_version()' if core.engine.dialect.name=='sqlite' else 'select version()')).scalar_one()
    meta={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'os':platform.platform(),
          'logical_cpus_visible':os.cpu_count(),'ram_visible_gib':round(psutil.virtual_memory().total/2**30,2),
          'database':core.engine.dialect.name,'db_version':dbversion,'repeats':args.repeats,'requests_per_case':args.requests,
          'seed':2026,'batch_interval':10000,'chunk_size':1000,'api_workers':1,'scope':'single host; preliminary SQLite if selected; CPU application only; RSS lifetime process high-water, not per-case peak; no DB server resource accounting',
          'versions':{p:version(p) for p in ['fastapi','uvicorn','graphql-core','SQLAlchemy','psycopg','httpx','psutil']}}
    (OUT/'environment.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    ingestion(args.repeats,[10000,50000,100000]);asyncio.run(api_bench(args.repeats,args.requests))
    print('BENCHMARK OK: results/ingestion.csv, api.csv, requests.csv, environment.json',flush=True)
if __name__=='__main__':main()
