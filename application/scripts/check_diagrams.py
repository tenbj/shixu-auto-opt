"""Real-browser acceptance for the two offline diagrams; read-only database metadata audit."""
from pathlib import Path
import json
import sys
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification'/'diagrams'
OUT.mkdir(parents=True,exist_ok=True)


def metadata_check(model):
    sys.path.insert(0,str(ROOT))
    import pymysql
    from app.mysql_store import settings
    opts=settings()
    with pymysql.connect(**opts) as connection, connection.cursor() as cur:
        # Only metadata for the application's configured dedicated schema.
        cur.execute('SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,ORDINAL_POSITION',(opts['database'],))
        columns=cur.fetchall()
        cur.execute('SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL',(opts['database'],))
        keys=cur.fetchall()
        connection.rollback()
    expected={(t['name'],f['name']):(f['type'].split('(')[0].lower().replace('boolean','tinyint'),f['nullable']) for t in model['tables'] for f in t['fields']}
    actual={(c['TABLE_NAME'],c['COLUMN_NAME']):(c['DATA_TYPE'],c['IS_NULLABLE']=='YES') for c in columns}
    assert expected==actual,'Live column definitions differ from the diagram'
    names={t['id']:t['name'] for t in model['tables']}
    expected_keys={(names[r['child']],r['fk'],names[r['parent']],r['pk']) for r in model['relations']}
    actual_keys={(r['TABLE_NAME'],r['COLUMN_NAME'],r['REFERENCED_TABLE_NAME'],r['REFERENCED_COLUMN_NAME']) for r in keys}
    assert expected_keys==actual_keys,'Live foreign keys differ from the diagram'
    return {'status':'pass','tables':len(model['tables']),'columns':len(columns),'foreign_keys':len(keys),'business_rows_read':0,'writes':0}


