import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os

class QuizDatabase:
    def __init__(self, db_path: str = "quiz_app.db"):
        """Initialize the database connection and create tables if they don't exist"""
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create quiz_sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    total_questions INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    percentage REAL NOT NULL,
                    time_taken TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Create quiz_questions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question_id INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    options TEXT NOT NULL,
                    correct_answer INTEGER NOT NULL,
                    user_answer INTEGER,
                    is_correct BOOLEAN NOT NULL,
                    explanation TEXT,
                    FOREIGN KEY (session_id) REFERENCES quiz_sessions (session_id)
                )
            ''')
            
            # Create quiz_results table for summary
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    total_questions INTEGER NOT NULL,
                    percentage REAL NOT NULL,
                    performance_level TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES quiz_sessions (session_id)
                )
            ''')
            
            conn.commit()
            print("✅ Database initialized successfully")

    def save_user(self, user_id: str, name: str) -> bool:
        """Save or update user information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if user already exists
                cursor.execute('SELECT id FROM users WHERE user_id = ?', (user_id,))
                existing_user = cursor.fetchone()
                
                if not existing_user:
                    # Insert new user
                    cursor.execute('''
                        INSERT INTO users (user_id, name)
                        VALUES (?, ?)
                    ''', (user_id, name))
                else:
                    # Update existing user name if different
                    cursor.execute('''
                        UPDATE users SET name = ? WHERE user_id = ?
                    ''', (name, user_id))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"❌ Error saving user: {e}")
            return False

    def save_quiz_session(self, session_id: str, user_id: str, name: str, 
                         department: str, quiz_data: Dict, results: List[Dict], 
                         score: int, time_taken: str = None) -> bool:
        """Save complete quiz session data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                total_questions = len(quiz_data['questions'])
                percentage = (score / total_questions) * 100
                
                # Determine performance level
                if percentage >= 80:
                    performance_level = "Excellent"
                elif percentage >= 60:
                    performance_level = "Good"
                elif percentage >= 40:
                    performance_level = "Average"
                else:
                    performance_level = "Poor"
                
                # Save quiz session
                cursor.execute('''
                    INSERT INTO quiz_sessions 
                    (session_id, user_id, name, department, total_questions, score, percentage, time_taken)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, user_id, name, department, total_questions, score, percentage, time_taken))
                
                # Save individual questions and answers
                for result in results:
                    question_data = next(q for q in quiz_data['questions'] if q['id'] == result['question_id'])
                    
                    cursor.execute('''
                        INSERT INTO quiz_questions 
                        (session_id, question_id, question_text, options, correct_answer, user_answer, is_correct, explanation)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        session_id,
                        result['question_id'],
                        result['question'],
                        json.dumps(question_data['options']),  # Store options as JSON
                        result['correct_answer'],
                        result['user_answer'] if result['user_answer'] is not None else None,
                        result['is_correct'],
                        result['explanation']
                    ))
                
                # Save quiz results summary
                cursor.execute('''
                    INSERT INTO quiz_results 
                    (session_id, user_id, name, department, score, total_questions, percentage, performance_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, user_id, name, department, score, total_questions, percentage, performance_level))
                
                conn.commit()
                print(f"✅ Quiz session {session_id} saved successfully")
                return True
                
        except sqlite3.Error as e:
            print(f"❌ Error saving quiz session: {e}")
            return False

    def get_user_quiz_history(self, user_id: str) -> List[Dict]:
        """Get quiz history for a specific user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT session_id, department, score, total_questions, percentage, 
                           performance_level, created_at
                    FROM quiz_results 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC
                ''', (user_id,))
                
                results = cursor.fetchall()
                return [
                    {
                        'session_id': row[0],
                        'department': row[1],
                        'score': row[2],
                        'total_questions': row[3],
                        'percentage': row[4],
                        'performance_level': row[5],
                        'created_at': row[6]
                    }
                    for row in results
                ]
        except sqlite3.Error as e:
            print(f"❌ Error getting user history: {e}")
            return []

    def get_quiz_details(self, session_id: str) -> Optional[Dict]:
        """Get detailed quiz results for a specific session"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get session info
                cursor.execute('''
                    SELECT user_id, name, department, score, total_questions, percentage, created_at
                    FROM quiz_sessions 
                    WHERE session_id = ?
                ''', (session_id,))
                
                session_data = cursor.fetchone()
                if not session_data:
                    return None
                
                # Get questions and answers
                cursor.execute('''
                    SELECT question_id, question_text, options, correct_answer, user_answer, is_correct, explanation
                    FROM quiz_questions 
                    WHERE session_id = ?
                    ORDER BY question_id
                ''', (session_id,))
                
                questions = cursor.fetchall()
                
                return {
                    'session_id': session_id,
                    'user_id': session_data[0],
                    'name': session_data[1],
                    'department': session_data[2],
                    'score': session_data[3],
                    'total_questions': session_data[4],
                    'percentage': session_data[5],
                    'created_at': session_data[6],
                    'questions': [
                        {
                            'question_id': q[0],
                            'question_text': q[1],
                            'options': json.loads(q[2]),
                            'correct_answer': q[3],
                            'user_answer': q[4],
                            'is_correct': q[5],
                            'explanation': q[6]
                        }
                        for q in questions
                    ]
                }
        except sqlite3.Error as e:
            print(f"❌ Error getting quiz details: {e}")
            return None

    def get_all_quiz_results(self, limit: int = 100) -> List[Dict]:
        """Get all quiz results with pagination"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT session_id, user_id, name, department, score, total_questions, 
                           percentage, performance_level, created_at
                    FROM quiz_results 
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (limit,))
                
                results = cursor.fetchall()
                return [
                    {
                        'session_id': row[0],
                        'user_id': row[1],
                        'name': row[2],
                        'department': row[3],
                        'score': row[4],
                        'total_questions': row[5],
                        'percentage': row[6],
                        'performance_level': row[7],
                        'created_at': row[8]
                    }
                    for row in results
                ]
        except sqlite3.Error as e:
            print(f"❌ Error getting all quiz results: {e}")
            return []

    def get_department_statistics(self, department: str) -> Dict:
        """Get statistics for a specific department"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) as total_attempts,
                           AVG(percentage) as avg_percentage,
                           MAX(percentage) as max_percentage,
                           MIN(percentage) as min_percentage,
                           COUNT(CASE WHEN performance_level = 'Excellent' THEN 1 END) as excellent_count,
                           COUNT(CASE WHEN performance_level = 'Good' THEN 1 END) as good_count,
                           COUNT(CASE WHEN performance_level = 'Average' THEN 1 END) as average_count,
                           COUNT(CASE WHEN performance_level = 'Poor' THEN 1 END) as poor_count
                    FROM quiz_results 
                    WHERE department = ?
                ''', (department,))
                
                result = cursor.fetchone()
                return {
                    'department': department,
                    'total_attempts': result[0],
                    'avg_percentage': round(result[1], 2) if result[1] else 0,
                    'max_percentage': result[2] if result[2] else 0,
                    'min_percentage': result[3] if result[3] else 0,
                    'excellent_count': result[4],
                    'good_count': result[5],
                    'average_count': result[6],
                    'poor_count': result[7]
                }
        except sqlite3.Error as e:
            print(f"❌ Error getting department statistics: {e}")
            return {}

    def delete_quiz_session(self, session_id: str) -> bool:
        """Delete a quiz session and all related data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Delete from quiz_questions
                cursor.execute('DELETE FROM quiz_questions WHERE session_id = ?', (session_id,))
                
                # Delete from quiz_results
                cursor.execute('DELETE FROM quiz_results WHERE session_id = ?', (session_id,))
                
                # Delete from quiz_sessions
                cursor.execute('DELETE FROM quiz_sessions WHERE session_id = ?', (session_id,))
                
                conn.commit()
                print(f"✅ Quiz session {session_id} deleted successfully")
                return True
                
        except sqlite3.Error as e:
            print(f"❌ Error deleting quiz session: {e}")
            return False

    def get_database_info(self) -> Dict:
        """Get general database information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count total users
                cursor.execute('SELECT COUNT(*) FROM users')
                total_users = cursor.fetchone()[0]
                
                # Count total quiz sessions
                cursor.execute('SELECT COUNT(*) FROM quiz_sessions')
                total_sessions = cursor.fetchone()[0]
                
                # Get database file size
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                return {
                    'total_users': total_users,
                    'total_quiz_sessions': total_sessions,
                    'database_size_bytes': db_size,
                    'database_size_mb': round(db_size / (1024 * 1024), 2),
                    'database_path': self.db_path
                }
        except sqlite3.Error as e:
            print(f"❌ Error getting database info: {e}")
            return {}

# Initialize database instance
db = QuizDatabase()

if __name__ == "__main__":
    # Test database functionality
    print("Testing database functionality...")
    
    # Test user creation
    db.save_user("TEST001", "Test User")
    
    # Test getting database info
    info = db.get_database_info()
    print(f"Database info: {info}")
    
    print("✅ Database test completed")