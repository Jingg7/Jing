from __future__ import annotations

import io
import json
import subprocess
import unittest
import urllib.error
from unittest.mock import patch

from core.tools.web_tools import FetchWebTool, SearchWebTool

HTML = b"""<!DOCTYPE html>
<html>
<head><title>Example Article</title></head>
<body>
<nav>Navigation menu</nav>
<article>
<h1>Main Title</h1>
<p>Hello <a href="https://example.com/docs">documentation</a>.</p>
<ul><li>First item</li><li>Second item</li></ul>
<table>
<tr><th>Name</th><th>Value</th></tr>
<tr><td>alpha</td><td>1</td></tr>
</table>
</article>
<footer>Copyright footer</footer>
</body>
</html>
"""


class FetchWebToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = FetchWebTool(timeout=10)
        self.url = "https://example.com/article"

    def test_schema(self) -> None:
        schema = self.tool.schema()["function"]
        self.assertEqual(schema["name"], "fetchWeb")
        self.assertEqual(schema["parameters"]["required"], ["url"])

    @patch("core.tools.web_tools.subprocess.run")
    def test_fetch_and_extract_markdown(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HTML, stderr=b""
        )

        output = self.tool.run({"url": self.url})

        self.assertIn(f"原始 URL: {self.url}", output)
        self.assertIn("# Main Title", output)
        self.assertIn("[documentation](https://example.com/docs)", output)
        self.assertIn("- First item", output)
        self.assertIn("| Name | Value |", output)
        self.assertNotIn("Navigation menu", output)
        self.assertNotIn("Copyright footer", output)

    @patch("core.tools.web_tools.subprocess.run")
    def test_curl_uses_argument_list_without_shell(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HTML, stderr=b""
        )

        self.tool.run({"url": self.url})

        args, kwargs = run.call_args
        command = args[0]
        self.assertIsInstance(command, list)
        self.assertIn("--url", command)
        self.assertEqual(command[command.index("--url") + 1], self.url)
        self.assertNotIn("shell", kwargs)
        self.assertFalse(kwargs.get("shell", False))

    @patch("core.tools.web_tools.subprocess.run")
    def test_curl_failure(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=22,
            stdout=b"",
            stderr=b"curl: (22) The requested URL returned error: 404",
        )

        output = self.tool.run({"url": self.url})

        self.assertIn("网页访问失败", output)
        self.assertIn("curl 退出码 22", output)
        self.assertIn("404", output)

    @patch("core.tools.web_tools.subprocess.run")
    def test_timeout(self, run) -> None:
        run.side_effect = subprocess.TimeoutExpired(cmd="curl", timeout=15)

        output = self.tool.run({"url": self.url})

        self.assertIn("网页访问超时", output)

    @patch("core.tools.web_tools.subprocess.run")
    def test_curl_missing(self, run) -> None:
        run.side_effect = FileNotFoundError()

        output = self.tool.run({"url": self.url})

        self.assertIn("未找到 curl", output)

    @patch("core.tools.web_tools.subprocess.run")
    def test_empty_response(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )

        output = self.tool.run({"url": self.url})

        self.assertIn("未获取到 HTML 内容", output)

    @patch("core.tools.web_tools.trafilatura.extract")
    @patch("core.tools.web_tools.subprocess.run")
    def test_no_main_content(self, run, extract) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HTML, stderr=b""
        )
        extract.return_value = None

        output = self.tool.run({"url": self.url})

        self.assertIn("正文提取失败", output)

    @patch("core.tools.web_tools.trafilatura.extract")
    @patch("core.tools.web_tools.subprocess.run")
    def test_html_parse_failure(self, run, extract) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HTML, stderr=b""
        )
        extract.side_effect = ValueError("bad html")

        output = self.tool.run({"url": self.url})

        self.assertIn("HTML 解析失败", output)
        self.assertIn("bad html", output)

    @patch("core.tools.web_tools.subprocess.run")
    def test_invalid_url_is_rejected(self, run) -> None:
        for url in ("", "example.com", "ftp://example.com", "file:///etc/passwd"):
            output = self.tool.run({"url": url})
            self.assertIn("无效的 URL", output)

        run.assert_not_called()


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


class SearchWebToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = SearchWebTool(api_key="test-key", timeout=15)

    def test_schema(self) -> None:
        schema = self.tool.schema()["function"]
        self.assertEqual(schema["name"], "searchWeb")
        self.assertEqual(schema["parameters"]["required"], ["query"])

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_search_results_are_formatted(self, urlopen) -> None:
        body = {
            "references": [
                {
                    "title": "最新新闻标题",
                    "url": "https://example.com/news",
                    "snippet": "这是一条搜索摘要。",
                    "date": "2026-10-26 10:00:00",
                    "website": "example.com",
                }
            ],
            "request_id": "req-1",
        }
        urlopen.return_value = FakeResponse(
            json.dumps(body, ensure_ascii=False).encode("utf-8")
        )

        output = self.tool.run({"query": "今日新闻"})

        self.assertIn("搜索关键词: 今日新闻", output)
        self.assertIn("最新新闻标题", output)
        self.assertIn("https://example.com/news", output)
        self.assertIn("这是一条搜索摘要。", output)
        self.assertIn("2026-10-26", output)

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["messages"][0]["content"], "今日新闻")
        self.assertEqual(payload["search_source"], "baidu_search_v2")

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_missing_api_key_is_reported(self, urlopen) -> None:
        output = SearchWebTool(api_key="").run({"query": "test"})

        self.assertIn("缺少配置", output)
        self.assertIn("baidu_qianfan_api_key", output)
        urlopen.assert_not_called()

    def test_empty_query_is_rejected(self) -> None:
        self.assertIn("query 不能为空", self.tool.run({"query": "   "}))

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_api_error_response(self, urlopen) -> None:
        body = {"code": 216003, "message": "Authentication error"}
        urlopen.return_value = FakeResponse(
            json.dumps(body, ensure_ascii=False).encode("utf-8")
        )

        output = self.tool.run({"query": "test"})

        self.assertIn("搜索 API 返回错误", output)
        self.assertIn("216003", output)
        self.assertIn("Authentication error", output)

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_http_error(self, urlopen) -> None:
        body = json.dumps({"code": 401, "message": "Unauthorized"}).encode("utf-8")
        error = urllib.error.HTTPError(
            "https://example.com", 401, "Unauthorized", None, io.BytesIO(body)
        )
        urlopen.side_effect = error

        output = self.tool.run({"query": "test"})

        self.assertIn("HTTP 401", output)
        self.assertIn("Unauthorized", output)

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_network_error(self, urlopen) -> None:
        urlopen.side_effect = urllib.error.URLError("connection refused")

        output = self.tool.run({"query": "test"})

        self.assertIn("网络请求失败", output)
        self.assertIn("connection refused", output)

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_timeout(self, urlopen) -> None:
        urlopen.side_effect = TimeoutError("timed out")

        output = self.tool.run({"query": "test"})

        self.assertIn("搜索请求超时", output)

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_invalid_json(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(b"not json")

        output = self.tool.run({"query": "test"})

        self.assertIn("响应解析失败", output)

    @patch("core.tools.web_tools.urllib.request.urlopen")
    def test_empty_results(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(b'{"references": []}')

        output = self.tool.run({"query": "test"})

        self.assertIn("未找到", output)


if __name__ == "__main__":
    unittest.main()
