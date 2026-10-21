import configparser
import json
import os

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


def save_history():
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


try:
    while True:
        prompt = input("请输入提示词: ")
        messages.append({"role": "user", "content": prompt})
        stream = client.chat.completions.create(
            model=config["llm"]["model"],
            messages=messages,
            stream=True,
        )
        reply = ""
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                reply += content
                print(content, end="", flush=True)
        print()
        messages.append({"role": "assistant", "content": reply})
        save_history()
except KeyboardInterrupt:
    save_history()
    print("\n已退出")
