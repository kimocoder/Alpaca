"""
Statistics service for Alpaca application.
Provides usage tracking and analytics for token usage, response times, and model usage.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List
import sqlite3
import os
import uuid


def generate_uuid() -> str:
    """Generate a unique ID for database records."""
    return f"{datetime.today().strftime('%Y%m%d%H%M%S%f')}{uuid.uuid4().hex}"


def _get_data_dir():
    """Get the data directory for Alpaca database."""
    try:
        from ..constants import data_dir
        return data_dir
    except ImportError:
        try:
            from constants import data_dir
            return data_dir
        except (ImportError, NameError):
            # Fallback for testing - use XDG_DATA_HOME or default
            base = os.getenv("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
            return os.path.join(base, "com.jeffser.Alpaca")


@dataclass
class TokenUsageStats:
    """
    Represents token usage statistics over a time period.
    
    Attributes:
        total_tokens: Total number of tokens used
        prompt_tokens: Tokens used for prompts
        completion_tokens: Tokens used for completions
        period_start: Start of the statistics period
        period_end: End of the statistics period
        by_model: Token usage broken down by model
    """
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    by_model: Dict[str, int]


@dataclass
class ResponseTimeStats:
    """
    Represents response time statistics.
    
    Attributes:
        average_ms: Average response time in milliseconds
        min_ms: Minimum response time in milliseconds
        max_ms: Maximum response time in milliseconds
        median_ms: Median response time in milliseconds
        total_requests: Total number of requests
        model: Optional model name for filtered stats
    """
    average_ms: float
    min_ms: int
    max_ms: int
    median_ms: float
    total_requests: int
    model: Optional[str]


class StatisticsService:
    """
    Service for tracking and analyzing usage statistics in the Alpaca application.
    
    This service records and retrieves statistics about:
    - Token usage (prompt and completion tokens)
    - Response times for model requests
    - Model usage frequency
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the statistics service with database connection.
        
        Args:
            db_path: Optional custom database path (mainly for testing)
        """
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.path.join(_get_data_dir(), "alpaca.db")
        
        # Ensure the statistics table exists
        self._ensure_table_exists()
    
    def _ensure_table_exists(self) -> None:
        """
        Ensure the statistics table exists in the database.
        Creates it if it doesn't exist.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS statistics (
                    id TEXT NOT NULL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    model TEXT,
                    tokens_used INTEGER,
                    response_time_ms INTEGER,
                    timestamp DATETIME NOT NULL
                )
            """)
            
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"Error creating statistics table: {e}")
    
    def record_token_usage(
        self,
        model: str,
        tokens_used: int,
        event_id: Optional[str] = None
    ) -> str:
        """
        Record token usage for a model interaction.
        
        Args:
            model: Name of the model used
            tokens_used: Number of tokens consumed
            event_id: Optional unique identifier for this event
        
        Returns:
            The event ID (generated if not provided)
        """
        if event_id is None:
            event_id = generate_uuid()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO statistics (id, event_type, model, tokens_used, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                event_id,
                'token_usage',
                model,
                tokens_used,
                datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            ))
            
            conn.commit()
            conn.close()
            
            return event_id
        except sqlite3.Error as e:
            print(f"Error recording token usage: {e}")
            return event_id
    
    def record_response_time(
        self,
        model: str,
        response_time_ms: int,
        event_id: Optional[str] = None
    ) -> str:
        """
        Record response time for a model interaction.
        
        Args:
            model: Name of the model used
            response_time_ms: Response time in milliseconds
            event_id: Optional unique identifier for this event
        
        Returns:
            The event ID (generated if not provided)
        """
        if event_id is None:
            event_id = generate_uuid()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO statistics (id, event_type, model, response_time_ms, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                event_id,
                'response_time',
                model,
                response_time_ms,
                datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            ))
            
            conn.commit()
            conn.close()
            
            return event_id
        except sqlite3.Error as e:
            print(f"Error recording response time: {e}")
            return event_id
    
    def record_model_usage(
        self,
        model: str,
        event_id: Optional[str] = None
    ) -> str:
        """
        Record that a model was used.
        
        Args:
            model: Name of the model used
            event_id: Optional unique identifier for this event
        
        Returns:
            The event ID (generated if not provided)
        """
        if event_id is None:
            event_id = generate_uuid()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO statistics (id, event_type, model, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                event_id,
                'model_usage',
                model,
                datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            ))
            
            conn.commit()
            conn.close()
            
            return event_id
        except sqlite3.Error as e:
            print(f"Error recording model usage: {e}")
            return event_id
    
    def get_token_usage(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> TokenUsageStats:
        """
        Get token usage statistics for a time period.
        
        Args:
            date_from: Optional start date for filtering
            date_to: Optional end date for filtering
        
        Returns:
            TokenUsageStats object with aggregated statistics
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Build query with optional date filtering
            sql_query = """
                SELECT 
                    SUM(tokens_used) as total_tokens,
                    model
                FROM statistics
                WHERE event_type = 'token_usage'
                AND tokens_used IS NOT NULL
            """
            
            params = []
            
            if date_from is not None:
                sql_query += " AND timestamp >= ?"
                params.append(date_from.strftime("%Y/%m/%d %H:%M:%S"))
            
            if date_to is not None:
                sql_query += " AND timestamp <= ?"
                params.append(date_to.strftime("%Y/%m/%d %H:%M:%S"))
            
            sql_query += " GROUP BY model"
            
            cursor.execute(sql_query, params)
            rows = cursor.fetchall()
            
            # Calculate totals and by-model breakdown
            total_tokens = 0
            by_model = {}
            
            for row in rows:
                tokens = row[0] or 0
                model = row[1] or "unknown"
                total_tokens += tokens
                by_model[model] = tokens
            
            conn.close()
            
            return TokenUsageStats(
                total_tokens=total_tokens,
                prompt_tokens=0,  # Not tracked separately yet
                completion_tokens=0,  # Not tracked separately yet
                period_start=date_from,
                period_end=date_to,
                by_model=by_model
            )
            
        except sqlite3.Error as e:
            print(f"Error getting token usage: {e}")
            return TokenUsageStats(
                total_tokens=0,
                prompt_tokens=0,
                completion_tokens=0,
                period_start=date_from,
                period_end=date_to,
                by_model={}
            )
    
    def get_response_times(
        self,
        model: Optional[str] = None
    ) -> ResponseTimeStats:
        """
        Get response time analytics, optionally filtered by model.
        
        Args:
            model: Optional model name to filter by
        
        Returns:
            ResponseTimeStats object with aggregated statistics
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Build query with optional model filtering
            sql_query = """
                SELECT response_time_ms
                FROM statistics
                WHERE event_type = 'response_time'
                AND response_time_ms IS NOT NULL
            """
            
            params = []
            
            if model is not None:
                sql_query += " AND model = ?"
                params.append(model)
            
            sql_query += " ORDER BY response_time_ms"
            
            cursor.execute(sql_query, params)
            rows = cursor.fetchall()
            
            conn.close()
            
            if not rows:
                return ResponseTimeStats(
                    average_ms=0.0,
                    min_ms=0,
                    max_ms=0,
                    median_ms=0.0,
                    total_requests=0,
                    model=model
                )
            
            # Calculate statistics
            response_times = [row[0] for row in rows]
            total_requests = len(response_times)
            
            average_ms = sum(response_times) / total_requests
            min_ms = min(response_times)
            max_ms = max(response_times)
            
            # Calculate median
            if total_requests % 2 == 0:
                median_ms = (response_times[total_requests // 2 - 1] + 
                           response_times[total_requests // 2]) / 2.0
            else:
                median_ms = float(response_times[total_requests // 2])
            
            return ResponseTimeStats(
                average_ms=average_ms,
                min_ms=min_ms,
                max_ms=max_ms,
                median_ms=median_ms,
                total_requests=total_requests,
                model=model
            )
            
        except sqlite3.Error as e:
            print(f"Error getting response times: {e}")
            return ResponseTimeStats(
                average_ms=0.0,
                min_ms=0,
                max_ms=0,
                median_ms=0.0,
                total_requests=0,
                model=model
            )
    
    def get_model_usage(self) -> Dict[str, int]:
        """
        Get model usage frequency across all recorded events.
        
        Returns:
            Dictionary mapping model names to usage counts
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT model, COUNT(*) as usage_count
                FROM statistics
                WHERE event_type = 'model_usage'
                AND model IS NOT NULL
                GROUP BY model
                ORDER BY usage_count DESC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            # Convert to dictionary
            model_usage = {}
            for row in rows:
                model = row[0]
                count = row[1]
                model_usage[model] = count
            
            return model_usage
            
        except sqlite3.Error as e:
            print(f"Error getting model usage: {e}")
            return {}
    
    def clear_statistics(
        self,
        date_before: Optional[datetime] = None
    ) -> int:
        """
        Clear statistics, optionally only those before a certain date.
        
        Args:
            date_before: Optional date - only clear statistics before this date
        
        Returns:
            Number of records deleted
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if date_before is not None:
                cursor.execute("""
                    DELETE FROM statistics
                    WHERE timestamp < ?
                """, (date_before.strftime("%Y/%m/%d %H:%M:%S"),))
            else:
                cursor.execute("DELETE FROM statistics")
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            return deleted_count
            
        except sqlite3.Error as e:
            print(f"Error clearing statistics: {e}")
            return 0
