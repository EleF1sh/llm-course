# LLM-Course 作业仓库

按课程要求整理的目录：

```text
D:\LLM-Course
├── PetHospitalServer      # 宠物医院后端（exe + data）
├── PetHospitalMCP         # 任务1：list_pets MCP
├── AnythingLLMMCP         # 任务2：AnythingLLM MCP
├── AnythingLLMWebPage     # 任务3：上传网页
├── Playground             # MCP 配置 mcp.json
└── Agent\Practice01       # 第4周对话练习
```

## 快速启动

### 1) 宠物医院后端
```powershell
cd D:\LLM-Course\PetHospitalServer
.\pethospital.exe
```

### 2) PetHospitalMCP
```powershell
cd D:\LLM-Course\PetHospitalMCP
python -m pip install -e ".[dev]"
python -m pet_hospital_mcp
```

### 3) AnythingLLMMCP
```powershell
cd D:\LLM-Course\AnythingLLMMCP
copy .env.example .env
# 编辑 .env 填入 ANYTHINGLLM_API_KEY
python -m pip install -e .
python -m anythingllm_mcp
```

### 4) 上传页
浏览器打开 `AnythingLLMWebPage\index.html`

### 5) Practice01
见 `Agent\Practice01\README.md`
