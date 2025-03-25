import argparse
import os
import datetime
import sqlite3
import csv
from rich.console import Console
from rich.table import Table


DB_NAME = "board_vault.db"


def init_db(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Create games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    # Create game_flow table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            played_at DATETIME NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    """)

    conn.commit()
    conn.close()


def list_games(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM games")
        games = cursor.fetchall()

        if len(games) == 0:
            print("🎲 No games found in your game collection.")
        else:
            print("🎲 Your game collection:")
            for game in games:
                print(f" {game[0]} - {game[1]}")

    except sqlite3.Error as e:
        print(f"⚠️ An error occurred: {e}")
    finally:
        conn.close()


def normalize_to_stars(value, max_value, max_stars=10):
    """Normalize values to stars based on max_value."""
    if max_value == 0:  # Avoid division by zero
        return "-"
    stars = round((value / max_value) * max_stars)
    return "⭐" * stars if stars > 0 else "-"


def show_stats(db_name, sort_by="game"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT 
            g.name, 
            COUNT(gf.id) AS total_played, 
            SUM(CASE 
                WHEN played_at >= datetime('now', '-3 months') THEN 1 
                ELSE 0 
            END) AS last_3_months_played, 
            MAX(gf.played_at) AS last_played
        FROM game_flow AS gf
        LEFT JOIN games AS g ON gf.game_id = g.id
        GROUP BY game_id
        ORDER BY 
            {'g.name' if sort_by == 'game' else ''}
            {'total_played DESC' if sort_by == 'total' else ''}
            {'last_played DESC' if sort_by == 'last-played' else ''};
    ''')

    stats = cursor.fetchall()
    conn.close()

    if not stats:
        print("🎲 No games have been played yet.")
        return

    # Get max values for normalization
    max_total = max((row[1] for row in stats), default=0)
    max_recent = max((row[2] for row in stats), default=0)

    # Create a pretty table
    console = Console()
    table = Table(title="🎲 Board Game Stats")

    table.add_column("Game", style="cyan", no_wrap=True)
    table.add_column("Total Played", style="green")
    table.add_column("Last 3 Months", style="yellow")
    table.add_column("Last Played", style="magenta")

    for row in stats:
        game_name = row[0]
        total_played = normalize_to_stars(row[1], max_total)
        recent_played = normalize_to_stars(row[2], max_recent)
        last_played = row[3].replace("T", " ") or "Never" # Show date only
        table.add_row(game_name, total_played, recent_played, last_played)

    console.print(table)


def add_new_game(game_name, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    try:
        cursor.execute("INSERT INTO games (name) VALUES (?)", (game_name,))
        conn.commit()
        print(f"✅ Game '{game_name}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"⚠️ Game '{game_name}' already exists.")
    finally:
        conn.close()


def play_game(game_name, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM games WHERE name = ?", (game_name,))
        game_id = cursor.fetchone()
        if game_id is None:
            print(f"⚠️ Game '{game_name}' not found.")
            return

        cursor.execute(
            "INSERT INTO game_flow (game_id, played_at) VALUES (?, ?)",
            (game_id[0], datetime.datetime.now().replace(microsecond=0).isoformat(sep=" "))
        )
        conn.commit()
        print(f"✅ Game '{game_name}' logged successfully.")
    except sqlite3.Error as e:
        print(f"⚠️ An error occurred: {e}")
    finally:
        conn.close()


def delete_game(game_name, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM games WHERE name = ?", (game_name,))
        game_id = cursor.fetchone()
        if game_id is None:
            print(f"⚠️ Game '{game_name}' not found.")
            return

        confirm = input(
            f"⚠️ Are you sure you want to delete '{game_name}' and all its play history? (y/yes/<Enter>): "
        ).lower()
        if confirm not in ("y", "yes", ""):
            print("❌ Deletion cancelled.")
            return

        cursor.execute("DELETE FROM games WHERE id = ?", (game_id[0],))
        cursor.execute("DELETE FROM game_flow WHERE game_id = ?", (game_id[0],))
        conn.commit()
        print(f"✅ Game '{game_name}' deleted successfully.")
    except sqlite3.Error as e:
        print(f"⚠️ An error occurred: {e}")
    finally:
        conn.close()


def import_games(csv_file, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header if present

            for row in reader:
                game_name, played_at = row[0], row[1]

                try:
                    played_at = datetime.datetime.strptime(played_at, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    print(f"⚠️ Skipping invalid date format for '{game_name}': {played_at}")
                    continue  # Skip this row if date is invalid

                cursor.execute("SELECT id FROM games WHERE name = ?", (game_name,))
                game_id = cursor.fetchone()

                if game_id is None:
                    # Insert new game
                    cursor.execute("INSERT INTO games (name) VALUES (?)", (game_name,))
                    game_id = cursor.lastrowid
                else:
                    game_id = game_id[0] 

                # Check if this play session already exists
                cursor.execute(
                    "SELECT COUNT(*) FROM game_flow WHERE game_id = ? AND played_at = ?",
                    (game_id, played_at)
                )
                existing_session = cursor.fetchone()[0]

                if existing_session == 0:
                    cursor.execute(
                        "INSERT INTO game_flow (game_id, played_at) VALUES (?, ?)",
                        (game_id, played_at.isoformat()),
                    )
                else:
                    print(f"⚠️ Skipping duplicate session for '{game_name}' at {played_at}")

        conn.commit()
        print(f"✅ Games imported successfully from '{csv_file}'.")
    except sqlite3.Error as e:
        print(f"⚠️ An error occurred: {e}")
    finally:
        conn.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="🎲 Board Vault: Track your board game plays"
    )
    parser.add_argument(
        "--add-new-game", type=str, help="Add a new game to your collection"
    )
    parser.add_argument("--play-game", type=str, help="Log a game play")
    parser.add_argument(
        "--list-games", action="store_true", help="List all games in your collection"
    )
    parser.add_argument(
        "--delete-game", type=str, help="Delete a game from your collection"
    )
    parser.add_argument(
        "--import-games",
        type=str,
        help="Import games from a CSV file to your collection(CSV format: 'name,played_at')"
    )
    parser.add_argument(
        "--stats", nargs="?", const="game", choices=["game", "total", "last-played"], help="Show game play statistics sorted by (game, total, last-played)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    init_db(DB_NAME)
    print("✅ Database initialized.")

    if args.list_games:
        list_games(DB_NAME)

    if args.add_new_game:
        add_new_game(args.add_new_game, DB_NAME)

    if args.play_game:
        play_game(args.play_game, DB_NAME)

    if args.delete_game:
        delete_game(args.delete_game, DB_NAME)

    if args.import_games:   
        import_games(args.import_games, DB_NAME)

    if args.stats:
        show_stats(DB_NAME, args.stats)

if __name__ == "__main__":
    main()