def main():
    errors=[]
    report={'checks':[]}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1920,'height':1200},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        requests=[]
        page.on('request',lambda r:requests.append(r.url) if r.url.startswith(('http://','https://')) else None)
        page.goto((ROOT/'static'/'diagrams'/'erd.html').as_uri()+'?qa=all')
        result=page.evaluate('window.ERD && ERD.validate()')
        page.screenshot(path=str(OUT/'erd-expanded.png'),full_page=True)
        if not result or not result['ok']:
            print(errors,result)
            browser.close()
            return 1
        model=page.evaluate('ERD.model')
        report['expanded']=result
        initial=page.evaluate('ERD.snapshot()')
        page.locator('#fields').click()
        report['collapsed']=page.evaluate('ERD.validate()')
        assert report['collapsed']['ok']
        collapsed=page.evaluate('ERD.snapshot()')
        assert all(t['h']<initial['tables'][i]['h'] for i,t in enumerate(collapsed['tables']))
        assert collapsed['relations']!=initial['relations'],'Paths did not recompute'
        page.screenshot(path=str(OUT/'erd-collapsed.png'),full_page=True)
        page.locator('#fields').click()
        for _ in range(20):
            page.locator('#fields').click()
            assert page.evaluate('ERD.validate().ok')
        assert page.evaluate('ERD.snapshot()')==initial
        report['checks'].append('20 consecutive field toggles; exact layout restored')

        page.locator('.entity[data-id="IS"]').click()
        assert page.locator('#detail tbody tr').count()==21
        assert '非 FK' in page.locator('#detail').inner_text()
        page.locator('#detail .close').click()
        page.locator('.entity[data-id="TA"]').hover()
        assert page.locator('.edge.active').count()==3
        page.locator('.entity[data-id="TA"]').click(button='right')
        page.locator('#hide').click()
        assert page.locator('.entity').count()==8 and page.locator('.edge').count()==3
        page.locator('#show').click()
        assert page.locator('.entity').count()==9 and page.locator('.edge').count()==6
        report['checks'].append('Full field details, linked highlighting, context hide and restore')

        def drag(x,y,dx,dy,kind):
            points=page.evaluate('([x,y,dx,dy])=>{const m=document.querySelector("#canvas").getScreenCTM();return [new DOMPoint(x,y).matrixTransform(m),new DOMPoint(x+dx,y+dy).matrixTransform(m)].map(p=>({x:p.x,y:p.y}))}',[x,y,dx,dy])
            page.mouse.move(points[0]['x'],points[0]['y'])
            target=page.evaluate('([x,y])=>document.elementFromPoint(x,y).closest("[data-drag]")?.dataset.drag',[points[0]['x'],points[0]['y']])
            assert target==kind,(kind,target)
            page.mouse.down()
            page.mouse.move(points[1]['x'],points[1]['y'],steps=8)
            page.mouse.up()
            assert page.evaluate('ERD.validate().ok')

        drag(860,735,18,10,'entity')
        assert page.evaluate('ERD.snapshot().tables.find(t=>t.id==="TA").x')!=750
        page.locator('#reset').click()
        drag(370,130,0,24,'port')
        assert page.evaluate('ERD.snapshot().relations.find(r=>r.id==="FU_issue_id").pts.at(-1).y')!=130
        assert page.evaluate('ERD.snapshot().tables')==initial['tables'],'Endpoint drag moved an entity'
        page.locator('#reset').click()
        hist=page.evaluate('ERD.snapshot().relations.find(r=>r.id==="HI_issue_id")')
        drag(380,hist['pts'][1]['y'],0,20,'edge')
        assert page.evaluate('ERD.snapshot().relations.find(r=>r.id==="HI_issue_id").pts[1].y')!=hist['pts'][1]['y']
        page.locator('#reset').click()
        label=page.evaluate('ERD.snapshot().relations.find(r=>r.id==="FU_issue_id").label')
        drag(label['x'],label['y'],25,0,'label')
        assert page.evaluate('ERD.snapshot().relations.find(r=>r.id==="FU_issue_id").label.x')!=label['x']
        page.screenshot(path=str(OUT/'erd-interaction.png'),full_page=True)
        report['checks'].append('Entity, boundary endpoint, orthogonal edge and anchored label all moved with valid geometry')
        page.locator('#reset').click()
        for s in ['0.5','1','2']:
            page.locator('#scale').select_option(s)
            actual=page.evaluate('document.querySelector("#canvas").getScreenCTM().a')
            assert abs(actual-float(s))<.01
            assert page.evaluate('ERD.validate().ok')
        page.locator('#fit').click()
        page.set_viewport_size({'width':1366,'height':900})
        page.locator('#fit').click()
        assert page.evaluate('ERD.validate().ok')
        page.screenshot(path=str(OUT/'erd-1366.png'),full_page=True)
        report['checks'].append('50%, 100%, 200% zoom; viewport resize and fit')
        page.set_viewport_size({'width':1920,'height':1200})
        page.goto((ROOT/'static'/'diagrams'/'architecture.html').as_uri())
        page.screenshot(path=str(OUT/'architecture.png'),full_page=True)
        assert page.locator('svg .band-title').count()==5
        outside=page.locator('svg text').evaluate_all('(nodes)=>nodes.filter(n=>{const b=n.getBBox();return b.x<0||b.y<0||b.x+b.width>1120||b.y+b.height>990}).map(n=>n.textContent)')
        assert not outside,outside
        page.set_viewport_size({'width':1366,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/'architecture-1366.png'),full_page=True)
        report['checks'].append('Architecture: five semantic bands, SVG text within canvas, responsive layout')
        assert not errors,errors
        assert not requests,requests
        report['browser_errors']=errors
        report['external_requests']=requests
        if '--live-schema' in sys.argv:
            report['live_schema']=metadata_check(model)
        report['status']='pass'
        report['passed']=True
        (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        browser.close()
    return int(bool(errors))


if __name__=='__main__':
    sys.exit(main())
