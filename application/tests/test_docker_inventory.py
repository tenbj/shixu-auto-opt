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
