import configparser
import json
import os
import platform
import subprocess

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")

client = OpenAI(
    base_url=config["llm"]["base_url"],
    api_key=config["llm"]["api_key"],
)

history_file = "history.json"
if os.path.exists(history_file):
    with open(history_file, encoding="utf-8") as f:
        messages = json.load(f)
else:
    messages = []

tools = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断输入的年份是否为闰年",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，例如 2024",
                    }
                },
                "required": ["year"],
            },
        },
    },
]


def save_history():
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def get_date_by_command():
    if platform.system() == "Windows":
        date_out = subprocess.run(
            ["cmd", "/c", "date", "/t"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        ).stdout.strip()
        time_out = subprocess.run(
            ["cmd", "/c", "time", "/t"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        ).stdout.strip()
        return f"{date_out} {time_out}".strip()
    result = subprocess.run(["date"], capture_output=True, text=True)
    return (result.stdout or result.stderr).strip()


def check_leap_year(year):
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return f"{year}年是闰年"
    return f"{year}年不是闰年"


def run_tool(name, arguments):
    args = json.loads(arguments) if arguments else {}
    if name == "getDate":
        return get_date_by_command()
    if name == "isLeapYear":
        return check_leap_year(int(args["year"]))
    return f"未知的工具: {name}"


def stream_reply():
    reply = ""
    tool_calls = []
    stream = client.chat.completions.create(
        model=config["llm"]["model"],
        messages=messages,
        tools=tools,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            reply += delta.content
            print(delta.content, end="", flush=True)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                while len(tool_calls) <= tc.index:
                    tool_calls.append({"id": "", "name": "", "arguments": ""})
                if tc.id:
                    tool_calls[tc.index]["id"] = tc.id
                if tc.function and tc.function.name:
                    tool_calls[tc.index]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    tool_calls[tc.index]["arguments"] += tc.function.arguments
    print()
    return reply, tool_calls


try:
    while True:
        prompt = input("请输入提示词: ")
        messages.append({"role": "user", "content": prompt})
        while True:
            reply, tool_calls = stream_reply()
            for i, tc in enumerate(tool_calls):
                if not tc["id"]:
                    tc["id"] = f"call_{i}"
            assistant_msg = {"role": "assistant", "content": reply or None}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"] or "{}",
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            if not tool_calls:
                break
            for tc in tool_calls:
                output = run_tool(tc["name"], tc["arguments"])
                print(f"[工具 {tc['name']}] {output}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": output,
                    }
                )
        save_history()
except KeyboardInterrupt:
    save_history()
    print("\n已退出")
