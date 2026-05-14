from __future__ import annotations

import datetime as dt
import html
import json
import re
import threading
import traceback
import uuid
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

load_dotenv()
load_dotenv(".env.enterprise", override=False)

ANALYSTS = ("market", "social", "news", "fundamentals")
ANALYST_LABELS = {
    "market": "市场分析",
    "social": "社交情绪",
    "news": "新闻分析",
    "fundamentals": "基本面分析",
}
STATUS_LABELS = {
    "queued": "排队中",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
}
PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "google": None,
    "anthropic": "https://api.anthropic.com/",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4/",
    "openrouter": "https://openrouter.ai/api/v1",
    "azure": None,
    "ollama": "http://localhost:11434/v1",
}


@dataclass
class WebJob:
    id: str
    params: dict[str, Any]
    status: str = "queued"
    created_at: str = field(default_factory=lambda: dt.datetime.now().isoformat(timespec="seconds"))
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, WebJob] = {}
        self._lock = threading.Lock()

    def create(self, params: dict[str, Any]) -> WebJob:
        job = WebJob(id=uuid.uuid4().hex[:12], params=params)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> WebJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self) -> list[WebJob]:
        with self._lock:
            return list(self._jobs.values())[-20:][::-1]

    def update(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in updates.items():
                setattr(job, key, value)


JOB_STORE = JobStore()


class SerialJobRunner:
    """Single-worker background queue for TradingAgents jobs."""

    def __init__(self) -> None:
        self._queue: list[str] = []
        self._condition = threading.Condition()
        self._started = False

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            worker = threading.Thread(target=self._run_forever, daemon=True)
            worker.start()
            self._started = True

    def enqueue(self, job_id: str) -> None:
        self.start()
        with self._condition:
            self._queue.append(job_id)
            self._condition.notify()

    def _run_forever(self) -> None:
        while True:
            with self._condition:
                while not self._queue:
                    self._condition.wait()
                job_id = self._queue.pop(0)
            run_job(job_id)


JOB_RUNNER = SerialJobRunner()


def parse_form(raw_body: bytes) -> dict[str, Any]:
    values = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
    today = dt.datetime.now().strftime("%Y-%m-%d")
    analysts = [item for item in values.get("analysts", []) if item in ANALYSTS]
    if not analysts:
        analysts = ["market", "news"]

    provider = values.get("llm_provider", ["openai"])[0].strip().lower() or "openai"
    backend_url = values.get("backend_url", [""])[0].strip()
    params = {
        "request_text": values.get("request_text", [""])[0].strip(),
        "ticker": values.get("ticker", ["SPY"])[0].strip().upper() or "SPY",
        "analysis_date": values.get("analysis_date", [today])[0].strip() or today,
        "analysts": analysts,
        "research_depth": _to_int(values.get("research_depth", ["1"])[0], default=1),
        "llm_provider": provider,
        "backend_url": backend_url or PROVIDER_URLS.get(provider),
        "quick_think_llm": values.get("quick_think_llm", [DEFAULT_CONFIG["quick_think_llm"]])[0].strip() or DEFAULT_CONFIG["quick_think_llm"],
        "deep_think_llm": values.get("deep_think_llm", [DEFAULT_CONFIG["deep_think_llm"]])[0].strip() or DEFAULT_CONFIG["deep_think_llm"],
        "output_language": values.get("output_language", ["Chinese"])[0].strip() or "Chinese",
        "checkpoint_enabled": values.get("checkpoint_enabled", ["off"])[0] == "on",
    }
    if params["request_text"]:
        params.update(infer_request_params(params["request_text"], today))
        if not params.get("backend_url"):
            params["backend_url"] = PROVIDER_URLS.get(params["llm_provider"])
    return params


def infer_request_params(request_text: str, today: str | None = None) -> dict[str, Any]:
    """Parse a Codex-style natural language request into TradingAgents parameters."""
    today = today or dt.datetime.now().strftime("%Y-%m-%d")
    text = request_text.strip()
    lower = text.lower()
    updates: dict[str, Any] = {}

    ticker = _infer_ticker(text)
    if ticker:
        updates["ticker"] = ticker

    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if date_match:
        updates["analysis_date"] = date_match.group(1)
    elif "今天" in text or "today" in lower:
        updates["analysis_date"] = today
    elif "昨天" in text or "yesterday" in lower:
        updates["analysis_date"] = (
            dt.datetime.strptime(today, "%Y-%m-%d") - dt.timedelta(days=1)
        ).strftime("%Y-%m-%d")

    if "英文" in text or "english" in lower:
        updates["output_language"] = "English"
    elif "中文" in text or "chinese" in lower or "汉语" in text:
        updates["output_language"] = "Chinese"

    if "全部" in text or "所有" in text or "all analysts" in lower:
        updates["analysts"] = list(ANALYSTS)
    else:
        requested_analysts = []
        if any(word in lower for word in ("market", "technical")) or any(word in text for word in ("市场", "技术", "指标")):
            requested_analysts.append("market")
        if "social" in lower or any(word in text for word in ("社交", "情绪", "舆情")):
            requested_analysts.append("social")
        if "news" in lower or any(word in text for word in ("新闻", "消息", "宏观")):
            requested_analysts.append("news")
        if "fundamental" in lower or any(word in text for word in ("基本面", "财报", "估值")):
            requested_analysts.append("fundamentals")
        if requested_analysts:
            updates["analysts"] = [a for a in ANALYSTS if a in requested_analysts]

    depth_match = re.search(r"(?:深度|depth)\s*[:：=]?\s*([1-5])", lower)
    if depth_match:
        updates["research_depth"] = int(depth_match.group(1))
    elif any(word in text for word in ("最深", "全面", "深入")) or "deep" in lower:
        updates["research_depth"] = 5
    elif any(word in text for word in ("快速", "简单", "简要")) or "quick" in lower:
        updates["research_depth"] = 1

    for provider in PROVIDER_URLS:
        if provider in lower:
            updates["llm_provider"] = provider
            updates["backend_url"] = PROVIDER_URLS[provider]
            break

    if "断点" in text or "续跑" in text or "checkpoint" in lower:
        updates["checkpoint_enabled"] = True

    return updates


def _infer_ticker(text: str) -> str | None:
    for pattern in (
        r"(?:分析|评估|看看|研究|analyze|check|review)\s+([A-Za-z][A-Za-z0-9.-]{0,12})",
        r"(?:股票|代码|ticker|symbol)\s*[:：=]?\s*([A-Za-z][A-Za-z0-9.-]{0,12})",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()

    ignored = {"OPENAI", "OLLAMA", "SPY", "ETF", "AI", "LLM"}
    candidates = re.findall(r"\b[A-Z][A-Z0-9]{0,5}(?:[.-][A-Z0-9]{1,4})?\b", text)
    for candidate in candidates:
        if candidate.upper() not in ignored:
            return candidate.upper()
    return None


def _to_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(1, min(parsed, 5))


def build_config(params: dict[str, Any]) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = params["llm_provider"]
    config["backend_url"] = params["backend_url"]
    config["quick_think_llm"] = params["quick_think_llm"]
    config["deep_think_llm"] = params["deep_think_llm"]
    config["output_language"] = params["output_language"]
    config["max_debate_rounds"] = params["research_depth"]
    config["max_risk_discuss_rounds"] = params["research_depth"]
    config["checkpoint_enabled"] = params["checkpoint_enabled"]
    return config


def run_job(job_id: str) -> None:
    job = JOB_STORE.get(job_id)
    if job is None:
        return

    JOB_STORE.update(job_id, status="running", started_at=dt.datetime.now().isoformat(timespec="seconds"))
    try:
        config = build_config(job.params)
        graph = TradingAgentsGraph(
            selected_analysts=job.params["analysts"],
            config=config,
            debug=False,
        )
        final_state, decision = graph.propagate(job.params["ticker"], job.params["analysis_date"])
        report_path = write_web_report(config["results_dir"], job, final_state, decision)
        JOB_STORE.update(
            job_id,
            status="completed",
            finished_at=dt.datetime.now().isoformat(timespec="seconds"),
            result={
                "decision": decision,
                "report_path": str(report_path),
                "final_state": final_state,
            },
        )
    except Exception as exc:
        JOB_STORE.update(
            job_id,
            status="failed",
            finished_at=dt.datetime.now().isoformat(timespec="seconds"),
            error=f"{exc}\n\n{traceback.format_exc()}",
        )


def write_web_report(results_dir: str, job: WebJob, final_state: dict[str, Any], decision: str) -> Path:
    run_dir = (
        Path(results_dir)
        / job.params["ticker"]
        / job.params["analysis_date"]
        / f"web_{job.id}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    report = render_markdown_report(job.params["ticker"], job.params["analysis_date"], final_state, decision)
    report_path = run_dir / "complete_report.md"
    report_path.write_text(report, encoding="utf-8")
    (run_dir / "final_state.json").write_text(
        json.dumps(final_state, indent=2, default=str),
        encoding="utf-8",
    )
    return report_path


def render_markdown_report(ticker: str, analysis_date: str, final_state: dict[str, Any], decision: str) -> str:
    sections = [
        f"# 交易分析报告：{ticker}",
        f"分析日期：{analysis_date}",
        f"生成时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "## 最终决策",
        str(decision),
    ]
    for key, title in (
        ("market_report", "市场分析"),
        ("sentiment_report", "社交情绪"),
        ("news_report", "新闻分析"),
        ("fundamentals_report", "基本面分析"),
        ("investment_plan", "研究团队决策"),
        ("trader_investment_plan", "交易计划"),
        ("final_trade_decision", "投资组合经理决策"),
    ):
        value = final_state.get(key)
        if value:
            sections.extend([f"## {title}", str(value)])
    return "\n\n".join(sections) + "\n"


def job_payload(job: WebJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "status_label": status_label(job.status),
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "params": job.params,
        "error": job.error,
        "result": {
            "decision": job.result.get("decision"),
            "report_path": job.result.get("report_path"),
        } if job.result else None,
    }


class TradingAgentsWebHandler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsWeb/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(render_home())
            return
        if path.startswith("/jobs/") and path.endswith(".json"):
            job_id = path.removeprefix("/jobs/").removesuffix(".json")
            self._send_job_json(job_id)
            return
        if path.startswith("/jobs/"):
            job_id = path.removeprefix("/jobs/")
            self._send_html(render_job_page(job_id))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/jobs":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        params = parse_form(self.rfile.read(length))
        job = JOB_STORE.create(params)
        JOB_RUNNER.enqueue(job.id)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/jobs/{job.id}")
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_job_json(self, job_id: str) -> None:
        job = JOB_STORE.get(job_id)
        if job is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = json.dumps(job_payload(job)).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def render_home() -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    jobs = "\n".join(render_job_row(job) for job in JOB_STORE.recent())
    analyst_checks = "\n".join(
        f'<label><input type="checkbox" name="analysts" value="{a}" {"checked" if a in ("market", "news") else ""}> {ANALYST_LABELS[a]}</label>'
        for a in ANALYSTS
    )
    provider_options = "\n".join(f'<option value="{p}">{p}</option>' for p in PROVIDER_URLS)
    return page(
        "TradingAgents Web 控制台",
        f"""
        <main class="shell">
          <section class="run">
            <h1>TradingAgents Codex 控制台</h1>
            <form method="post" action="/jobs">
              <label class="prompt">任务描述
                <textarea name="request_text" rows="5" placeholder="例如：用中文分析 NVDA 今天的交易建议，深度 3，包含新闻、市场和基本面。"></textarea>
              </label>
              <button type="submit">执行任务</button>
              <details>
                <summary>高级参数</summary>
                <div class="grid">
                  <label>股票代码 <input name="ticker" value="SPY"></label>
                  <label>分析日期 <input type="date" name="analysis_date" value="{today}"></label>
                  <label>模型提供商 <select name="llm_provider">{provider_options}</select></label>
                  <label>研究深度 <input type="number" name="research_depth" min="1" max="5" value="1"></label>
                  <label>快速模型 <input name="quick_think_llm" value="{html.escape(DEFAULT_CONFIG["quick_think_llm"])}"></label>
                  <label>深度模型 <input name="deep_think_llm" value="{html.escape(DEFAULT_CONFIG["deep_think_llm"])}"></label>
                  <label>输出语言 <input name="output_language" value="Chinese"></label>
                  <label>后端地址 <input name="backend_url" placeholder="使用提供商默认地址"></label>
                </div>
                <fieldset>
                  <legend>分析师</legend>
                  <div class="checks">{analyst_checks}</div>
                </fieldset>
                <label class="inline"><input type="checkbox" name="checkpoint_enabled"> 启用断点续跑</label>
              </details>
            </form>
          </section>
          <section class="history">
            <h2>最近任务</h2>
            <div class="jobs">{jobs or '<p class="muted">暂无任务。</p>'}</div>
          </section>
        </main>
        """,
    )


def render_job_page(job_id: str) -> str:
    job = JOB_STORE.get(job_id)
    if job is None:
        return page("任务不存在", '<main class="shell"><h1>任务不存在</h1><a href="/">返回</a></main>')

    result_html = ""
    if job.result:
        report = Path(job.result["report_path"]).read_text(encoding="utf-8")
        result_html = f"""
        <section class="result">
          <h2>结果</h2>
          <p><strong>报告：</strong> {html.escape(job.result["report_path"])}</p>
          <pre>{html.escape(report)}</pre>
        </section>
        """
    elif job.error:
        result_html = f'<section class="result error"><h2>错误</h2><pre>{html.escape(job.error)}</pre></section>'

    return page(
        f"任务 {job.id}",
        f"""
        <main class="shell">
          <a href="/">返回</a>
          <section class="status">
            <h1>{html.escape(job.params["ticker"])} <span id="status">{html.escape(status_label(job.status))}</span></h1>
            <p>{html.escape(job.params["analysis_date"])} · {html.escape(job.params["llm_provider"])}</p>
            {render_request_summary(job)}
            <p class="muted">缓存：{html.escape(DEFAULT_CONFIG["data_cache_dir"])} · 输出：{html.escape(DEFAULT_CONFIG["results_dir"])}</p>
          </section>
          {result_html or '<section class="result"><h2>运行中</h2><p class="muted">页面会自动刷新任务状态。</p></section>'}
        </main>
        <script>
          async function poll() {{
            const resp = await fetch('/jobs/{job.id}.json');
            const data = await resp.json();
            document.getElementById('status').textContent = data.status_label;
            if (data.status === 'running' || data.status === 'queued') {{
              setTimeout(poll, 2000);
            }} else if (!document.querySelector('.result pre')) {{
              location.reload();
            }}
          }}
          poll();
        </script>
        """,
    )


def render_job_row(job: WebJob) -> str:
    return (
        f'<a class="job" href="/jobs/{job.id}">'
        f'<strong>{html.escape(job.params["ticker"])}</strong>'
        f'<span>{html.escape(job.params["analysis_date"])}</span>'
        f'<em>{html.escape(status_label(job.status))}</em>'
        "</a>"
    )


def render_request_summary(job: WebJob) -> str:
    request_text = job.params.get("request_text")
    if not request_text:
        return ""
    return f'<p class="request">{html.escape(request_text)}</p>'


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172026; --muted:#66737f; --line:#d8dee4; --panel:#f7f9fb; --accent:#0f766e; --warn:#a14400; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #ffffff; }}
    .shell {{ width: min(1120px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0; }}
    h1 {{ margin: 0 0 18px; font-size: 34px; line-height: 1.1; font-weight: 720; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    .run, .history, .status, .result {{ border-top: 1px solid var(--line); padding: 24px 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }}
    label, legend {{ display: grid; gap: 6px; font-size: 13px; color: var(--muted); }}
    input, select, textarea {{ width: 100%; min-height: 38px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; font: inherit; color: var(--ink); background: white; }}
    textarea {{ resize: vertical; line-height: 1.45; }}
    .prompt {{ color: var(--ink); font-size: 14px; }}
    details {{ margin-top: 18px; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 650; }}
    details .grid {{ margin-top: 14px; }}
    fieldset {{ margin: 18px 0 12px; border: 1px solid var(--line); border-radius: 6px; padding: 12px; }}
    .checks {{ display: flex; flex-wrap: wrap; gap: 14px; }}
    .checks label, .inline {{ display: inline-flex; align-items: center; gap: 8px; color: var(--ink); }}
    .checks input, .inline input {{ width: auto; min-height: auto; }}
    button {{ margin-top: 14px; min-height: 40px; border: 0; border-radius: 6px; padding: 0 16px; background: var(--accent); color: white; font: inherit; font-weight: 650; cursor: pointer; }}
    .jobs {{ display: grid; gap: 8px; }}
    .job {{ display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: center; min-height: 42px; border-bottom: 1px solid var(--line); color: var(--ink); text-decoration: none; }}
    .job em, #status {{ color: var(--accent); font-style: normal; }}
    .muted {{ color: var(--muted); }}
    .request {{ border-left: 3px solid var(--accent); padding-left: 12px; color: var(--ink); }}
    pre {{ overflow: auto; white-space: pre-wrap; border: 1px solid var(--line); border-radius: 6px; padding: 16px; background: var(--panel); line-height: 1.45; }}
    .error pre {{ border-color: #e5a6a6; background: #fff7f7; }}
    a {{ color: var(--accent); }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
    @media (max-width: 560px) {{ .grid, .job {{ grid-template-columns: 1fr; }} .shell {{ width: min(100vw - 20px, 1120px); padding: 18px 0; }} }}
  </style>
</head>
<body>{body}</body>
</html>"""


def run_web_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = False) -> None:
    JOB_RUNNER.start()
    server = ThreadingHTTPServer((host, port), TradingAgentsWebHandler)
    url = f"http://{host}:{port}"
    print(f"TradingAgents Web 控制台运行在 {url}")
    print(f"缓存目录：{DEFAULT_CONFIG['data_cache_dir']}")
    print(f"输出目录：{DEFAULT_CONFIG['results_dir']}")
    if open_browser:
        webbrowser.open(url)
    server.serve_forever()
