"""
XFINLAB Event Intelligence V1
Database Module - Manages event history storage and retrieval
"""

import sqlite3
import os
from typing import List, Dict, Optional


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "event_history.db")
SQL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "event_history.sql")


class EventDatabase:
    """Handles all database operations for event history"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database and load schema + sample data if not exists"""
        db_exists = os.path.exists(self.db_path)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if not db_exists:
                # Load and execute SQL schema + sample data
                if os.path.exists(SQL_PATH):
                    with open(SQL_PATH, "r") as f:
                        sql_script = f.read()
                    cursor.executescript(sql_script)
                    conn.commit()
            else:
                # Ensure table exists even if DB file exists but is empty
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS event_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        event_date TEXT NOT NULL,
                        price_before REAL NOT NULL,
                        price_after_1d REAL,
                        price_after_7d REAL,
                        price_after_30d REAL,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """
                )
                conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def find_events_by_type(self, event_type: str) -> List[Dict]:
        """Find all events matching a given event type"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM event_history
                WHERE event_type = ?
                ORDER BY event_date DESC
            """,
                (event_type,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def find_events_by_symbol(self, symbol: str) -> List[Dict]:
        """Find all events for a given symbol"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM event_history
                WHERE symbol = ?
                ORDER BY event_date DESC
            """,
                (symbol,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def find_events(
        self, symbol: Optional[str] = None, event_type: Optional[str] = None
    ) -> List[Dict]:
        """Find events filtered by symbol and/or event type"""
        query = "SELECT * FROM event_history WHERE 1=1"
        params = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY event_date DESC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def insert_event(
        self,
        symbol: str,
        event_type: str,
        event_date: str,
        price_before: float,
        price_after_1d: float = None,
        price_after_7d: float = None,
        price_after_30d: float = None,
    ) -> int:
        """Insert a new event record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO event_history
                (symbol, event_type, event_date, price_before, price_after_1d, price_after_7d, price_after_30d)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    symbol,
                    event_type,
                    event_date,
                    price_before,
                    price_after_1d,
                    price_after_7d,
                    price_after_30d,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_all_events(self) -> List[Dict]:
        """Get all events in the database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM event_history ORDER BY event_date DESC")
            return [dict(row) for row in cursor.fetchall()]
