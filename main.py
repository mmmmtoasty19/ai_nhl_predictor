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
                win_type TEXT,
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

                # Determine type of WIN
                win_type = game.get("gameOutcome", {}).get("lastPeriodType", "REG")

                # Store game
                cur.execute(
                    """
                    INSERT OR REPLACE INTO games
                    (game_id, game_date, home_team_id, away_team_id, 
                    home_score, away_score, game_state, winner_id, win_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        win_type,
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

    def get_team_stats(self, team_id):
        """
        TOOL: Calculate team statistics
        """

        cur = self.db_connection.cursor()
        result = cur.execute(
            """
            SELECT game_id, home_team_id, away_team_id, 
            home_score, away_score, winner_id, win_type 
            FROM games WHERE game_state = 'final'
            AND (home_team_id = ? OR away_team_id = ?)
            ORDER BY game_date DESC
        """,
            (team_id, team_id),
        )

        # console.print(result.fetchall())

        # Initialize stat counters
        total_wins = 0
        total_losses = 0
        overtime_losses = 0
        goals_for = 0
        goals_against = 0
        home_wins = 0
        home_losses = 0
        home_ot_losses = 0
        away_wins = 0
        away_losses = 0
        away_ot_losses = 0

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
                if game["win_type"] == "REG":
                    total_losses += 1
                    if team_was_home:
                        home_losses += 1
                    else:
                        away_losses += 1
                else:
                    overtime_losses += 1
                    if team_was_home:
                        home_ot_losses += 1
                    else:
                        away_ot_losses += 1

        # Derived Stats
        total_games = total_wins + total_losses
        points = (total_wins * 2) + overtime_losses
        points_percentage = points / (total_games * 2)
        goals_per_game = goals_for / total_games
        goals_against_per_game = goals_against / total_games
        goal_differential = goals_for - goals_against

        # TODO Calculate Last 10

        return {
            "team_id": team_id,
            "total_games": total_games,
            "wins": total_wins,
            "losses": total_losses,
            "overtime_losses": overtime_losses,
            "points": points,
            "points_percentage": points_percentage,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "goal_differential": goal_differential,
            "goals_per_game": goals_per_game,
            "goals_against_per_game": goals_against_per_game,
            "overall_record": f"{total_wins}-{total_losses}-{overtime_losses}",
            "home_record": f"{home_wins}-{home_losses}-{home_ot_losses}",
            "away_record": f"{away_wins}-{away_losses}-{away_ot_losses}",
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

    def _calculate_team_score(self, team_stats, is_home=False):
        # base score using teams Points Percentage
        base_score = team_stats["points_percentage"]

        if is_home:
            base_score += 0.08

        # add Goal Differential capped at +/- 0.15
        gdiff_factor = max(-0.15, min(0.15, team_stats["goal_differential"] / 100))

        record = team_stats["home_record"] if is_home else team_stats["away_record"]

        wins, losses, ot_losses = map(int, record.split("-"))
        points = (wins * 2) + ot_losses
        games = wins + losses + ot_losses
        record_points_pct = points / (games * 2) if games > 0 else 0

        venue_advantage = record_points_pct - team_stats["points_percentage"]

        # Cap Advantage at 0.1
        venue_advantage = max(-0.10, min(0.10, venue_advantage))

        total_score = base_score + gdiff_factor + venue_advantage

        return total_score

    def make_prediction(self, game_id: int, force=False):
        cur = self.db_connection.cursor()

        game = cur.execute(
            """
            SELECT home_team_id, away_team_id, game_state FROM games
            WHERE game_id = ?
        """,
            (game_id,),
        ).fetchone()

        if game["game_state"] != "scheduled":
            console.print(" Cannot predict game that has already started/finished")
            return None

        prediction_exist = cur.execute(
            """ 
            SELECT * FROM predictions
            WHERE game_id = ?
        """,
            (game_id,),
        ).fetchone()

        if prediction_exist and not force:
            console.print("Prediction exists for this game already")
            return None

        if prediction_exist and force:
            cur.execute("DELETE FROM predictions WHERE game_id = ?", (game_id,))
            console.print("[yellow]Overwriting existing prediction...[/yellow]")

        home_stats = self.get_team_stats(game["home_team_id"])
        away_stats = self.get_team_stats(game["away_team_id"])

        home_score = self._calculate_team_score(home_stats, is_home=True)
        away_score = self._calculate_team_score(away_stats, is_home=False)

        if home_score > away_score:
            predicted_winner = game["home_team_id"]
        else:
            predicted_winner = game["away_team_id"]

        confidence = abs(home_score - away_score)

        # Store Prediction
        prediction_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute(
            """
            INSERT INTO predictions (
            game_id, predicted_winner_id, confidence, prediction_date, correct
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (game_id, predicted_winner, confidence, prediction_date, None),
        )

        self.db_connection.commit()

        return {
            "game_id": game_id,
            "home_team": game["home_team_id"],
            "away_team": game["away_team_id"],
            "predicted_winner": predicted_winner,
            "confidence": confidence,
        }

    def clear_predictions(self, game_id=None):
        """
        Clear predictions for testing

        Args:
            game_id: If provided, clear only this game's prediction
                        If None, clear ALL predictions
        """
        cur = self.db_connection.cursor()

        if game_id:
            cur.execute("DELETE FROM predictions WHERE game_id = ?", (game_id,))
            console.print(f"[yellow]Cleared prediction for game {game_id}[/yellow]")
        else:
            cur.execute("DELETE FROM predictions")
            console.print("[yellow]Cleared ALL predictions[/yellow]")

        self.db_connection.commit()

    # ===================
    # ACTION METHODS
    # ===================
    # TODO instead of today, allow user to choose what to predict, maybe even future?
    def predict_todays_games(self, force=False):
        date = datetime.now().strftime("%Y-%m-%d")

        cur = self.db_connection.cursor()

        games = cur.execute(
            """
            SELECT game_id, home_team_id, away_team_id FROM games
            WHERE game_date = ? AND game_state = 'scheduled'
            """,
            (date,),
        ).fetchall()

        if not games:
            print("No scheduled games found for today")
            return 0

        predictions_made = 0
        predictions_skipped = 0

        for game in games:
            game_id = game["game_id"]

            prediction = self.make_prediction(game_id, force=force)

            if prediction is not None:
                predictions_made += 1

                home_id = prediction["home_team"]
                away_id = prediction["away_team"]
                winner_id = prediction["predicted_winner"]
                confidence_pct = prediction["confidence"] * 100

                home_team = cur.execute(
                    "SELECT team_name, abbreviation FROM teams WHERE team_id = ?",
                    (home_id,),
                ).fetchone()

                away_team = cur.execute(
                    "SELECT team_name, abbreviation FROM teams WHERE team_id = ?",
                    (away_id,),
                ).fetchone()

                home_abbrev = (
                    home_team["abbreviation"] if home_team else f"Team {home_id}"
                )
                away_abbrev = (
                    away_team["abbreviation"] if away_team else f"Team {away_id}"
                )

                # Determine winner and loser for nice display
                if winner_id == home_id:
                    winner_abbrev = home_abbrev
                    loser_abbrev = away_abbrev
                else:
                    winner_abbrev = away_abbrev
                    loser_abbrev = home_abbrev

                console.print(
                    f"[green]Predicted:[/green] {winner_abbrev} over {loser_abbrev} "
                    f"({confidence_pct:.1f}% confidence)"
                )

            else:
                predictions_skipped += 1

        console.print(f"\n[cyan]Made {predictions_made} predictions[/cyan]")
        if predictions_skipped > 0:
            console.print(
                f"[yellow]Skipped {predictions_skipped} games "
                f"(already predicted or insufficient data)[/yellow]"
            )

    def evaluate_predictions(self):
        """
        Check predictions against actual results
        Updates 'correct' column for finished games
        """

        cur = self.db_connection.cursor()

        # Find predictions that need evaluation
        predictions_to_evaluate = cur.execute(
            """
            SELECT 
                p.prediction_id,
                p.game_id,
                p.predicted_winner_id,
                g.winner_id,
                g.home_team_id,
                g.away_team_id
            FROM predictions p
            JOIN games g ON p.game_id = g.game_id
            WHERE p.correct IS NULL
            AND g.game_state = 'final'
            """
        ).fetchall()

        # Check if there's anything to evaluate
        if not predictions_to_evaluate:
            console.print("[yellow]No predictions ready for evaluation[/yellow]")
            return None

        # Evaluate each prediction
        evaluated_count = 0
        correct_count = 0

        for prediction in predictions_to_evaluate:
            prediction_id = prediction["prediction_id"]
            predicted_winner = prediction["predicted_winner_id"]
            actual_winner = prediction["winner_id"]

            # Check if prediction was correct
            if predicted_winner == actual_winner:
                is_correct = 1
                correct_count += 1
            else:
                is_correct = 0

            # Update the prediction
            cur.execute(
                """
                UPDATE predictions 
                SET correct = ?
                WHERE prediction_id = ?
                """,
                (is_correct, prediction_id),
            )

            evaluated_count += 1

        # Commit all updates
        self.db_connection.commit()

        # Calculate and display accuracy
        wrong_count = evaluated_count - correct_count
        accuracy = (correct_count / evaluated_count) * 100 if evaluated_count > 0 else 0

        console.print(f"\n[cyan]Evaluated {evaluated_count} predictions[/cyan]")
        console.print(f"[green]Correct: {correct_count}[/green]")
        console.print(f"[red]Wrong: {wrong_count}[/red]")
        console.print(f"[bold]Accuracy: {accuracy:.1f}%[/bold]")

        # Return evaluation summary
        return {
            "evaluated": evaluated_count,
            "correct": correct_count,
            "wrong": wrong_count,
            "accuracy": accuracy,
        }

    # TODO add this post MVP product using as a placeholder for now
    def show_prediction_stats(self):
        cur = self.db_connection.cursor()

        predictions = cur.execute("""
            SELECT confidence, correct FROM predictions 
            WHERE correct IS NOT NULL
            """).fetchall()

        if not predictions:
            console.print("No predictions evaluated yet")
            return None

        # Calculate overall stats
        total = len(predictions)
        correct = sum(1 for pred in predictions if pred["correct"] == 1)
        wrong = total - correct
        accuracy = (correct / total) * 100

        # Print overall stats first
        console.print("\n[bold cyan]═══ Overall Prediction Performance ═══[/bold cyan]")
        console.print(f"Total Predictions: {total}")
        console.print(f"[green]Correct: {correct}[/green]")
        console.print(f"[red]Wrong: {wrong}[/red]")
        console.print(f"[bold]Overall Accuracy: {accuracy:.1f}%[/bold]")

        # Initialize counters for each bucket
        low_total = 0
        low_correct = 0
        medium_total = 0
        medium_correct = 0
        high_total = 0
        high_correct = 0

        for pred in predictions:
            confidence = pred["confidence"]
            is_correct = pred["correct"]

            if confidence < 0.30:
                low_total += 1
                if is_correct == 1:
                    low_correct += 1
            elif confidence < 0.60:
                medium_total += 1
                if is_correct == 1:
                    medium_correct += 1
            else:
                high_total += 1
                if is_correct == 1:
                    high_correct += 1

        # Print breakdown by confidence
        console.print("\n[bold cyan]Breakdown by Confidence Level:[/bold cyan]")

        # Low confidence
        if low_total > 0:
            low_accuracy = (low_correct / low_total) * 100
            console.print(
                f"Low confidence (0-30%): {low_correct}/{low_total} "
                f"correct ({low_accuracy:.1f}%)"
            )

        # Medium confidence
        if medium_total > 0:
            medium_accuracy = (medium_correct / medium_total) * 100
            console.print(
                f"Medium confidence (30-60%): {medium_correct}/{medium_total} "
                f"correct ({medium_accuracy:.1f}%)"
            )

        # High confidence
        if high_total > 0:
            high_accuracy = (high_correct / high_total) * 100
            console.print(
                f"High confidence (60%+): {high_correct}/{high_total} "
                f"correct ({high_accuracy:.1f}%)"
            )

        return {
            "total": total,
            "correct": correct,
            "wrong": wrong,
            "accuracy": accuracy,
            "by_confidence": {
                "low": {"total": low_total, "correct": low_correct},
                "medium": {"total": medium_total, "correct": medium_correct},
                "high": {"total": high_total, "correct": high_correct},
            },
        }

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


# TODO MVP Update to be a loop, or give user options to choose from
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

    """ TODO THis is really only needed at the begining to fill in the teams table with 
     conference and Division """
    # console.print("\n[cyan]Step 2: Enriching teams with standings...[/cyan]")
    # console.print("[blue]=[/blue]" * 50)
    # agent.enrich_teams_with_standings()

    agent.evaluate_predictions()
    agent.predict_todays_games()
    agent.show_prediction_stats()

    # Clean up
    agent.close()

    print("\n✅ Data collection complete!")


if __name__ == "__main__":
    main()
