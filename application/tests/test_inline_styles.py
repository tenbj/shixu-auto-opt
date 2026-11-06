"""生成页的 9 处静态样式改为冻结原型 v0.4.0 的类；运行时宽度仍内联。"""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
BUILD = (ROOT / 'scripts' / 'build_frontend.py').read_text(encoding='utf-8')
ACCOUNTS = (ROOT / 'scripts' / 'account_frontend.py').read_text(encoding='utf-8')

STATIC_STYLES = (
    'style="font-size:11px;margin-top:10px"',
    'style="margin:0 12px;color:#bcc6b2"',
    'style="font-size:11px"',
    'style="font-size:10px;color:var(--muted)"',
    'style="margin-top:20px"',
    'style="margin-top:10px"',
    'style="margin-top:15px"',
    'style="padding:8px 0"',
    'style="margin-bottom:18px"',
)
CLASS_MARKUP = (
    'class="sidebar-meta"',
    'class="crumb-sep"',
    'class="sync-state"',
    'class="issue-progress-text"',
    'class="note-motto"',
    'class="list-issue-title"',
    'class="detail-title"',
    'panelhead-inline',
    'class="form-context"',
)
RUNTIME_STYLES = (
    'style="width:${ts.length?n/ts.length*100:0}%"',
    'style="width:${total?count/total*100:0}%;background:var(--dist-${index},#91a985)"',
    'style="width:${denominator?count/denominator*100:0}%;background:var(--dist-${index},#91a985)"',
    'style="--issue-width:${issuePaneWidth}px"',
)
PROTOTYPE_CSS = """/* R4: 9 处内联样式 → 类（含视觉微调） */
.sidebar-meta{font-size:11px;line-height:1.7;margin-top:10px;color:#8a957f}
.crumb-sep{margin:0 10px;color:#bcc6b2;font-weight:300}
.sync-state{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);white-space:nowrap}
.sync-state::before{content:"";width:6px;height:6px;border-radius:50%;background:#91a985}
.issue-progress-text{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.note-motto{margin-top:20px;padding-top:14px;border-top:1px dashed #d3dcc6}
.list-issue-title{margin-top:10px;line-height:1.45}
.detail-title{margin-top:14px;line-height:1.4;overflow-wrap:anywhere}
.panelhead.panelhead-inline{padding:12px 0 8px;margin-top:6px;border-top:1px solid #e6ebdf}
.form-context{margin-bottom:18px;padding:10px 12px;border-radius:8px;background:#f3f6ee;color:#5c7053;font-size:13px;overflow-wrap:anywhere}
@media(max-width:700px){.sync-state{display:none}.form-context{font-size:14px}}"""


def test_static_inline_styles_removed():
    for snippet in STATIC_STYLES:
        assert snippet not in INDEX, snippet


def test_static_classes_match_prototype():
    for snippet in CLASS_MARKUP:
        assert snippet in INDEX
        assert snippet in BUILD
    assert PROTOTYPE_CSS in ACCOUNTS
    assert PROTOTYPE_CSS in INDEX
    assert 'class="sync-state">连接中…' in INDEX
    assert 'class="sync-state">连接中…' in BUILD


def test_runtime_widths_stay_inline():
    for snippet in RUNTIME_STYLES:
        assert snippet in INDEX


def test_generated_frontend_matches_sources(monkeypatch):
    # account_frontend now adapts the API bootstrap; verify the complete generated result.
    generated = {}
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    monkeypatch.setattr(Path, 'write_text', lambda path, text, **kwargs: generated.update({path: text}))
    runpy.run_path(str(ROOT / 'scripts' / 'build_frontend.py'))
    assert generated[ROOT / 'static' / 'index.html'] == INDEX
