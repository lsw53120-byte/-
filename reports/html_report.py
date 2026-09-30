import html
from datetime import datetime
from pathlib import Path

from core.indexing_policy import ADVICE
from core.models import Status


STATUS_TITLES = {
    "INDEXED": "정상 색인", "DISCOVERED_NOT_INDEXED": "발견됨 · 현재 미색인",
    "CRAWLED_NOT_INDEXED": "크롤링됨 · 현재 미색인", "ALTERNATE_CANONICAL": "대체 canonical",
    "REDIRECT": "리디렉션", "NOINDEX": "noindex", "ROBOTS_BLOCKED": "robots.txt 차단",
    "NOT_FOUND": "페이지 없음", "SERVER_ERROR": "서버 오류", "TEMP_ERROR": "일시 오류",
    "LOGIN_REQUIRED": "로그인 필요", "TIMEOUT": "시간 초과", "UNKNOWN": "상태 미상",
}


def generate_run_report(store, run_id, property_url, reports_dir):
    """Build a report from persisted run rows, independent of GUI events."""
    rows = store.run_results(run_id)
    if not rows:
        return None
    for item in rows:
        code = item.get("last_status") or "UNKNOWN"
        try:
            status = Status(code)
        except ValueError:
            status = Status.UNKNOWN
        request = store.request_summary(item["url"])
        action = "요청 안 함"
        if request:
            action = {"CONFIRMED": "Google 접수 확인", "ATTEMPTED": "요청 결과 확인 필요",
                      "UNKNOWN": "요청 결과 미확인"}.get(request["outcome"], request["outcome"])
        item.update({"status_code": code, "status_title": STATUS_TITLES.get(code, code),
                     "summary": ADVICE[status],
                     "root_cause": item.get("last_error") or "Search Console 원문을 아래에서 확인하세요.",
                     "action_guide": [ADVICE[status]], "action_taken": action})
    return generate(rows, property_url, reports_dir,
                    filename=f"서치콘솔_진단보고서_작업{run_id}.html")


def generate(results, property_url, reports_dir, filename=None):
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / (filename or ("서치콘솔_진단보고서_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".html"))
    counts = {}
    error_count = sum(bool(result.get("last_error")) for result in results)
    for result in results:
        counts[result.get("status_code", "UNKNOWN")] = counts.get(result.get("status_code", "UNKNOWN"), 0) + 1
    cards = []
    for i, r in enumerate(results, 1):
        status = html.escape(str(r.get("status_title", r.get("status_code", "미상"))))
        url = html.escape(str(r.get("url", "")), quote=True)
        summary = html.escape(str(r.get("summary", "")))
        reason = html.escape(str(r.get("root_cause", "")))
        raw = html.escape(str(r.get("raw_status", "")))
        checked = html.escape(str(r.get("last_checked", "기록 없음")))
        advice = "".join(f"<li>{html.escape(str(step))}</li>" for step in r.get("action_guide", []))
        action = html.escape(str(r.get("action_taken", "요청 안 함")))
        canonical = html.escape(str(r.get("canonical_url") or "확인되지 않음"), quote=True)
        cards.append(f"""<article class="card" data-status="{html.escape(str(r.get('status_code','UNKNOWN')))}">
          <header><span class="badge">{status}</span><span>{action}</span></header>
          <a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>
          <p class="muted">검사 시각: {checked}</p><p>{summary}</p><details><summary>원인과 권장 조치</summary><p>{reason}</p><ul>{advice}</ul>
          <p>Canonical: <a href="{canonical}">{canonical}</a></p><details><summary>Search Console 원문</summary><pre>{raw}</pre></details>
          </details></article>""")
    stats = "".join(f"<div><b>{n}</b><span>{html.escape(k)}</span></div>" for k, n in sorted(counts.items()))
    document = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>Search Console 진단 보고서</title><style>
    body{{font:16px system-ui,sans-serif;background:#f3f6fb;color:#172033;margin:0;padding:24px}}main{{max-width:1050px;margin:auto}}
    .hero,.card{{background:white;border:1px solid #dce3ee;border-radius:14px;padding:22px;margin:14px 0}}
    .stats{{display:flex;gap:10px;flex-wrap:wrap}}.stats div{{background:#eaf1ff;padding:12px;border-radius:10px;min-width:90px}}
    .stats b,.stats span{{display:block}}header{{display:flex;justify-content:space-between;gap:10px;margin-bottom:12px}}
    a{{overflow-wrap:anywhere;color:#1457bd}}.badge{{font-weight:bold}}pre{{white-space:pre-wrap;max-height:350px;overflow:auto}}
    input{{padding:10px;width:min(420px,80%)}}.muted{{color:#65738b}}</style><main>
    <section class="hero"><h1>Search Console URL 진단</h1><p>속성: {html.escape(str(property_url), quote=True)}</p>
    <p class="muted">생성: {datetime.now().astimezone().isoformat(timespec="minutes")} · 색인 요청은 Google의 색인을 보장하지 않습니다.</p>
    <p>{f'이전 검사 오류 기록 {error_count}개가 포함되어 있습니다. 해당 URL의 상태는 Search Console에서 다시 확인하세요.' if error_count else '검사 오류 기록이 없습니다.'}</p>
    <div class="stats">{stats}</div><p><input id="q" placeholder="URL 또는 상태 검색" oninput="filterCards()"></p></section>
    {''.join(cards)}<script>function filterCards(){{let q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.hidden=!c.innerText.toLowerCase().includes(q))}}</script>
    </main></html>"""
    path.write_text(document, encoding="utf-8")
    return path
