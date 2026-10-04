from fastapi.testclient import TestClient as BaseClient
class TestClient(BaseClient):
    def __enter__(self):
        super().__enter__()
        body=dict(username='fixture',password='fixture-only-password',displayName='Fixture')
        result=self.post('/api/auth/register',json=body)
        if result.status_code==409:result=self.post('/api/auth/login',json=body)
        assert result.status_code==200,result.text
        self.headers['x-csrf-token']=result.json()['csrf']
        return self
