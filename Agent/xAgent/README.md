# xAgent

鍩轰簬 `Agent/Practice02/chat_files.py` 閲嶆瀯锛氭妸**涓氬姟鏍稿績**涓?*鐣岄潰**鍒嗙锛屼究浜庝互鍚庢崲 Web / Desktop銆?
```text
Agent/xAgent
鈹溾攢鈹€ core/          # 涓氬姟鏍稿績锛堟棤 UI锛?鈹?  鈹溾攢鈹€ config.py  # 閰嶇疆涓?WORKSPACE_ROOT
鈹?  鈹溾攢鈹€ schemas.py # tools 瀹氫箟
鈹?  鈹溾攢鈹€ tools.py   # getDate / isLeapYear / 鏂囦欢宸ュ叿
鈹?  鈹斺攢鈹€ agent.py   # ToolAgent锛圠LM + tool loop锛?鈹溾攢鈹€ tui/           # Textual 缁堢鐣岄潰
鈹?  鈹斺攢鈹€ app.py
鈹溾攢鈹€ run.py         # 鍚姩鍏ュ彛
鈹溾攢鈹€ config.ini.example
鈹斺攢鈹€ requirements.txt
```

## 瀹夎

```powershell
cd D:\LLM-Course\Agent\xAgent
copy config.ini.example config.ini
# 濉啓 api_key锛涗篃鍙洿鎺ヤ娇鐢?Practice02\config.ini锛坈ore 浼氳嚜鍔ㄥ洖閫€鏌ユ壘锛?pip install -r requirements.txt
```

## 运行 TUI

双击本目录下的 **`启动 xAgent.bat`**（优先用 Windows Terminal 打开）。

或在终端中：

```powershell
cd D:\LLM-Course\Agent\xAgent
python run.py
```

- 杈撳叆妗嗗洖杞﹀彂閫? 
- `Ctrl+C` / `Ctrl+Q` 閫€鍑? 
- 宸ュ叿璋冪敤浼氭樉绀哄湪瀵硅瘽鏃ュ織涓? 

## 鍒嗗眰璇存槑

| 灞?| 鑱岃矗 |
|----|------|
| `core` | 閰嶇疆銆佸伐鍏峰疄鐜般€丄gent 寰幆锛涘彲琚?CLI/TUI/Web 澶嶇敤 |
| `tui` | 浠呰礋璐?Textual 灞曠ず涓庤緭鍏ワ紝閫氳繃 `ToolAgent(on_event=...)` 璁㈤槄浜嬩欢 |

鍘?`Practice02/chat_files.py` 浠嶄繚鐣欎綔浣滀笟瀵圭収锛屾湭鍒犻櫎銆?

## 界面

按效果图实现：左侧工具列表、对话流（你/助手/工具/结果）、底部输入；请在 **Windows Terminal / 系统 PowerShell** 运行，勿用 IDE 内置 Run 窗口。

### 界面语言

侧栏提供「语言」切换（**English / 中文**）。文案集中在 `tui/i18n.py`（含命令面板）；以后加语言只需在 `LOCALES` 增加条目。

### 主题

`Ctrl+P` → Theme 可切换整套配色（侧栏/对话区/输入框/标签色均跟随）。默认 `xagent-ink`，另有 `xagent-mist`；也可选 Textual 内置主题。自定义主题见 `tui/themes.py`。

当前主题会写入本目录 `ui.ini`，下次启动自动恢复。

