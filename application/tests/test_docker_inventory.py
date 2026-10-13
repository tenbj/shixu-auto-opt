"""Parallel acceptance must never exempt unrelated user containers by name."""
from docker_check import inventory

def test_unrelated_test_named_container_is_preserved():
    rows=[{'ID':'a','Names':'h02test-user-data','Labels':'com.docker.compose.project=user-test'}]
    assert inventory(rows,'our-project',set())==(['a'],[])

def test_only_exact_peer_compose_label_is_exempt():
    rows=[{'ID':'a','Names':'peer','Labels':'com.docker.compose.project=peer'},
          {'ID':'b','Names':'peer-other','Labels':'com.docker.compose.project=peer-other'},
          {'ID':'c','Names':'peer','Labels':''}]
    kept,excluded=inventory(rows,'our-project',{'peer'})
    assert kept==['b','c']
    assert excluded==[{'id':'a','compose_project':'peer'}]

def test_resume_exempts_only_own_compose_project():
    rows=[{'ID':'a','Labels':'com.docker.compose.project=our-project'},
          {'ID':'b','Labels':'com.docker.compose.project=production'}]
    assert inventory(rows,'our-project',set())[0]==['b']


def test_keyboard_interrupt_reaps_command_before_cleanup(monkeypatch):
    import docker_check
    calls=[]
    class Child:
        def communicate(self,**kwargs):raise KeyboardInterrupt()
    child=Child()
    monkeypatch.setattr(docker_check.subprocess,'Popen',lambda *a,**k:child)
    monkeypatch.setattr(docker_check,'stop_command',lambda p:calls.append(p))
    import pytest
    with pytest.raises(KeyboardInterrupt):docker_check.run(['synthetic-command'])
    assert calls==[child]


def test_cleanup_checks_exact_labels_even_after_down(monkeypatch,tmp_path):
    import docker_check,json,pytest
    project='h02test-shixu-ab12';private=tmp_path/'runtime'/project;private.mkdir(parents=True)
    (private/'compose.json').write_text(json.dumps({'services':{'app':{'ports':['127.0.0.1:1234:8765'],'image':'test-only'}}}),encoding='utf-8')
    monkeypatch.setattr(docker_check,'ROOT',tmp_path)
    calls=[]
    def fake_run(args,**kwargs):
        calls.append(args)
        return b'owned-container' if args[1]=='ps' else b''
    monkeypatch.setattr(docker_check,'run',fake_run)
    with pytest.raises(RuntimeError,match='Owned containers remain'):docker_check.cleanup_owned(project,private)
    assert calls[0][-3:]==['down','--volumes','--remove-orphans']
    assert 'label=com.docker.compose.project='+project in calls[1]


def test_original_interrupt_survives_cleanup_failure(monkeypatch):
    import docker_check,pytest
    class Child:
        def communicate(self,**kwargs):raise KeyboardInterrupt('original interruption')
    monkeypatch.setattr(docker_check.subprocess,'Popen',lambda *a,**k:Child())
    def fail_cleanup(p):raise RuntimeError('cleanup failed')
    monkeypatch.setattr(docker_check,'stop_command',fail_cleanup)
    with pytest.raises(KeyboardInterrupt,match='original interruption') as caught:docker_check.run(['synthetic-command'])
    assert 'cleanup failed' in caught.value.__notes__[0]
