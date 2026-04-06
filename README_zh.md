# Chess.app Autoplayer（中文文档）

一个面向 macOS 自带 `Chess.app` 的离线国际象棋自动化工具，由 Stockfish 引擎和 macOS Accessibility API 驱动。

> **English docs**: [README.md](README.md)

## 工作原理

Chess.app 通过 macOS Accessibility API 将 64 个棋格暴露为可点击按钮。本工具：

1. 直接从这些按钮读取实时棋盘状态（无需图像识别）
2. 使用本地 **Stockfish** 引擎计算最优着法
3. 通过点击 Accessibility 按钮执行落子
4. 将实时 AX 状态与预期棋盘状态对比，检测对手着法（无竞态条件）
5. 保存 PGN 棋谱并更新胜负统计

**新局**：从初始局面开始时不要用 `--resume`，内部状态与棋盘一致。**半局续下**：使用 `play --resume`，从 Chess.app 当前盘面读取并继续。

## 功能

- 自动启动并聚焦 `Chess.app`
- 通过 Accessibility API 精确读取 64 个格子
- 无 3D 透视问题地可靠落子
- 无轮询延迟或竞态条件地检测对手着法
- 使用本地 Stockfish 计算最优着法
- `dry-run` 模式：只思考，不点击
- `self-check` 命令：验证环境和权限
- 将每局棋谱保存至 `state/games/`
- 在 `state/stats.json` 中追踪累计胜负平统计

## 环境要求

- macOS
- Python 3.11+
- [Stockfish](https://stockfishchess.org/)（本地安装）
- `Chess.app`（macOS 自带）

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

通过 Homebrew 安装 Stockfish：

```bash
brew install stockfish
```

若 `stockfish` 不在常见路径，通过环境变量指定：

```bash
export STOCKFISH_PATH="/opt/homebrew/bin/stockfish"
```

## macOS 权限

首次使用前授予以下权限：

| 权限 | 用途 | 路径 |
|---|---|---|
| **辅助功能** | 读取和点击棋格 | 系统设置 → 隐私与安全性 → 辅助功能 |
| **屏幕录制** | `self-check` 截图验证 | 系统设置 → 隐私与安全性 → 屏幕录制 |

修改权限后重启终端。

## 如何运行（入口）

**推荐：包装脚本**（固定使用仓库内 `.venv/bin/python`，便于自动化白名单配置）：

```bash
chmod +x bin/openclaw-cheese   # 每个克隆只需一次
./bin/openclaw-cheese self-check
./bin/openclaw-cheese play --no-launch --think-time 2.0 --poll-interval 0.5 --move-confirmation-timeout 15
# 续当前盘面上的半局：
./bin/openclaw-cheese play --no-launch --resume --think-time 2.0
```

**备选：激活虚拟环境后**用 `python -m`：

```bash
source .venv/bin/activate
python -m src.main self-check
python -m src.main play --no-launch
```

**不激活环境的一行命令**（与包装脚本等价）：

```bash
.venv/bin/python -m src.main play --no-launch
```

## 快速开始

### 1. 自检

```bash
./bin/openclaw-cheese self-check
# 或：.venv/bin/python -m src.main self-check
```

### 2. 校准（首次使用）

```bash
./bin/openclaw-cheese calibrate --bot-color white --board-bottom white
```

### 3. dry-run（只思考不走棋）

```bash
./bin/openclaw-cheese dry-run --no-launch
```

### 4. 开始自动对局

在 `Chess.app` 中新建一局（`Cmd+N`），然后：

```bash
./bin/openclaw-cheese play --no-launch
```

机器人将循环：读取局面 → 计算最优着法 → 落子 → 等待对手响应，直到对局结束。

## 命令参考

| 命令 | 说明 |
|---|---|
| `self-check` | 检查权限和运行环境 |
| `calibrate` | 校准棋盘区域 |
| `dry-run` | 只输出最佳着法 |
| `play` | 自动完整对局 |

### `play` 常用参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--think-time` | `0.5` | Stockfish 思考时间（秒） |
| `--poll-interval` | `0.5` | 对手着法轮询间隔（秒） |
| `--move-confirmation-timeout` | `10.0` | 落子确认超时（秒） |
| `--max-half-moves` | 无限制 | 最大半回合数（测试用） |
| `--no-launch` | false | 不重新启动 Chess.app |
| `--no-save` | false | 不保存 PGN 和统计 |
| `--resume` | false | 从 Chess.app 当前局面续局 |

## 项目结构

```
chess-app-autoplayer/
├── bin/
│   └── openclaw-cheese         # zsh 包装：.venv/bin/python -m src.main
├── src/
│   ├── main.py                 # 主入口和游戏主循环
│   ├── ax_board.py             # Accessibility API 棋盘读取
│   ├── actuator.py             # Accessibility API 落子执行
│   ├── engine.py               # Stockfish 封装
│   ├── config.py               # 路径和配置
│   ├── calibrate.py            # 棋盘校准
│   ├── launcher.py             # 启动和权限检查
│   ├── board_capture.py        # 截图工具
│   └── position_recognizer.py  # 图像识别辅助工具
├── state/                      # 运行时数据（已 gitignore）
├── assets/templates/           # 棋子模板（已 gitignore）
├── tests/                      # 单元测试
├── requirements.txt
└── README.md
```

## 技术说明

### 核心方案：macOS Accessibility API

Chess.app 通过 Accessibility API 将每个格子暴露为按钮，描述格式：

| 描述 | 含义 |
|---|---|
| `"白兵, e2"` | e2 上的白兵 |
| `"e4"` | e4 空格 |

中英文描述均受支持，`ax_board.py` 中的 `_PIECE_MAP` 已涵盖两种格式。

### 对手着法检测

将 Accessibility API 实时状态与内部 `python-chess` 棋盘（已包含机器人上一步）对比，变化的格子集合匹配合法着法的步法足迹，即可确定对手着法。该方案：

- 无竞态条件（不依赖时序）
- 正确处理王车易位、吃过路兵、升变
- 不受对手 AI 思考速度影响

## License

MIT
