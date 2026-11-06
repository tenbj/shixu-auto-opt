import pytest
from fastapi.responses import Response
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'cache.sqlite3')) as client:
        yield client


@pytest.mark.parametrize('path', ['/', '/static/index.html', '/static/accounts-api.js', '/static/ai-access.css'])
def test_gzip_and_revalidation(client, path):
    plain = client.get(path, headers={'Accept-Encoding': 'identity'})
    zipped = client.get(path, headers={'Accept-Encoding': 'gzip'})
    assert zipped.status_code == plain.status_code == 200
    assert zipped.headers['content-encoding'] == 'gzip'
    assert zipped.content == plain.content  # HTTPX decodes the actual gzip stream.
    assert int(zipped.headers['content-length']) < min(len(plain.content) // 2, 80_000)
    assert zipped.headers['etag'] == plain.headers['etag']
    for encoding in ('gzip', 'identity'):
        for etag in (zipped.headers['etag'], '"stale", ' + zipped.headers['etag'], '*'):
            cached = client.get(path, headers={'Accept-Encoding': encoding, 'If-None-Match': etag})
            assert cached.status_code == 304 and cached.content == b''
            assert cached.headers['cache-control'] == 'no-cache'
            assert 'Accept-Encoding' in cached.headers['vary']
    assert client.get(path, headers={'If-None-Match': '"stale"'}).status_code == 200
    assert 'content-encoding' not in client.get(path, headers={'Accept-Encoding': 'gzip;q=0'}).headers


@pytest.mark.parametrize('encoding', ['identity', 'gzip'])
def test_home_head_and_revalidation(client, encoding):
    headers = {'Accept-Encoding': encoding}
    get = client.get('/', headers=headers)
    head = client.head('/', headers=headers)
    assert head.status_code == get.status_code == 200
    assert head.content == b''
    assert head.headers['etag'] == get.headers['etag']
    assert head.headers['cache-control'] == get.headers['cache-control'] == 'no-cache'
    assert 'Accept-Encoding' in head.headers['vary']
    assert 'content-encoding' not in head.headers
    for etag in (get.headers['etag'], '"stale", ' + get.headers['etag'], '*'):
        conditional = {**headers, 'If-None-Match': etag}
        cached = client.head('/', headers=conditional)
        assert cached.status_code == client.get('/', headers=conditional).status_code == 304
        assert cached.content == b''
        assert cached.headers['etag'] == get.headers['etag']
        assert cached.headers['cache-control'] == 'no-cache'
        assert 'Accept-Encoding' in cached.headers['vary']
        assert 'content-encoding' not in cached.headers
    stale = client.head('/', headers={**headers, 'If-None-Match': '"stale"'})
    assert stale.status_code == 200 and stale.content == b''
    assert 'content-encoding' not in stale.headers


@pytest.mark.parametrize('status', [200, 401, 302])
def test_uncacheable_responses(client, status):
    # Insert before the static mount to exercise the same path with non-200 responses.
    path = '/api/health' if status == 200 else '/static/cache-probe'
    client.app.router.add_route(path, lambda request: Response('x' * 2048, status_code=status, media_type='text/html'))
    client.app.router.routes.insert(0, client.app.router.routes.pop())
    for target, expected in [(path, status), ('/api/health', 200), ('/api/workspace', 401)]:
        response = client.get(target, headers={'If-None-Match': '*'}, follow_redirects=False)
        assert response.status_code == expected
        assert response.headers['cache-control'] == 'no-store'
        assert 'etag' not in response.headers and 'content-encoding' not in response.headers


@pytest.mark.parametrize('size,media_type,compressed', [(1024, 'text/plain', False), (1025, 'text/plain', True), (2048, 'application/json', True), (2048, 'image/svg+xml', True), (2048, 'application/octet-stream', False)])
def test_gzip_threshold_and_type(client, size, media_type, compressed):
    client.app.router.add_route('/static/probe', lambda request: Response(b'x' * size, media_type=media_type, headers={'ETag': '"probe"'}))
    client.app.router.routes.insert(0, client.app.router.routes.pop())
    response = client.get('/static/probe', headers={'Accept-Encoding': 'gzip'})
    assert response.content == b'x' * size
    assert (response.headers.get('content-encoding') == 'gzip') == compressed
