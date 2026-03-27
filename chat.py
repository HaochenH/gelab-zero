#!/usr/bin/env python
import sys
sys.path.append(".")

from tools.ask_llm_v2 import ask_llm_anything

print("=" * 50)
print("  Gelab-Zero 交互式对话")
print("  模型: gelab-zero (本地 Ollama)")
print("  输入 'quit' 或 'exit' 退出")
print("=" * 50)
print()

messages = []

while True:
    try:
        user_input = input("你: ").strip()

        if user_input.lower() in ['quit', 'exit', 'q']:
            print("再见!")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        print("AI: ", end="", flush=True)

        response = ask_llm_anything(
            model_provider="local",
            model_name="gelab-zero",
            messages=messages,
            args={
                "max_tokens": 1024,
                "temperature": 0.7,
            }
        )

        print(response)
        print()

        messages.append({"role": "assistant", "content": response})

    except KeyboardInterrupt:
        print("\n再见!")
        break
    except Exception as e:
        print(f"错误: {e}")
        break