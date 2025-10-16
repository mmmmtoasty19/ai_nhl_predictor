import json
import sqlite3
from datetime import datetime

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

    def fetch_team_standings(self):
        """
        Fetches all NHL teams and their current standings from the NHL API.
        Stores data in both the cache (for quick access) and database (for persistence).

        Returns:
            teams_cached: The in memory storage for team standings
        """
        console.print("[green]Fetching team standings from NHL API...[/green]")

        url = f"{self.nhl_api_base}/v1/standings/now"
        console.print(f"URL: {url}")

        # Make API Request
        try:
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                console.print(
                    f"[red] Error: API returned status code {response.status_code}[/red]"
                )
                return None

            data = response.json()
            console.print("[green]Successfully received data from API[/green]")
        except requests.exceptions.Timeout:
            console.print("[red]Error: request timed out[/red]")
            return None
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error making request: {e}[/red]")

        # Parse the Data

        if "standings" not in data:
            console.print("[red]Error: 'standings' key not found in API response[/red]")
            console.print("   Available keys:", list(data.keys()))
            return None

        teams_data = data["standings"]
        console.print(f"Found {len(teams_data)} teams in standings")

        # Extract and store
        cur = self.db_connection.cursor()
        teams_stored = 0

        for team in teams_data:
            try:
                # API nests data in default keys
                # Extract the info from nested data
                team_abv = team.get("teamAbbrev", {})
                if isinstance(team_abv, dict):
                    team_abv = team_abv.get("default", "UNK")

                team_name = team.get("teamName", {})
                if isinstance(team_name, dict):
                    team_name = team_name.get("default", "Unkown")
                else:
                    team_name = str(team_name)

                conference = team.get("conferenceName", "Unknown")
                division = team.get("divisionName", "Unknown")

                wins = team.get("wins", 0)
                losses = team.get("losses", 0)
                ot_losses = team.get("otLosses", 0)
                points = team.get("points", 0)

                # creating ID using the abbrevation
                team_id = abs(hash(team_abv)) % (10**8)

                # Store in Cache
                self.teams_cache[team_abv] = {
                    "id": team_id,
                    "name": team_name,
                    "abbrev": team_abv,
                    "conference": conference,
                    "division": division,
                    "wins": wins,
                    "losses": losses,
                    "ot_losses": ot_losses,
                    "points": points,
                }

                # Store in DB

                cur.execute(
                    """
                    INSERT OR REPLACE INTO teams
                    (team_id, team_name, abbreviation, conference, division)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (team_id, team_name, team_abv, conference, division),
                )
                teams_stored += 1
            except Exception as e:
                console.print(f"[red] Warning: Cound not process team: {e}")
                continue
        self.db_connection.commit()

        console.print(f"Successfully stored {teams_stored} teams")
        console.print(f"    - In cache: {len(self.teams_cache)} teams")
        console.print(f"    - In database: {teams_stored} teams")

        return self.teams_cache

    def fetch_todays_games(self):
        """
        TOOL: Get games scheduled for today

        STEPS:
        1. Get today's date
        2. Call NHL schedule API
        3. Extract game information
        4. Store games in database
        5. Return list of games
        """
        current_date = datetime.now().strftime("%Y-%m-%d")

        url = f"{self.nhl_api_base}/v1/schedule/{current_date}"
        console.print(f"URL: {url}")

        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                console.print(
                    f"[red] Error: API returned status code {response.status_code}[/red]"
                )
                return None

            data = response.json()
        except requests.exceptions.Timeout:
            console.print("[red]Error: request timed out[/red]")
            return None
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error making request: {e}[/red]")

        todays_data = [
            day for day in data.get("gameWeek", []) if day.get("date") == current_date
        ]

        todays_games = todays_data[0].get("games", []) if todays_data else []

        with open("sample_schedule.json", "w") as f:
            json.dump(todays_games, f, indent=2)

    def fetch_team_recent_games(self, team_id, num_games=5):
        """
        TOOL: Get recent game results for a team

        STEPS:
        1. Query database for team's recent games
        2. If not enough games in DB, fetch from API
        3. Return list of recent games with results
        """
        pass

    def get_team_stats(self, team_id):
        """
        TOOL: Calculate team statistics

        STEPS:
        1. Query database for all team's games
        2. Calculate:
           - Win/loss record
           - Goals per game
           - Home vs away record
           - Recent form (last 5 games)
        3. Return stats dictionary
        """
        pass

    def ensure_complete_game_history(self, days_back=30):
        """
        Fill in any missing game data from the past N days
        """
        from datetime import timedelta

        # STEP 1: Calculate date range
        # - End date = today
        # - Start date = today - days_back

        # STEP 2: For each date in range:
        #   - Query database: How many games on this date?
        #   - If count < expected (usually 1-16 games per day):
        #       - Fetch games for this date from API
        #       - Store in database
        #   - Print progress

        # STEP 3: Print summary
        # - "Found X games, added Y new games"

        pass

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
        ACTION: Show user today's matchups

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

    console.print("[blue]=[/blue]" * 50)

    agent.fetch_team_standings()
    # Clean up
    agent.close()

    print("\n✅ Data collection complete!")


if __name__ == "__main__":
    main()
