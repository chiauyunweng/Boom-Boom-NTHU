# Boom-Boom-NTHU

清大校園主題的 Pygame 視覺小說與解謎小遊戲，包含「上機考（找教室與摺痕紙條解謎）」、「成功湖釣魚」與「化學館煉金調配」三大章節。

---

## 安裝與執行教學

### 步驟一：複製專案

```bash
git clone https://github.com/chiauyunweng/Boom-Boom-NTHU.git
cd Boom-Boom-NTHU
```

### 步驟二：使用 `uv` 安裝環境與啟動遊戲（推薦）

1. **安裝 `uv`**（若尚未安裝）：
   - **macOS / Linux**：
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
   - **Windows (PowerShell)**：
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```

2. **同步虛擬環境與套件**：
   ```bash
   uv sync
   ```

3. **啟動遊戲**：
   ```bash
   uv run main.py
   ```

---

### 備用方式：使用傳統 `pip` 安裝

若不使用 `uv`，也可直接使用傳統 `pip` 搭配 `requirements.txt` 安裝依賴並啟動：

1. **安裝套件**：
   ```bash
   pip install -r requirements.txt
   ```

2. **啟動遊戲**：
   ```bash
   python main.py
   ```
