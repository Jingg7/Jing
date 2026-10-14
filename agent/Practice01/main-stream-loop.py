import configparser

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")

client = OpenAI(
    base_url=config["llm"]["base_url"],
    api_key=config["llm"]["api_key"],
)

messages = []
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
except KeyboardInterrupt:
    print("\n已退出")
