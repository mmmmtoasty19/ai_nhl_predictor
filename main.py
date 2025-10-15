# PSEUDOCODE for class-based agent
import sqlite3
from datetime import datetime

import requests


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
        TOOL: Get current NHL standings

        STEPS:
        1. Make API request to standings endpoint
        2. Parse team data
        3. Store in self.teams_cache
        4. Store in database
        5. Return formatted data
        """
        pass

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
        pass

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
    print("🏒 NHL Game Predictor Agent - Phase 1")
    print("=" * 50)

    # Create agent instance
    agent = NHLPredictorAgent()

    # TODO Uncomment as these steps are avaliable
    # Run data collection
    # agent.collect_all_data()

    # # Display today's games
    # print("\n📅 Today's NHL Games:")
    # agent.display_todays_games()

    # Clean up
    agent.close()

    print("\n✅ Data collection complete!")


if __name__ == "__main__":
    main()
