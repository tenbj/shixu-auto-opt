import hashlib,importlib.util,json,zipfile
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('skill_updater',ROOT/'skills/shixu-issues/scripts/update.py')
updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)
def bundle(tmp_path,version='1.5.0',extra=None):
    path=tmp_path/(version+'.zip')
    with zipfile.ZipFile(path,'w') as z:
        for k,v in dict({'shixu-issues/SKILL.md':'content','shixu-issues/VERSION':version},**(extra or {})).items():z.writestr(k,v)
    return path,hashlib.sha256(path.read_bytes()).hexdigest()
def test_install_update_backup_and_idempotence(tmp_path):
    path,sha=bundle(tmp_path);target=tmp_path/'client/shixu-issues'
    assert not updater.install(path,sha,target)['applied'] and not target.exists()
    assert updater.install(path,sha,target,True)['applied']
    assert updater.install(path,sha,target,True)['status']=='current'
    path,sha=bundle(tmp_path,'1.6.0')
    result=updater.install(path,sha,target,True)
    assert (Path(result['backup'])/'VERSION').read_text()=='1.5.0'
    assert (target/'VERSION').read_text()=='1.6.0'
def test_user_changes_hash_and_zip_paths(tmp_path):
    path,sha=bundle(tmp_path);target=tmp_path/'shixu-issues'
    with pytest.raises(ValueError,match='SHA256'):updater.install(path,'0'*64,target,True)
    updater.install(path,sha,target,True)
    (target/'SKILL.md').write_text('personal')
    with pytest.raises(ValueError,match='modifications'):updater.install(path,sha,target,True)
    assert (target/'SKILL.md').read_text()=='personal'
    path,sha=bundle(tmp_path,'2.0.0',{'shixu-issues/../../outside':'bad'})
    with pytest.raises(ValueError,match='Unsafe'):updater.install(path,sha,target,True)
    assert not (tmp_path/'outside').exists()
def test_existing_without_receipt_preserved(tmp_path):
    path,sha=bundle(tmp_path);target=tmp_path/'shixu-issues';target.mkdir()
    (target/'SKILL.md').write_text('old')
    with pytest.raises(ValueError,match='no receipt'):updater.install(path,sha,target,True)
    assert (target/'SKILL.md').read_text()=='old'

def test_adopt_verified_legacy_bundle(tmp_path):
    old,old_sha=bundle(tmp_path,'1.4.0');new,new_sha=bundle(tmp_path,'1.5.0')
    target=tmp_path/'shixu-issues';target.mkdir()
    (target/'SKILL.md').write_text('content');(target/'VERSION').write_text('1.4.0')
    result=updater.install(new,new_sha,target,True,old,old_sha)
    assert result['applied'] and (target/'VERSION').read_text()=='1.5.0'
