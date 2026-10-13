"""Compare all row contents of two isolated test databases; output only count/hash."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,'/app')
import pymysql
from app.mysql_store import settings

def snapshot(name):
    if not name.startswith('shixu_') or not name.endswith('_test'):
        raise ValueError('Only isolated _test databases allowed')
    opts=settings(name);opts['cursorclass']=pymysql.cursors.DictCursor
    result={}
    with pymysql.connect(**opts) as c,c.cursor() as q:
        q.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
        q.execute('SHOW TABLES');tables=sorted(next(iter(x.values())) for x in q.fetchall())
        for table in tables:
            if not table.replace('_','').isalnum():raise ValueError('Unexpected table identifier')
            q.execute('SELECT * FROM `'+table+'`')
            rows=sorted(json.dumps(x,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')) for x in q.fetchall())
            result[table]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
        c.rollback()
    return result
if __name__=='__main__':
    left=snapshot(sys.argv[1]);right=snapshot(sys.argv[2]);assert left==right,'Restored row contents differ'
    print(json.dumps({'passed':True,'table_count':len(left),'tables':left,'scope':'All column values, all rows; deterministic sorted JSON digest; same isolated instance, distinct database'}))
