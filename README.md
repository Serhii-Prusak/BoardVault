# Board Vault

Board Vault is a Python-based CLI tool to manage your board game collection, track play history, and generate game statistics.

## Prerequisites

Before running the script, ensure you have the following installed:
- Python 3.8+
- SQLite3

## Features
- Add a new game to your collection.
- Delete an existing game.
- Log a game session when you play a game.
- List all games in your collection.
- Generate statistics on total plays and recent plays (last 3 months).
- Import game data from a CSV file.

## Installation

1. Clone the repository:
   ```sh
   git clone https://github.com/Serhii-Prusak/BoardVault.git
   cd board-vault
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv .venv
   source .venv/bin/activate 
   ```

3. Install required dependencies:
   ```sh
   pip install -r requirements.txt
   ```

## Usage

Run the script with the following arguments:

```sh
python board-vault.py --stat [--sort-by {game, total, last-played}]
python board-vault.py --add-new-game "Game Name"
python board-vault.py --delete-game "Game Name"
python board-vault.py --play-game "Game Name"
python board-vault.py --import-csv games.csv
```

### Arguments
- `--stat` - Display statistics of games played (sortable by `game`, `total` plays, or `last-played`).
- `--add-new-game` - Add a new game to the collection.
- `--delete-game` - Remove a game from the collection (confirmation required).
- `--play-game` - Log a play session for a game.
- `--import-csv` - Import games and play data from a CSV file.

## Example Usage
```sh
python board-vault.py --add-new-game "Catan"
python board-vault.py --play-game "Catan"
python board-vault.py --stat --sort-by total
python board-vault.py --delete-game "Catan"
```

## Database
The script uses an SQLite database to store:
- `games` table: Game names and IDs.
- `game_flow` table: Play history with timestamps.

---
Enjoy tracking your board games with Board Vault! 🎲
