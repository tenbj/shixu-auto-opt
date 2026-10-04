"""Build the application-owned portable Skill; deterministic bytes and per-file hashes."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    source=ROOT/'skills/shixu-issues'
    version=(source/'VERSION').read_text(encoding='utf-8').strip()
    filename=f'shixu-issues-{version}.zip'
    files=sorted(p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    target=ROOT/'downloads'/filename
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info=zipfile.ZipInfo('shixu-issues/'+p.relative_to(source).as_posix(),date_time=(2026,10,4,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,p.read_bytes())
    manifest=dict(name='shixu-issues',version=version,filename=filename,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source='application/skills/shixu-issues',derivedFrom='F02 portable Skill 1.4.0; system releases maintain this portable distribution',sources={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (ROOT/'downloads/skill-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(filename+' '+manifest['sha256'])
if __name__=='__main__':main()
