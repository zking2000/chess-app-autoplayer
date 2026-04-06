# Chess.app Autoplayer

An offline chess automation tool for macOS's built-in `Chess.app`, powered by Stockfish and the macOS Accessibility API.

> **中文文档**: [README_zh.md](README_zh.md)

## How It Works

Chess.app exposes all 64 board squares as clickable buttons via the macOS Accessibility API. This tool:

1. Reads the live board state directly from those buttons (no image recognition)
2. Computes the best move using a local **Stockfish** engine
3. Executes the move by clicking the appropriate AX buttons
4. Detects the opponent's response by comparing the live AX state against the expected board state (no race conditions)
5. Saves a PGN game record and updates win/loss statistics

**Fresh game**: For a new game from the start position, run `play` without `--resume` so the internal state matches the board. **Mid-game**: use `play --resume` to read the live position from Chess.app and continue.

## Features

- Launch and focus `Chess.app` automatically
- Read all 64 squares accurately via Accessibility API
- Execute moves reliably — no 3D perspective issues
- Detect opponent moves without polling delays or race conditions
- Use local Stockfish for optimal move calculation
- `dry-run` mode: think only, no clicks
- `self-check` command: verify environment and permissions
- Save each game as a PGN file in `state/games/`
- Track cumulative win / loss / draw statistics in `state/stats.json`

## Requirements

- macOS
- Python 3.11+
- [Stockfish](https://stockfishchess.org/) (local install)
- `Chess.app` (bundled with macOS)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install Stockfish via Homebrew:

```bash
brew install stockfish
```

If `stockfish` is not on a standard path, set the environment variable:

```bash
export STOCKFISH_PATH="/opt/homebrew/bin/stockfish"
```

## macOS Permissions

Grant the following permissions before first use:

| Permission | Purpose | Path |
|---|---|---|
| **Accessibility** | Read and click board squares | System Settings → Privacy & Security → Accessibility |
| **Screen Recording** | Screenshot during `self-check` | System Settings → Privacy & Security → Screen Recording |

Restart your terminal after changing permissions.

## How to run (entry points)

**Recommended — wrapper script** (uses `.venv/bin/python` from the repo root; handy for automation allowlists):

```bash
chmod +x bin/openclaw-cheese   # once per clone
./bin/openclaw-cheese self-check
./bin/openclaw-cheese play --no-launch --think-time 2.0 --poll-interval 0.5 --move-confirmation-timeout 15
# Resume a game already on the board:
./bin/openclaw-cheese play --no-launch --resume --think-time 2.0
```

**Alternative — activate the venv**, then use `python -m`:

```bash
source .venv/bin/activate
python -m src.main self-check
python -m src.main play --no-launch
```

**One-liner without activating** (same as the wrapper):

```bash
.venv/bin/python -m src.main play --no-launch
```

## Quick Start

### 1. Self-check

```bash
./bin/openclaw-cheese self-check
# or: .venv/bin/python -m src.main self-check
```

### 2. Calibrate (first time only)

```bash
./bin/openclaw-cheese calibrate --bot-color white --board-bottom white
```

Calibration records the board region for template generation (`dry-run`). The `play` command uses the Accessibility API and does not require precise coordinates.

### 3. Dry run (think without playing)

```bash
./bin/openclaw-cheese dry-run --no-launch
```

### 4. Play a full game

Open a new game in `Chess.app` (`Cmd+N`), then:

```bash
./bin/openclaw-cheese play --no-launch
```

The bot will:
1. Read the current board state via Accessibility API
2. Calculate the best move with Stockfish
3. Click the board squares to execute the move
4. Wait for the opponent (AI) to respond
5. Loop until the game ends

Results are saved to `state/games/` and `state/stats.json`.

## Command Reference

| Command | Description |
|---|---|
| `self-check` | Verify permissions and environment |
| `calibrate` | Calibrate board region |
| `dry-run` | Print best move, no clicks |
| `play` | Run a full automated game |

### `play` options

| Flag | Default | Description |
|---|---|---|
| `--think-time` | `0.5` | Stockfish thinking time in seconds |
| `--poll-interval` | `0.5` | Opponent move polling interval in seconds |
| `--move-confirmation-timeout` | `10.0` | Timeout waiting for move confirmation |
| `--max-half-moves` | unlimited | Stop after N half-moves (testing) |
| `--no-launch` | false | Do not relaunch Chess.app |
| `--no-save` | false | Skip saving PGN and stats |
| `--resume` | false | Continue from the current Chess.app position (mid-game) |

## Project Structure

```
chess-app-autoplayer/
├── bin/
│   └── openclaw-cheese         # zsh wrapper → .venv/bin/python -m src.main
├── src/
│   ├── main.py                 # Entry point and game loop
│   ├── ax_board.py             # Accessibility API board reader
│   ├── actuator.py             # Accessibility API move executor
│   ├── engine.py               # Stockfish wrapper
│   ├── config.py               # Paths and configuration
│   ├── calibrate.py            # Board calibration (screenshot region)
│   ├── launcher.py             # App launch and permission checks
│   ├── board_capture.py        # Screenshot utility
│   └── position_recognizer.py  # Image-based recognition helpers
├── state/
│   └── calibration.json        # Board calibration data (gitignored)
├── assets/templates/           # Piece templates (generated, gitignored)
├── tests/                      # Unit tests
├── requirements.txt
└── README.md
```

## Technical Details

### Core: macOS Accessibility API

Chess.app exposes each square as a button with a description:

| Description | Meaning |
|---|---|
| `"White Pawn, e2"` | White pawn on e2 |
| `"e4"` | Empty square e4 |

This lets the bot:
- **Read state**: know exactly what piece is on each square without any image processing
- **Execute moves**: click buttons directly; Chess.app handles 3D rendering internally

### Opponent Move Detection

The bot compares the live Accessibility state against the internal `python-chess` board (which already has the bot's last move applied). The set of changed squares is matched against legal moves to identify the opponent's move. This approach:

- Has no race conditions (does not rely on timing)
- Handles castling, en passant, and promotion
- Is unaffected by the opponent's thinking speed

## Verified Opening (Ruy Lopez)

```
White (Bot): e2e4  →  Black (AI): e7e5
White (Bot): g1f3  →  Black (AI): b8c6
White (Bot): f1b5  →  Black (AI): g8f6
... continues until game over
```

## License

MIT
