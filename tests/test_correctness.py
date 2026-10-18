import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
from fastapi.testclient import TestClient
from app import app

class Correctness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):core.init()
    def setUp(self):core.reset()
    def test_background_ingestion(self):
        import time
        rows=core.generate(2)
        with TestClient(app) as client:
            self.assertEqual(client.post('/events',json={'events':rows}).json()['inserted'],2)
            self.assertEqual(client.post('/events',json={'events':rows}).json()['inserted'],0)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                got=[client.get('/rest/summary',params={'mode':m}).json()['summary'] for m in core.MODES]
                if all(x==core.expected(rows) for x in got):break
                time.sleep(.02)
            else:self.fail('Consumers did not publish the events')
            self.assertEqual(client.get('/health').status_code,200)
    def test_duplicate_late_batch_and_replay(self):
        rows=core.generate(12050)
        self.assertEqual(core.append(rows[:5000]),5000)
        for m in core.MODES:core.drain(m)
        self.assertEqual(core.append(rows[:100]),0)
        core.append(rows[5000:])
        late=dict(rows[0],event_id='late',day='2026-09-01')
        core.append([late]); rows.append(late)
        for m in core.MODES:
            core.drain(m)
            self.assertEqual(core.totals(m),core.expected(rows))
            self.assertEqual(core.totals(m,'TST-000','2026-10-01','2026-10-14'),core.expected(rows,'TST-000','2026-10-01','2026-10-14'))
            self.assertEqual(core.step(m),0)
            core.rebuild(m)
            self.assertEqual(core.totals(m),core.expected(rows))
    def test_rest_graphql_equal_and_validate(self):
        rows=core.generate(123);core.append(rows)
        for m in core.MODES:core.drain(m)
        # No lifespan here, no background consumer during deterministic tests.
        client=TestClient(app)
        for m in core.MODES:
            rest=client.get('/rest/summary',params={'mode':m}).json()['summary']
            gql=client.post('/graphql',json={'query':f'{{summary(mode:{m}){{plate records gallonsMilli costCents}}}}'}).json()
            self.assertNotIn('errors',gql)
            self.assertEqual(rest,gql['data']['summary'])
            self.assertEqual(rest,core.expected(rows))
        self.assertEqual(client.get('/rest/summary?mode=wrong').status_code,422)
        self.assertIn('errors',client.post('/graphql',json={'query':'{ nonexistent }'}).json())
        self.assertEqual(client.post('/events',json={'events':[dict(rows[0],gallons_milli=-1)]}).status_code,422)
    def test_batch_cutover_then_new_events(self):
        rows=core.generate(11000);core.append(rows[:10000]);core.drain('lambda')
        self.assertEqual(core.totals('lambda'),core.expected(rows[:10000]))
        core.append(rows[10000:]);core.drain('lambda')
        self.assertEqual(core.totals('lambda'),core.expected(rows))

if __name__=='__main__':unittest.main()
