import argparse
import datetime
import sqlite3
import csv
from rich.console import Console
from rich.table import Table


DB_NAME = "board_vault.db"
RECENT_MONTHS = 12


def init_db(db_name):
    """Create required tables if they do not exist."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Create sizes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sizes (
            size TEXT PRIMARY KEY,
            time REAL NOT NULL
        )
    """)

    # Create games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            size TEXT,
            FOREIGN KEY (size) REFERENCES sizes(size)
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
    """Print the list of games in the collection."""
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


def get_games(db_name):
    """Return a list of (id, name) for all games."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM games ORDER BY name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"⚠️ An error occurred: {e}")
        return []
    finally:
        conn.close()


def select_game_name(db_name):
    """Prompt the user to select a game name from the collection."""
    games = get_games(db_name)
    if not games:
        print("🎲 No games found in your game collection.")
        return None

    print("🎲 Choose a game to log:")
    for idx, (_, name) in enumerate(games, start=1):
        print(f" {idx}. {name}")

    choice = input("Enter number (or press Enter to cancel): ").strip()
    if not choice:
        print("❌ Selection cancelled.")
        return None
    if not choice.isdigit():
        print("⚠️ Invalid selection.")
        return None

    index = int(choice)
    if not 1 <= index <= len(games):
        print("⚠️ Invalid selection.")
        return None

    return games[index - 1][1]


def normalize_to_stars(value, max_value, max_stars=10):
    """Normalize values to stars based on max_value."""
    if max_value == 0:  # Avoid division by zero
        return "-"
    stars = round((value / max_value) * max_stars)
    return "⭐" * stars if stars > 0 else "-"


def show_stats(db_name, sort_by="game", recent_months=RECENT_MONTHS):
    """Render game play statistics sorted by the chosen field."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    cursor.execute(f'''
    SELECT 
        g.name,
        COALESCE(g.size, '-') AS size,
        COUNT(gf.id) AS total_played, 
        COALESCE(SUM(CASE 
            WHEN gf.played_at >= datetime('now', '-{recent_months} months') THEN 1 
            ELSE 0 
        END), 0) AS last_12_months_played, 
        COALESCE(MAX(gf.played_at), '') AS last_played
    FROM games AS g
    LEFT JOIN game_flow AS gf ON gf.game_id = g.id
    GROUP BY g.id
    ORDER BY 
        {"g.name" if sort_by == "game" else ""}
        {"CASE size WHEN 'XL' THEN 1 WHEN 'L' THEN 2 WHEN 'M' THEN 3 WHEN 'S' THEN 4 ELSE 5 END" if sort_by == "size" else ""}
        {"total_played DESC" if sort_by == "total" else ""}
        {"last_played DESC" if sort_by == "last-played" else ""};
    ''')

    stats = cursor.fetchall()
    conn.close()

    if not stats:
        print("🎲 No games have been played yet.")
        return

    # Get max values for normalization
    max_total = max((row[2] for row in stats), default=0)
    max_recent = max((row[3] for row in stats), default=0)

    # Create a pretty table
    console = Console()
    table = Table(title="🎲 Board Game Stats")

    table.add_column("Game", style="cyan", no_wrap=True)
    table.add_column("Size", style="blue")
    table.add_column("Total Played", style="green")
    table.add_column(f"Last {recent_months} Months", style="yellow")
    table.add_column("Last Played", style="magenta")

    for row in stats:
        game_name = row[0]
        game_size = row[1]
        total_played = normalize_to_stars(row[2], max_total)
        recent_played = normalize_to_stars(row[3], max_recent)
        last_played = row[4].replace("T", " ") or "Never" # Show date only
        table.add_row(game_name, game_size, total_played, recent_played, last_played)

    console.print(table)


def get_rank_recommendations(db_name, months=None):
    """Return recommendations based on rank vs plays, optionally filtered by months."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    if months is None:
        cursor.execute("""
            SELECT 
                g.name,
                g.rank,
                COUNT(gf.id) AS total_played,
                s.time as size_time
            FROM games AS g
            LEFT JOIN game_flow AS gf ON g.id = gf.game_id
            LEFT JOIN sizes AS s ON g.size = s.size
            GROUP BY g.id
        """)
    else:
        cursor.execute("""
            SELECT 
                g.name,
                g.rank,
                COUNT(gf.id) AS recent_played,
                s.time as size_time
            FROM games AS g
            LEFT JOIN game_flow AS gf 
                ON g.id = gf.game_id AND gf.played_at >= datetime('now', ?)
            LEFT JOIN sizes AS s ON g.size = s.size
            GROUP BY g.id
        """, (f"-{months} months",))
    data = cursor.fetchall()
    conn.close()

    if not data:
        return [], []

    max_score = max([row[2] * row[3] for row in data]) or 1
    results = []
    for name, rank, played, size_time in data:
        if rank == 0:
            continue
        normalized = (played * size_time / max_score) * 10
        score = normalized - rank
        results.append((name, rank, played, normalized, round(score, 2)))

    sorted_by_score = sorted(results, key=lambda x: x[4])
    count = max(1, len(results) // 10)
    underplayed = sorted_by_score[:count]
    overplayed = [row for row in sorted_by_score if row[2] > 0][-count:]
    return underplayed, overplayed


def get_neglected_games(db_name):
    """Return never-played and rarely-played ranked games."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Games never played
    cursor.execute("""
        SELECT name FROM games
        WHERE id NOT IN (SELECT DISTINCT game_id FROM game_flow)
        AND rank > 0
    """)
    never_played = [row[0] for row in cursor.fetchall()]

    # Rarely played: get oldest last_played
    cursor.execute("""
        SELECT g.name, MAX(gf.played_at) as last_played
        FROM game_flow gf
        JOIN games g ON g.id = gf.game_id
        WHERE g.rank > 0
        GROUP BY gf.game_id
        ORDER BY last_played ASC
    """)
    data = cursor.fetchall()
    count = max(1, len(data) // 10)
    rarely_played = data[:count]

    conn.close()
    return never_played, rarely_played


def show_recommendations(db_name, recent=False, neglected=False):
    """Display recommendation tables based on rank, recency, and neglect."""
    console = Console()
    console.print("[bold magenta]🎯 Game Recommendations[/bold magenta]\n")

    if not recent:
        under, over = get_rank_recommendations(db_name)

        # Underplayed favorites
        table = Table(title="📈 Games you love but rarely play. Consider to play or decrease the rank.", show_lines=True)
        table.add_column("Game", style="cyan", no_wrap=True)
        table.add_column("Rank", justify="center")
        table.add_column("Played", justify="center")
        table.add_column("Score", justify="right")

        for name, rank, played, norm, score in under:
            table.add_row(name, str(rank), str(played), f"{score:.2f}")

        console.print(table)

        # Overplayed games
        table2 = Table(title="📛 Games you might be overplaying. Consider to increase the rank.", show_lines=True)
        table2.add_column("Game", style="cyan", no_wrap=True)
        table2.add_column("Rank", justify="center")
        table2.add_column("Played", justify="center")
        table2.add_column("Score", justify="right")

        for name, rank, played, norm, score in over:
            table2.add_row(name, str(rank), str(played), f"{score:.2f}")

        console.print(table2)

    if recent:
        console.print(f"\n[bold yellow]🕒 Based on Last {RECENT_MONTHS} Months[/bold yellow]\n")
        under, over = get_rank_recommendations(db_name, months=RECENT_MONTHS)

        recent_table = Table(
            title="📈 Recent favorites you're ignoring. Consider to play or decrease the rank.",
            show_lines=True,
        )
        recent_table.add_column("Game", style="green")
        recent_table.add_column("Rank", justify="center")
        recent_table.add_column(f"{RECENT_MONTHS}-Month Plays", justify="center")
        recent_table.add_column("Score", justify="right")

        for name, rank, played, norm, score in under:
            recent_table.add_row(name, str(rank), str(played), f"{score:.2f}")

        console.print(recent_table)

        recent_table2 = Table(title="📛 Recently overplayed. Consider to increase the rank.", show_lines=True)
        recent_table2.add_column("Game", style="green")
        recent_table2.add_column("Rank", justify="center")
        recent_table2.add_column(f"{RECENT_MONTHS}-Month Plays", justify="center")
        recent_table2.add_column("Score", justify="right")

        for name, rank, played, norm, score in over[::-1]:
            recent_table2.add_row(name, str(rank), str(played), f"{score:.2f}")

        console.print(recent_table2)

    if neglected:
        never, rare = get_neglected_games(db_name)

        if never:
            table_never = Table(title="📉 Never Played Games", show_lines=True)
            table_never.add_column("Game", style="red")
            for name in never:
                table_never.add_row(name)
            console.print(table_never)

        if rare:
            table_rare = Table(title="⏳ Long Time Since Played", show_lines=True)
            table_rare.add_column("Game", style="blue")
            table_rare.add_column("Last Played", justify="center")

            for name, last in rare:
                last_clean = last.replace("T", " ") if last else "N/A"
                table_rare.add_row(name, last_clean)

            console.print(table_rare)


def add_new_game(game_name, db_name):
    """Insert a new game into the collection."""
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
    """Log a play session for an existing game."""
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
    """Delete a game and its play history after confirmation."""
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
    """Import games and play sessions from a CSV file."""
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
    """Parse CLI arguments for the Board Vault app."""
    parser = argparse.ArgumentParser(
        description="🎲 Board Vault: Track your board game plays"
    )
    parser.add_argument(
        "--add-new-game", type=str, help="Add a new game to your collection"
    )
    parser.add_argument(
        "--play-game",
        nargs="?",
        const="__prompt__",
        type=str,
        help="Log a game play (omit value to choose from list)",
    )
    parser.add_argument(
        "--list-games", action="store_true", help="List all games in your collection"
    )
    parser.add_argument(
        "--delete-game",
        nargs="?",
        const="__prompt__",
        type=str,
        help="Delete a game from your collection (omit value to choose from list)",
    )
    parser.add_argument(
        "--import-games",
        type=str,
        help="Import games from a CSV file to your collection(CSV format: 'name,played_at')"
    )
    parser.add_argument(
        "--stats",
        nargs="?",
        const="game",
        choices=["game", "size", "total", "last-played"],
        help="Show game play statistics sorted by (game, size, total, last-played)",
    )
    parser.add_argument(
        "--recommend", action="store_true", help="Show game recommendations"
    )
    parser.add_argument(
        "--recent", action="store_true", help="Use recent plays for recommendation"
    )
    parser.add_argument(
        "--neglected", action="store_true", help="Show neglected/never-played games"
    )

    return parser.parse_args()


def main():
    """Entry point for the CLI application."""
    args = parse_args()

    init_db(DB_NAME)
    print("✅ Database initialized.")

    if args.list_games:
        list_games(DB_NAME)

    if args.add_new_game:
        add_new_game(args.add_new_game, DB_NAME)

    if args.play_game:
        if args.play_game == "__prompt__":
            selected = select_game_name(DB_NAME)
            if selected:
                play_game(selected, DB_NAME)
        else:
            play_game(args.play_game, DB_NAME)

    if args.delete_game:
        if args.delete_game == "__prompt__":
            selected = select_game_name(DB_NAME)
            if selected:
                delete_game(selected, DB_NAME)
        else:
            delete_game(args.delete_game, DB_NAME)

    if args.import_games:   
        import_games(args.import_games, DB_NAME)

    if args.stats:
        show_stats(DB_NAME, args.stats)

    if args.recommend:
        show_recommendations(DB_NAME, args.recent, args.neglected)

    if not any(vars(args).values()):
        print("⚠️ No command provided. Use --help for usage information.")

if __name__ == "__main__":
    main()
