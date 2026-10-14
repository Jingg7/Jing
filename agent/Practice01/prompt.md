你是 Python 开发工程师，请在 Practice01 目录开发项目，严格按下面顺序迭代，代码尽量简单，禁止冗余、过度设计。
首先创建 chat.py、config.ini、requirements.txt，实现一次性对话、非 stream 模式。
config.ini：[llm]，base_url、api_key、model，用户手动修改。
chat.py 使用 configparser 读取配置，单次一问一答，一次性返回完整回答。
然后改造代码，开启 stream 流式输出，实现打字机逐字输出效果。
修改 chat.py，增加无限循环对话，按下 Ctrl+C 强制退出，除此之外不改动其他代码。
继续改造：增加聊天历史，每一轮循环请求 LLM 时，把全部历史对话传给大模型，保留上下文。
在项目根目录新建 .gitignore，添加一行 config.ini。
用户和 AI 回答之间用---三条减号分隔对话。
对接 AnythingLLM 的 OpenAI 兼容接口。