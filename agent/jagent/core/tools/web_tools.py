from __future__ import annotations

import json
import socket
import subprocess
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

import trafilatura

from ..config import DEFAULT_SEARCH_ENDPOINT, DEFAULT_SEARCH_MAX_RESULTS
from .base import BaseTool

DEFAULT_TIMEOUT = 20.0
DEFAULT_CURL = "curl"
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_MAX_ERROR_CHARS = 500
QIANFAN_SEARCH_ENDPOINT = DEFAULT_SEARCH_ENDPOINT
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


class FetchWebTool(BaseTool):
    name = "fetchWeb"
    description = (
        "获取指定网页的主要内容并转换为 Markdown。"
        "会自动去除导航栏、广告、页脚等无关内容，保留标题、段落、列表、表格和链接。"
        "返回原始 URL 和提取后的 Markdown 正文。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要获取的网页 URL，必须以 http:// 或 https:// 开头",
            }
        },
        "required": ["url"],
    }

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        curl_executable: str = DEFAULT_CURL,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_error_chars: int = DEFAULT_MAX_ERROR_CHARS,
    ):
        self._timeout = timeout
        self._curl = curl_executable
        self._connect_timeout = connect_timeout
        self._max_error_chars = max_error_chars

    def run(self, arguments: dict[str, Any]) -> str:
        url = str(arguments["url"]).strip()
        invalid = self._validate_url(url)
        if invalid:
            return invalid

        command = self._build_command(url)
        try:
            response = subprocess.run(
                command,
                capture_output=True,
                timeout=self._timeout + 5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"网页访问超时（超过 {self._timeout:g} 秒）: {url}"
        except FileNotFoundError:
            return f"网页访问失败：未找到 curl 可执行文件（{self._curl}）"
        except OSError as exc:
            return f"网页访问失败: {exc}"

        if response.returncode != 0:
            detail = self._decode_output(response.stderr).strip()
            if len(detail) > self._max_error_chars:
                detail = detail[: self._max_error_chars] + "..."
            return f"网页访问失败（curl 退出码 {response.returncode}）: {detail or url}"

        if not response.stdout:
            return f"网页访问失败：未获取到 HTML 内容: {url}"

        try:
            markdown = trafilatura.extract(
                response.stdout,
                url=url,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_formatting=True,
                include_comments=False,
                favor_precision=True,
                deduplicate=True,
            )
        except Exception as exc:
            return f"HTML 解析失败: {exc}"

        if not markdown or not markdown.strip():
            return f"正文提取失败：无法从页面中提取有效正文: {url}"

        return f"原始 URL: {url}\n\n{markdown.strip()}\n"

    def _build_command(self, url: str) -> list[str]:
        return [
            self._curl,
            "--silent",
            "--show-error",
            "--location",
            "--compressed",
            "--fail",
            "--max-time",
            f"{self._timeout:g}",
            "--connect-timeout",
            f"{min(self._connect_timeout, self._timeout):g}",
            "--user-agent",
            USER_AGENT,
            "--header",
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "--url",
            url,
        ]

    @staticmethod
    def _validate_url(url: str) -> str | None:
        if not url:
            return "无效的 URL：URL 不能为空"
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return f"无效的 URL（仅支持 http:// 或 https://）: {url}"
        return None

    @staticmethod
    def _decode_output(data: bytes) -> str:
        if not data:
            return ""
        for encoding in ("utf-8", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")


class SearchWebTool(BaseTool):
    name = "searchWeb"
    description = (
        "使用百度千帆搜索 API 搜索互联网上的最新信息。"
        "接受搜索关键词或问题，返回搜索摘要、参考来源标题、URL 和日期。"
        "适用于查询时事、新闻、实时数据或模型知识之外的信息。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问题，不能为空",
            }
        },
        "required": ["query"],
    }

    def __init__(
        self,
        api_key: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        endpoint: str = QIANFAN_SEARCH_ENDPOINT,
        max_results: int = DEFAULT_SEARCH_MAX_RESULTS,
    ):
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._endpoint = endpoint
        self._max_results = max_results

    def run(self, arguments: dict[str, Any]) -> str:
        query = str(arguments["query"]).strip()
        if not query:
            return "搜索失败：query 不能为空"
        if not self._api_key:
            return (
                "搜索失败：缺少配置，请在 config.ini 的 [search] 小节设置 "
                "baidu_qianfan_api_key"
            )

        payload = {
            "messages": [{"role": "user", "content": query}],
            "search_source": "baidu_search_v2",
            "edition": "standard",
            "resource_type_filter": [
                {"type": "web", "top_k": self._max_results}
            ],
            "query_policy": {"enable_rewrite": True},
        }

        try:
            raw = self._post(payload)
        except urllib.error.HTTPError as exc:
            detail = self._api_error_detail(exc.read())
            if not detail:
                detail = str(exc.reason)
            return f"搜索 API 请求失败（HTTP {exc.code}）: {detail}"
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return f"搜索请求超时（超过 {self._timeout:g} 秒）"
            return f"搜索网络请求失败: {reason}"
        except (TimeoutError, socket.timeout):
            return f"搜索请求超时（超过 {self._timeout:g} 秒）"
        except OSError as exc:
            return f"搜索网络请求失败: {exc}"

        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return f"搜索 API 响应解析失败: {exc}"

        if not isinstance(response, dict):
            return "搜索 API 响应解析失败：返回内容不是 JSON 对象"

        code = response.get("code")
        if code not in (None, 0, "0", 200, "200"):
            message = response.get("message") or "未知错误"
            return f"搜索 API 返回错误（code {code}）: {message}"

        references = response.get("references")
        if not isinstance(references, list):
            return "搜索 API 返回错误：响应中缺少 references 列表"
        if not references:
            return f"未找到与“{query}”相关的搜索结果"

        formatted = self._format_references(query, references)
        if not formatted:
            return f"未找到与“{query}”相关的有效搜索结果"
        return formatted

    def _post(self, payload: dict[str, Any]) -> bytes:
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            return response.read()

    @staticmethod
    def _api_error_detail(raw: bytes) -> str:
        if not raw:
            return ""
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw.decode("utf-8", errors="replace")[:500].strip()
        if isinstance(data, dict):
            message = data.get("message")
            code = data.get("code")
            if message and code is not None:
                return f"{message}（code {code}）"
            if message:
                return str(message)
        return ""

    @staticmethod
    def _format_references(query: str, references: list[Any]) -> str:
        sections: list[str] = [f"搜索关键词: {query}", ""]
        index = 0
        for reference in references:
            if not isinstance(reference, dict):
                continue
            title = str(reference.get("title") or reference.get("web_anchor") or "").strip()
            url = str(reference.get("url") or "").strip()
            if not title and not url:
                continue
            index += 1
            sections.append(f"### {index}. {title or '(无标题)'}")
            if url:
                sections.append(f"- URL: {url}")
            website = str(reference.get("website") or "").strip()
            if website:
                sections.append(f"- 来源: {website}")
            date = str(reference.get("date") or "").strip()
            if date:
                sections.append(f"- 日期: {date}")
            snippet = str(
                reference.get("snippet") or reference.get("content") or ""
            ).strip()
            if snippet:
                sections.append(f"- 摘要: {snippet}")
            sections.append("")
        if index == 0:
            return ""
        return "\n".join(sections).strip()
