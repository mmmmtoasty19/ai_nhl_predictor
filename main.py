import sqlite3
from datetime import datetime, timedelta

import requests
from rich.console import Console

# Global
console = Console()


class NHLPredictorAgent:
    """
    AI Agent for NHL game predictions and data collection
    """

    def __init__(self, db_path="data/nhl_data.db"):
        """
        TASK: Initialize the agent

        STEPS:
        1. Store database path
        2. Initialize database connection
        3. Create tables if they don't exist
        4. Set up any API base URLs
        5. Initialize empty cache for team data
        """
        self.db_path = db_path
        self.db_connection = None
        self.nhl_api_base = "https://api-web.nhle.com"
        self.teams_cache = {}  # Store team data in memory

        # Call initialization methods
        self._connect_database()
        self._initialize_tables()

    def _connect_database(self):
        """
        TASK: Connect to SQLite database
        (underscore prefix = private method)
        """
        self.db_connection = sqlite3.connect(self.db_path)
        self.db_connection.row_factory = sqlite3.Row
        print(f"Connected to database: {self.db_path}")

    def _initialize_tables(self):
        """
        TASK: Create database tables if not exist

        """
        cur = self.db_connection.cursor()

        # Teams Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                team_id INTEGER PRIMARY KEY,
                team_name TEXT NOT NULL,
                abbreviation TEXT NOT NULL,
                conference TEXT,
                division TEXT
            )
        """)

        # Games Tables - Stores info about past and future games
        cur.execute("""
            CREATE TABLE IF NOT EXISTS games(
                game_id INTEGER PRIMARY KEY,
                game_date TEXT NOT NULL,
                home_team_id INTEGER NOT NULL,
                away_team_id INTEGER NOT NULL,
                home_score INTEGER,
                away_score INTEGER,
                game_state TEXT DEFAULT 'scheduled',
                winner_id INTEGER,
                FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
                FOREIGN KEY (away_team_id) REFERENCES teams(team_id),
                FOREIGN KEY (winner_id) REFERENCES teams(team_id)
            )
        """)

        # Predictions table - stores prediction and tracks accuracy
        cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                predicted_winner_id INTEGER NOT NULL,
                confidence REAL,
                prediction_date TEXT NOT NULL,
                correct INTEGER,
                FOREIGN KEY (game_id) REFERENCES games(game_id),
                FOREIGN KEY (predicted_winner_id) REFERENCES teams(team_id)
            )
        """)

        self.db_connection.commit()
        print("Database tables initialized")

    # ===================
    # TOOL METHODS
    # ===================
    # TODO Update this to pull in type of win
    def fetch_games_by_date(self, date: str | None = None):
        """
        Get games scheduled for a specific date

        Args:
            date (str, optional): Date in 'YYYY-MM-DD' format.
                                If None, defaults to today.

        Returns:
            int: Number of games stored
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        url = f"{self.nhl_api_base}/v1/schedule/{date}"
        console.print(f"URL: {url}")

        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                console.print(
                    f"[red]Error: API returned status code {response.status_code}[/red]"
                )
                return None

            data = response.json()
        except requests.exceptions.Timeout:
            console.print("[red]Error: request timed out[/red]")
            return None
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error making request: {e}[/red]")

        todays_data = [
            day for day in data.get("gameWeek", []) if day.get("date") == date
        ]

        if not todays_data:
            console.print("[yellow]No games scheduled for today[/yellow]")
            return 0

        todays_games = todays_data[0].get("games", [])
        # TODO change this to only show if pulling todays games not historical
        console.print(f"Found {len(todays_games)} games today!")

        cur = self.db_connection.cursor()
        games_stored = 0

        for game in todays_games:
            try:
                game_type = game.get("gameType")

                # Skip Preseason games
                if game_type == 1:
                    continue

                # Extract game info
                game_id = game.get("id")
                game_date = date

                # Extract HOME team
                home_team = game.get("homeTeam", {})
                home_id = home_team.get("id")
                home_abbrev = home_team.get("abbrev")
                home_place = home_team.get("placeName", {}).get("default", "Unknown")
                home_common = home_team.get("commonName", {}).get("default", "")
                home_name = f"{home_place} {home_common}".strip()

                # Extract AWAY team
                away_team = game.get("awayTeam", {})
                away_id = away_team.get("id")
                away_abbrev = away_team.get("abbrev")
                away_place = away_team.get("placeName", {}).get("default", "Unknown")
                away_common = away_team.get("commonName", {}).get("default", "")
                away_name = f"{away_place} {away_common}".strip()

                # INSERT OR IGNORE teams (creates if doesn't exist, skips if exists)
                cur.execute(
                    """
                    INSERT OR IGNORE INTO teams 
                    (team_id, team_name, abbreviation)
                    VALUES (?, ?, ?)
                """,
                    (home_id, home_name, home_abbrev),
                )

                cur.execute(
                    """
                    INSERT OR IGNORE INTO teams 
                    (team_id, team_name, abbreviation)
                    VALUES (?, ?, ?)
                """,
                    (away_id, away_name, away_abbrev),
                )

                # Game state
                # Game state
                game_state_raw = game.get("gameState", "FUT")
                if game_state_raw == "FUT":
                    game_state = "scheduled"
                elif game_state_raw == "LIVE":
                    game_state = "live"
                elif game_state_raw in ["FINAL", "OFF"]:
                    game_state = "final"
                else:
                    game_state = "scheduled"

                # Scores (None for scheduled games)
                home_score = home_team.get("score")
                away_score = away_team.get("score")

                # Determine winner
                winner_id = None
                if (
                    game_state == "final"
                    and home_score is not None
                    and away_score is not None
                ):
                    winner_id = home_id if home_score > away_score else away_id

                # Store game
                cur.execute(
                    """
                    INSERT OR REPLACE INTO games
                    (game_id, game_date, home_team_id, away_team_id, 
                    home_score, away_score, game_state, winner_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        game_id,
                        game_date,
                        home_id,
                        away_id,
                        home_score,
                        away_score,
                        game_state,
                        winner_id,
                    ),
                )

                games_stored += 1
                console.print(f"  {away_abbrev} @ {home_abbrev} - {game_state}")
            except Exception as e:
                console.print(f"[red]Warning: Could not process game: {e}[/red]")
                continue

        self.db_connection.commit()
        console.print(f"[green]Successfully stored {games_stored} games[/green]")

        return games_stored

    def enrich_teams_with_standings(self):
        """
        Enrich existing team records with conference, division, and current stats
        Run this AFTER fetch_todays_games() or any game fetching

        Returns:
            dict: teams_cache with updated info
        """
        console.print("[green]Enriching teams with standings data...[/green]")

        url = f"{self.nhl_api_base}/v1/standings/now"
        console.print(f"URL: {url}")

        # Make API request
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                console.print(
                    f"[red]Error: API returned status code {response.status_code}[/red]"
                )
                return None

            data = response.json()
            console.print("[green]Successfully received standings data[/green]")

        except requests.exceptions.Timeout:
            console.print("[red]Error: request timed out[/red]")
            return None
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error making request: {e}[/red]")
            return None

        # Parse standings data/
        if "standings" not in data:
            console.print("[red]Error: 'standings' key not found in API response[/red]")
            return None

        teams_data = data["standings"]
        console.print(f"Found standings for {len(teams_data)} teams")

        cursor = self.db_connection.cursor()
        teams_updated = 0

        for team in teams_data:
            try:
                # Extract team info
                team_abbrev = team.get("teamAbbrev", {})
                if isinstance(team_abbrev, dict):
                    team_abbrev = team_abbrev.get("default", "UNK")

                conference = team.get("conferenceName", "Unknown")
                division = team.get("divisionName", "Unknown")

                wins = team.get("wins", 0)
                losses = team.get("losses", 0)
                ot_losses = team.get("otLosses", 0)
                points = team.get("points", 0)

                # UPDATE existing team with conference/division
                cursor.execute(
                    """
                    UPDATE teams 
                    SET conference = ?, division = ?
                    WHERE abbreviation = ?
                """,
                    (conference, division, team_abbrev),
                )

                # Update/create cache entry
                if team_abbrev not in self.teams_cache:
                    # Get team_id from database
                    cursor.execute(
                        """
                        SELECT team_id, team_name 
                        FROM teams 
                        WHERE abbreviation = ?
                    """,
                        (team_abbrev,),
                    )
                    result = cursor.fetchone()
                    team_id = result[0] if result else None
                    team_name = result[1] if result else "Unknown"

                    self.teams_cache[team_abbrev] = {
                        "id": team_id,
                        "name": team_name,
                        "abbrev": team_abbrev,
                    }

                # Update cache with standings info
                self.teams_cache[team_abbrev].update(
                    {
                        "conference": conference,
                        "division": division,
                        "wins": wins,
                        "losses": losses,
                        "ot_losses": ot_losses,
                        "points": points,
                    }
                )

                teams_updated += 1

            except Exception as e:
                console.print(f"[red]Warning: Could not process team: {e}[/red]")
                continue

        self.db_connection.commit()
        console.print(f"[green]Successfully enriched {teams_updated} teams[/green]")
        console.print(f"    - Cache now has {len(self.teams_cache)} teams")

        return self.teams_cache

    # TODO Update this to include type of win
    def get_team_stats(self, team_id):
        """
        TOOL: Calculate team statistics

        STEP 3: Loop through each game
            FOR each game:

                A. Determine if team was home or away
                    IF game.home_team_id == team_id:
                        team_was_home = True
                        team_score = game.home_score
                        opponent_score = game.away_score
                    ELSE:
                        team_was_home = False
                        team_score = game.away_score
                        opponent_score = game.home_score

                B. Update goals
                    goals_for += team_score
                    goals_against += opponent_score

                C. Determine if team won
                    IF game.winner_id == team_id:
                        total_wins += 1
                        IF team_was_home:
                            home_wins += 1
                        ELSE:
                            away_wins += 1
                    ELSE:
                        total_losses += 1
                        IF team_was_home:
                            home_losses += 1
                        ELSE:
                            away_losses += 1

        STEP 4: Calculate derived stats
            - total_games = total_wins + total_losses
            - win_percentage = total_wins / total_games (handle divide by zero!)
            - goals_per_game = goals_for / total_games
            - goals_against_per_game = goals_against / total_games
            - goal_differential = goals_for - goals_against

        STEP 5: Calculate recent form (last 5-10 games)
            - Take first 5 games from query (already sorted by date DESC)
            - Count wins in those games
            - recent_form = "3-2" or "W-W-L-W-L" format (your choice)

        STEP 6: Return dictionary with all stats
            RETURN {
                'team_id': team_id,
                'total_games': total_games,
                'wins': total_wins,
                'losses': total_losses,
                'win_pct': win_percentage,
                'goals_for': goals_for,
                'goals_against': goals_against,
                'goal_differential': goal_differential,
                'goals_per_game': goals_per_game,
                'goals_against_per_game': goals_against_per_game,
                'home_record': f"{home_wins}-{home_losses}",
                'away_record': f"{away_wins}-{away_losses}",
                'recent_form': recent_form
        }
        """

        cur = self.db_connection.cursor()
        result = cur.execute(
            """
            SELECT game_id, home_team_id, away_team_id, 
            home_score, away_score, winner_id FROM games WHERE game_state = 'final'
            AND (home_team_id = ? OR away_team_id = ?)
            ORDER BY game_date DESC
        """,
            (team_id, team_id),
        )

        # console.print(result.fetchall())

        # Initialize stat counters
        total_wins = 0
        total_losses = 0
        goals_for = 0
        goals_against = 0
        home_wins = 0
        home_losses = 0
        away_wins = 0
        away_losses = 0

        for game in result.fetchall():
            if game["home_team_id"] == team_id:
                team_was_home = True
                team_score = game["home_score"]
                opponent_score = game["away_score"]
            else:
                team_was_home = False
                team_score = game["away_score"]
                opponent_score = game["home_score"]

            goals_for += team_score
            goals_against += opponent_score

            if game["winner_id"] == team_id:
                total_wins += 1
                if team_was_home:
                    home_wins += 1
                else:
                    away_wins += 1
            else:
                total_losses += 1
                if team_was_home:
                    home_losses += 1
                else:
                    away_losses += 1

        # Derived Stats
        # TODO fix points percentage once OT losses are included
        total_games = total_wins + total_losses
        points_percentage = (total_wins * 2) / (total_games * 2)
        goals_per_game = goals_for / total_games
        goals_against_per_game = goals_against / total_games
        goal_differential = goals_for - goals_against

        # TODO Calculate Last 10

        return {
            "team_id": team_id,
            "total_games": total_games,
            "wins": total_wins,
            "losses": total_losses,
            "points_percentage": points_percentage,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "goal_differential": goal_differential,
            "goals_per_game": goals_per_game,
            "goals_against_per_game": goals_against_per_game,
            "home_record": f"{home_wins}-{home_losses}",
            "away_record": f"{away_wins}-{away_losses}",
            # "last_10" : last_10
        }

    def ensure_complete_game_history(self, days_back=30):
        """
        Fill in any missing game data from the past N days
        """

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")

            self.fetch_games_by_date(date_str)
            current += timedelta(days=1)

    # ===================
    # ACTION METHODS
    # ===================

    def collect_all_data(self):
        """
        ACTION: Collect and store all NHL data

        STEPS:
        1. Print status: "Collecting team standings..."
        2. Call fetch_team_standings()
        3. Print status: "Collecting today's games..."
        4. Call fetch_todays_games()
        5. Print status: "Collecting recent games for each team..."
        6. For each team, call fetch_team_recent_games()
        7. Print summary of data collected
        """
        pass

    def display_todays_games(self):
        """
        ACTION: Show user today's matchup's

        STEPS:
        1. Get today's games
        2. For each game:
           - Print matchup (Team A vs Team B)
           - Print game time
           - Print venue
        """
        pass

    def close(self):
        """
        TASK: Clean up - close database connection
        """
        if self.db_connection:
            self.db_connection.close()
            print("Database connection closed")


# ===================
# MAIN EXECUTION
# ===================


def main():
    """
    Entry point - creates and runs the agent
    """
    console.print("🏒 NHL Game Predictor Agent - Phase 1")
    console.print("[blue]=[/blue]" * 50)

    # Create agent instance
    agent = NHLPredictorAgent()

    console.print("\n[cyan]Step 1: Fetching today's games...[/cyan]")
    console.print("[blue]=[/blue]" * 50)
    agent.fetch_games_by_date()

    console.print("\n[cyan]Step 2: Enriching teams with standings...[/cyan]")
    console.print("[blue]=[/blue]" * 50)
    agent.enrich_teams_with_standings()

    # Clean up
    agent.close()

    print("\n✅ Data collection complete!")


if __name__ == "__main__":
    main()
