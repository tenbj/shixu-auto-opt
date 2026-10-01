"""Read-only HTTP/browser smoke check against an explicitly supplied local/LAN URL."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    host = urlparse(args.url).hostname
    if host != 'localhost' and not ipaddress.ip_address(host).is_private:
        raise SystemExit('Only an explicitly supplied local/private address is supported')
    checks = []
    with httpx.Client(base_url=args.url, trust_env=False, timeout=20) as client:
        for path in ['/', '/api/health', '/docs', '/static/diagrams/erd.html', '/static/diagrams/architecture.html']:
            response = client.get(path)
            assert response.status_code == 200, path
            checks.append({'path': path, 'status': response.status_code})
        assert client.get('/api/health', headers={'Host': 'untrusted.invalid'}).status_code == 400
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        expect(page.locator('#sync-state')).to_contain_text('已同步')
        assert not errors, errors
        browser.close()
    report = {'passed': True, 'scope': '本机通过所给内网IP进行真实HTTP与浏览器只读访问；未使用另一台设备验收',
              'routes': checks, 'browser_loaded_from_api': True, 'unknown_host_rejected': True,
              'writes': 0, 'business_screenshots_saved': False, 'browser_errors': errors}
    (ROOT / 'verification/lan-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
