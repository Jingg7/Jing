import requests
import json

# ==========配置区==========
API_KEY = "YOUR_ANYTHINGLLM_API_KEY"
WORKSPACE_SLUG = "ac3a3899-e7dc-453e-8181-b161fbdb18bb"
BASE_URL = "http://127.0.0.1:3001/api/v1/workspace"
# ==========================

def stream_chat(message: str):
    url = f"{BASE_URL}/{WORKSPACE_SLUG}/stream-chat"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "message": message,
        "mode": "chat"
    }
    resp = requests.post(url, headers=headers, json=payload, stream=True)
    if resp.status_code != 200:
        print(f"\n调用失败：{resp.status_code} {resp.text}")
        return
    for line in resp.iter_lines():
        if not line:
            continue
        raw = line.decode("utf-8").strip()
        if raw.startswith("data: "):
            data_str = raw.removeprefix("data: ")
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                chunk = data.get("answer", "") # ✅ 这里改成 answer！！！
                print(chunk, end="", flush=True)
            except Exception as e:
                continue
    print()

if __name__ == "__main__":
    print("小助手已就绪，输入 exit 退出对话")
    while True:
        user_msg = input("\n你：").strip()
        if user_msg.lower() in ["exit", "quit", "退出"]:
            print("再见！")
            break
        print("助手：", end="", flush=True)
        stream_chat(user_msg)