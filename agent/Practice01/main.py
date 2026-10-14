import configparser

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")

client = OpenAI(
    base_url=config["llm"]["base_url"],
    api_key=config["llm"]["api_key"],
)

prompt = input("请输入你的问题: ")
response = client.chat.completions.create(
    model=config["llm"]["model"],
    messages=[{"role": "user", "content": prompt}],
)
print(response.choices[0].message.content)
