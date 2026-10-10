# Practice01 — Python LLM 对话练习

功能：

1. 从 `config.ini` 读取 LLM 配置  
2. 支持非流式 / 流式（打字机）输出  
3. 无限循环对话，`Ctrl+C` 退出  
4. 每轮带上完整历史 messages  

## 使用

```powershell
cd D:\LLM-Course\Agent\Practice01
copy config.ini.example config.ini
# 编辑 config.ini 填入 base_url / api_key / model
python -m pip install -r requirements.txt

# 流式（默认）
python chat.py

# 非流式
$env:PRACTICE_STREAM="0"
python chat.py
```

`config.ini` 已被根目录 `.gitignore` 忽略，请勿提交密钥。
