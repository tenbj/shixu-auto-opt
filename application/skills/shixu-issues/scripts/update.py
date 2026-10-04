"""Verify a downloaded Skill ZIP and optionally install it. No network or credential access.

python update.py --bundle <zip> --sha256 <trusted-manifest-hash> --target <skills>/shixu-issues [--apply]
Default is a read-only plan. Existing installations need a matching .installed.json receipt.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from uuid import uuid4
import zipfile

def sha(data):return hashlib.sha256(data).hexdigest()

def linked(path):
    return path.is_symlink() or (path.exists() and bool(getattr(path.lstat(),'st_file_attributes',0)&0x400))

def inspect_bundle(bundle, expected):
    data=Path(bundle).read_bytes()
    if sha(data)!=expected.lower():raise ValueError('Bundle SHA256 mismatch')
    files={}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(x.file_size for x in archive.infolist())>8*1024*1024:raise ValueError('Bundle too large')
        for info in archive.infolist():
            name=info.filename;parts=PurePosixPath(name).parts
            if '\\' in name or ':' in name or name.startswith('/') or '..' in parts or not parts or parts[0]!='shixu-issues':raise ValueError('Unsafe bundle path')
            reserved={'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
            if any(p.endswith((' ','.')) or p.split('.')[0].upper() in reserved for p in parts):raise ValueError('Unsafe Windows filename')
            if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Symlink in bundle')
            if info.is_dir():continue
            key='/'.join(parts[1:])
            if not key or key=='.installed.json' or key.casefold() in {x.casefold() for x in files}:raise ValueError('Invalid or duplicate file')
            files[key]=archive.read(info)
    if not {'SKILL.md','VERSION'}<=files.keys():raise ValueError('Incomplete Skill')
    return files

def install(bundle, expected, target, apply=False, previous_bundle=None, previous_sha256=None):
    files=inspect_bundle(bundle,expected)
    target=Path(target).absolute()
    if target.name!='shixu-issues':raise ValueError('Target must be the shixu-issues directory')
    if any(linked(p) for p in [target,*target.parents]):raise ValueError('Linked target is not supported')
    hashes={k:sha(v) for k,v in files.items()}
    if target.exists():
        if not target.is_dir():raise ValueError('Target is not a directory')
        receipt=target/'.installed.json'
        current={}
        for p in target.rglob('*'):
            if linked(p):raise ValueError('Linked existing file')
            if p.is_file() and p!=receipt:current[p.relative_to(target).as_posix()]=sha(p.read_bytes())
        if receipt.is_file():recorded=json.loads(receipt.read_text(encoding='utf-8'))['files']
        elif previous_bundle and previous_sha256:
            recorded={k:sha(v) for k,v in inspect_bundle(previous_bundle,previous_sha256).items()}
        else:raise ValueError('Existing installation has no receipt; supply verified previous bundle or preserve and review before adoption')
        changed=sorted(k for k in current.keys()|recorded.keys() if current.get(k)!=recorded.get(k))
        if changed:raise ValueError('User modifications preserved: '+', '.join(changed))
        if current==hashes:return dict(status='current',applied=False)
    plan=dict(status='update' if target.exists() else 'install',version=files['VERSION'].decode().strip(),applied=False)
    if not apply:return plan
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.shixu-staging-',dir=target.parent))
    assert staging.resolve().parent==target.parent.resolve()
    backup=None
    try:
        for key,data in files.items():
            path=staging/key;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        (staging/'.installed.json').write_text(json.dumps(dict(bundle_sha256=expected,files=hashes),indent=2),encoding='utf-8')
        if target.exists():
            backup=target.with_name('.shixu-backup-'+uuid4().hex)
            assert backup.resolve().parent==target.resolve().parent==target.parent.resolve()
            os.replace(target,backup)
        try:os.replace(staging,target)
        except Exception:
            if backup:os.replace(backup,target)
            raise
        plan.update(applied=True,backup=str(backup) if backup else None)
        return plan
    finally:
        if staging.exists():
            assert not linked(staging) and staging.resolve().parent==target.parent.resolve()
            shutil.rmtree(staging)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',required=True,type=Path);p.add_argument('--sha256',required=True)
    p.add_argument('--target',required=True,type=Path);p.add_argument('--apply',action='store_true')
    p.add_argument('--previous-bundle',type=Path);p.add_argument('--previous-sha256')
    a=p.parse_args()
    try:print(json.dumps(install(a.bundle,a.sha256,a.target,a.apply,a.previous_bundle,a.previous_sha256),ensure_ascii=False))
    except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:raise SystemExit(str(e))
