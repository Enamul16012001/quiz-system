import sqlite3
import json
import uuid
import secrets
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os


class ExamDatabase:
    def __init__(self, db_path: str = "exam_system.db"):
        """Initialize the database connection and create tables if they don't exist"""
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create exams table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exams (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    department TEXT NOT NULL,
                    position TEXT NOT NULL,
                    description TEXT,
                    time_limit INTEGER NOT NULL,
                    instructions TEXT,
                    question_structure TEXT,
                    exam_link TEXT UNIQUE,
                    is_finalized BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Check if is_active column exists, if not add it
            try:
                cursor.execute("SELECT is_active FROM exams LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                print("🔄 Adding is_active column to existing exams table...")
                cursor.execute("ALTER TABLE exams ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
                # Set all existing finalized exams to active
                cursor.execute("UPDATE exams SET is_active = TRUE WHERE is_finalized = TRUE")
                print("✅ Database migration completed")
            
            # Create questions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS questions (
                    id TEXT PRIMARY KEY,
                    exam_id TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    options TEXT,
                    correct_answer INTEGER,
                    expected_answer TEXT,
                    evaluation_criteria TEXT,
                    marks INTEGER NOT NULL,
                    question_order INTEGER,
                    explanation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (exam_id) REFERENCES exams (id)
                )
            ''')
            
            # Create exam_results table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exam_results (
                    id TEXT PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    exam_id TEXT NOT NULL,
                    candidate_name TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    total_marks INTEGER NOT NULL,
                    obtained_marks REAL NOT NULL,
                    percentage REAL NOT NULL,
                    performance_level TEXT NOT NULL,
                    time_taken TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (exam_id) REFERENCES exams (id)
                )
            ''')
            
            # Create candidate_answers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS candidate_answers (
                    id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    candidate_answer TEXT,
                    marks_obtained REAL NOT NULL,
                    is_correct BOOLEAN,
                    feedback TEXT,
                    evaluation_details TEXT,
                    FOREIGN KEY (result_id) REFERENCES exam_results (id),
                    FOREIGN KEY (question_id) REFERENCES questions (id)
                )
            ''')
            
            # Create detailed_evaluations table for storing AI feedback
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detailed_evaluations (
                    id TEXT PRIMARY KEY,
                    answer_id TEXT NOT NULL,
                    strengths TEXT,
                    improvements TEXT,
                    overall_feedback TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (answer_id) REFERENCES candidate_answers (id)
                )
            ''')
            
            conn.commit()
            print("✅ Exam database initialized successfully")

    def create_exam(self, title: str, department: str, position: str, description: str, 
                   time_limit: int, instructions: str, question_structure: Dict) -> str:
        """Create a new exam"""
        try:
            exam_id = str(uuid.uuid4())
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO exams (id, title, department, position, description, 
                                     time_limit, instructions, question_structure)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (exam_id, title, department, position, description, 
                     time_limit, instructions, json.dumps(question_structure)))
                conn.commit()
                print(f"✅ Exam created with ID: {exam_id}")
                return exam_id
        except sqlite3.Error as e:
            print(f"❌ Error creating exam: {e}")
            return None

    def save_exam_question(self, exam_id: str, question_data: Dict) -> str:
        """Save a question for an exam"""
        try:
            question_id = str(uuid.uuid4())
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get current max order for this exam
                cursor.execute('SELECT MAX(question_order) FROM questions WHERE exam_id = ?', (exam_id,))
                max_order = cursor.fetchone()[0] or 0
                
                cursor.execute('''
                    INSERT INTO questions (id, exam_id, question_type, question_text, 
                                         options, correct_answer, expected_answer, 
                                         evaluation_criteria, marks, question_order, explanation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    question_id, exam_id, question_data['type'], question_data['question'],
                    json.dumps(question_data.get('options', [])) if question_data.get('options') else None,
                    question_data.get('correct_answer'),
                    question_data.get('expected_answer'),
                    question_data.get('evaluation_criteria'),
                    question_data['marks'],
                    max_order + 1,
                    question_data.get('explanation')
                ))
                conn.commit()
                return question_id
        except sqlite3.Error as e:
            print(f"❌ Error saving question: {e}")
            return None

    def get_exam_by_id(self, exam_id: str) -> Optional[Dict]:
        """Get exam by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, title, department, position, description, time_limit, 
                           instructions, question_structure, exam_link, is_finalized, is_active, created_at
                    FROM exams WHERE id = ?
                ''', (exam_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'title': row[1],
                        'department': row[2],
                        'position': row[3],
                        'description': row[4],
                        'time_limit': row[5],
                        'instructions': row[6],
                        'question_structure': json.loads(row[7]) if row[7] else {},
                        'exam_link': row[8],
                        'is_finalized': bool(row[9]),  # Convert to boolean
                        'is_active': bool(row[10]),    # Convert to boolean
                        'created_at': row[11]
                    }
                return None
        except sqlite3.Error as e:
            print(f"❌ Error getting exam: {e}")
            return None

    def toggle_exam_status(self, exam_id: str, is_active: bool) -> bool:
        """Activate or deactivate an exam"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE exams SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (is_active, exam_id))
                conn.commit()
                status = "activated" if is_active else "deactivated"
                print(f"✅ Exam {status} successfully")
                return True
        except sqlite3.Error as e:
            print(f"❌ Error toggling exam status: {e}")
            return False

    def update_question_marks(self, question_id: str, result_id: str, new_marks: float) -> bool:
        """Update marks for a specific question in a result"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Update the marks in candidate_answers
                cursor.execute('''
                    UPDATE candidate_answers 
                    SET marks_obtained = ? 
                    WHERE question_id = ? AND result_id = ?
                ''', (new_marks, question_id, result_id))
                
                # Recalculate total marks and percentage for the result
                cursor.execute('''
                    SELECT SUM(marks_obtained) FROM candidate_answers 
                    WHERE result_id = ?
                ''', (result_id,))
                total_obtained = cursor.fetchone()[0] or 0
                
                cursor.execute('''
                    SELECT total_marks FROM exam_results 
                    WHERE id = ?
                ''', (result_id,))
                total_marks = cursor.fetchone()[0] or 1
                
                new_percentage = (total_obtained / total_marks) * 100
                
                # Determine new performance level
                if new_percentage >= 85:
                    performance_level = "Excellent"
                elif new_percentage >= 70:
                    performance_level = "Good"
                elif new_percentage >= 50:
                    performance_level = "Average"
                else:
                    performance_level = "Poor"
                
                # Update the exam_results table
                cursor.execute('''
                    UPDATE exam_results 
                    SET obtained_marks = ?, percentage = ?, performance_level = ?
                    WHERE id = ?
                ''', (total_obtained, new_percentage, performance_level, result_id))
                
                conn.commit()
                print(f"✅ Question marks updated successfully")
                return True
        except sqlite3.Error as e:
            print(f"❌ Error updating question marks: {e}")
            return False

    def get_exam_by_link(self, exam_link: str) -> Optional[Dict]:
        """Get exam by link"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # First check if exam exists with this link
                cursor.execute('''
                    SELECT id, title, department, position, description, time_limit, 
                           instructions, question_structure, exam_link, is_finalized, is_active
                    FROM exams WHERE exam_link = ?
                ''', (exam_link,))
                
                row = cursor.fetchone()
                if not row:
                    print(f"❌ No exam found with link: {exam_link}")
                    return None
                
                exam_data = {
                    'id': row[0],
                    'title': row[1],
                    'department': row[2],
                    'position': row[3],
                    'description': row[4],
                    'time_limit': row[5],
                    'instructions': row[6],
                    'question_structure': json.loads(row[7]) if row[7] else {},
                    'exam_link': row[8],
                    'is_finalized': row[9],
                    'is_active': row[10]
                }
                
                print(f"📊 Exam found - Title: {exam_data['title']}, Finalized: {exam_data['is_finalized']}, Active: {exam_data['is_active']}")
                
                # Check if exam is finalized and active
                if not exam_data['is_finalized']:
                    print(f"❌ Exam not finalized: {exam_data['title']}")
                    return None
                    
                if not exam_data['is_active']:
                    print(f"❌ Exam not active: {exam_data['title']}")
                    return None
                
                print(f"✅ Exam accessible: {exam_data['title']}")
                return exam_data
                
        except sqlite3.Error as e:
            print(f"❌ Error getting exam by link: {e}")
            return None

    def get_exam_questions(self, exam_id: str) -> List[Dict]:
        """Get all questions for an exam"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, question_type, question_text, options, correct_answer, 
                           expected_answer, evaluation_criteria, marks, explanation
                    FROM questions WHERE exam_id = ? ORDER BY question_order
                ''', (exam_id,))
                
                questions = []
                for row in cursor.fetchall():
                    question = {
                        'id': row[0],
                        'type': row[1],
                        'question': row[2],
                        'marks': row[7],
                        'explanation': row[8]
                    }
                    
                    if row[3]:  # options exist (MCQ)
                        question['options'] = json.loads(row[3])
                        question['correct_answer'] = row[4]
                    else:  # short/essay questions
                        question['expected_answer'] = row[5]
                        question['evaluation_criteria'] = row[6]
                    
                    questions.append(question)
                
                return questions
        except sqlite3.Error as e:
            print(f"❌ Error getting exam questions: {e}")
            return []

    def finalize_exam(self, exam_id: str) -> str:
        """Finalize exam and generate unique link"""
        try:
            exam_link = secrets.token_urlsafe(16)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE exams SET exam_link = ?, is_finalized = TRUE, is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (exam_link, exam_id))
                conn.commit()
                print(f"✅ Exam finalized and activated with link: {exam_link}")
                return exam_link
        except sqlite3.Error as e:
            print(f"❌ Error finalizing exam: {e}")
            return None

    def save_exam_result(self, session_id: str, exam_id: str, candidate_name: str, 
                        candidate_id: str, answers: Dict, evaluation: Dict, time_taken: str) -> bool:
        """Save exam result and candidate answers"""
        try:
            result_id = str(uuid.uuid4())
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Save main result
                cursor.execute('''
                    INSERT INTO exam_results (id, session_id, exam_id, candidate_name, candidate_id,
                                            total_marks, obtained_marks, percentage, performance_level, time_taken)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    result_id, session_id, exam_id, candidate_name, candidate_id,
                    evaluation['total_marks'], evaluation['obtained_marks'], 
                    evaluation['percentage'], evaluation['performance_level'], time_taken
                ))
                
                # Save individual answers
                for question_result in evaluation['question_results']:
                    answer_id = str(uuid.uuid4())
                    cursor.execute('''
                        INSERT INTO candidate_answers (id, result_id, question_id, candidate_answer,
                                                     marks_obtained, is_correct, feedback, evaluation_details)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        answer_id, result_id, question_result['question_id'],
                        question_result['candidate_answer'], question_result['marks_obtained'],
                        question_result.get('is_correct'), question_result['feedback'],
                        question_result.get('evaluation_details')
                    ))
                    
                    # Save detailed evaluation if available
                    if question_result.get('strengths') or question_result.get('improvements'):
                        cursor.execute('''
                            INSERT INTO detailed_evaluations (id, answer_id, strengths, improvements, overall_feedback)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            str(uuid.uuid4()), answer_id,
                            question_result.get('strengths'),
                            question_result.get('improvements'),
                            evaluation.get('overall_feedback')
                        ))
                
                conn.commit()
                print(f"✅ Exam result saved for {candidate_name}")
                return True
        except sqlite3.Error as e:
            print(f"❌ Error saving exam result: {e}")
            return False

    def get_all_exams(self) -> List[Dict]:
        """Get all exams"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, title, department, position, description, time_limit, 
                           exam_link, is_finalized, is_active, created_at
                    FROM exams ORDER BY created_at DESC
                ''')
                
                exams = []
                for row in cursor.fetchall():
                    exams.append({
                        'id': row[0],
                        'title': row[1],
                        'department': row[2],
                        'position': row[3],
                        'description': row[4],
                        'time_limit': row[5],
                        'exam_link': row[6],
                        'is_finalized': bool(row[7]),  # Convert to boolean
                        'is_active': bool(row[8]),     # Convert to boolean
                        'created_at': row[9]
                    })
                return exams
        except sqlite3.Error as e:
            print(f"❌ Error getting all exams: {e}")
            return []

    def get_recent_exam_results(self, limit: int = 50) -> List[Dict]:
        """Get recent exam results"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT er.id, er.candidate_name, er.candidate_id, er.total_marks,
                           er.obtained_marks, er.percentage, er.performance_level,
                           er.time_taken, er.submitted_at, e.title, e.department, e.position
                    FROM exam_results er
                    JOIN exams e ON er.exam_id = e.id
                    ORDER BY er.submitted_at DESC
                    LIMIT ?
                ''', (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'id': row[0],
                        'candidate_name': row[1],
                        'candidate_id': row[2],
                        'total_marks': row[3],
                        'obtained_marks': row[4],
                        'percentage': row[5],
                        'performance_level': row[6],
                        'time_taken': row[7],
                        'submitted_at': row[8],
                        'exam_title': row[9],
                        'department': row[10],
                        'position': row[11]
                    })
                return results
        except sqlite3.Error as e:
            print(f"❌ Error getting recent results: {e}")
            return []

    def get_exam_results(self, exam_id: str) -> List[Dict]:
        """Get all results for a specific exam"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, candidate_name, candidate_id, total_marks, obtained_marks,
                           percentage, performance_level, time_taken, submitted_at
                    FROM exam_results WHERE exam_id = ?
                    ORDER BY submitted_at DESC
                ''', (exam_id,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'id': row[0],
                        'candidate_name': row[1],
                        'candidate_id': row[2],
                        'total_marks': row[3],
                        'obtained_marks': row[4],
                        'percentage': row[5],
                        'performance_level': row[6],
                        'time_taken': row[7],
                        'submitted_at': row[8]
                    })
                return results
        except sqlite3.Error as e:
            print(f"❌ Error getting exam results: {e}")
            return []

    def update_question(self, question_id: str, question_data: Dict) -> bool:
        """Update a question"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE questions SET question_text = ?, options = ?, correct_answer = ?,
                                       expected_answer = ?, evaluation_criteria = ?, marks = ?, explanation = ?
                    WHERE id = ?
                ''', (
                    question_data['question'],
                    json.dumps(question_data.get('options', [])) if question_data.get('options') else None,
                    question_data.get('correct_answer'),
                    question_data.get('expected_answer'),
                    question_data.get('evaluation_criteria'),
                    question_data['marks'],
                    question_data.get('explanation'),
                    question_id
                ))
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"❌ Error updating question: {e}")
            return False

    def delete_question(self, question_id: str) -> bool:
        """Delete a question"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM questions WHERE id = ?', (question_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"❌ Error deleting question: {e}")
            return False

    def get_result_details(self, result_id: str) -> Optional[Dict]:
        """Get detailed results for a specific result"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get main result info
                cursor.execute('''
                    SELECT er.candidate_name, er.candidate_id, er.total_marks, er.obtained_marks,
                           er.percentage, er.performance_level, er.time_taken, er.submitted_at,
                           e.title as exam_title, e.department, e.position
                    FROM exam_results er
                    JOIN exams e ON er.exam_id = e.id
                    WHERE er.id = ?
                ''', (result_id,))
                
                result_row = cursor.fetchone()
                if not result_row:
                    return None
                
                # Get detailed answers
                cursor.execute('''
                    SELECT ca.question_id, ca.candidate_answer, ca.marks_obtained, ca.is_correct,
                           ca.feedback, ca.evaluation_details, q.question_text, q.question_type,
                           q.marks, q.options, q.correct_answer
                    FROM candidate_answers ca
                    JOIN questions q ON ca.question_id = q.id
                    WHERE ca.result_id = ?
                    ORDER BY q.question_order
                ''', (result_id,))
                
                questions = []
                for row in cursor.fetchall():
                    question = {
                        'question_id': row[0],
                        'candidate_answer': row[1],
                        'marks_obtained': row[2],
                        'is_correct': row[3],
                        'feedback': row[4],
                        'evaluation_details': row[5],
                        'question_text': row[6],
                        'question_type': row[7],
                        'marks_total': row[8]
                    }
                    
                    # Add MCQ specific data
                    if row[7] == 'mcq' and row[9]:  # if question_type is mcq and options exist
                        options = json.loads(row[9])
                        question['options'] = options
                        question['correct_answer'] = row[10]
                        
                        # Get selected and correct option text
                        if row[1] is not None and row[1].isdigit():
                            selected_idx = int(row[1])
                            if 0 <= selected_idx < len(options):
                                question['selected_option'] = options[selected_idx]
                        
                        if row[10] is not None and 0 <= row[10] < len(options):
                            question['correct_option'] = options[row[10]]
                    
                    questions.append(question)
                
                return {
                    'result_id': result_id,
                    'candidate_name': result_row[0],
                    'candidate_id': result_row[1],
                    'total_marks': result_row[2],
                    'obtained_marks': result_row[3],
                    'percentage': result_row[4],
                    'performance_level': result_row[5],
                    'time_taken': result_row[6],
                    'submitted_at': result_row[7],
                    'exam_title': result_row[8],
                    'department': result_row[9],
                    'position': result_row[10],
                    'questions': questions
                }
                
        except sqlite3.Error as e:
            print(f"❌ Error getting result details: {e}")
            return None

    def delete_exam(self, exam_id: str) -> bool:
        """Delete an exam and all related data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Delete questions first (foreign key constraint)
                cursor.execute('DELETE FROM questions WHERE exam_id = ?', (exam_id,))
                
                # Delete candidate answers related to this exam
                cursor.execute('''
                    DELETE FROM candidate_answers 
                    WHERE result_id IN (
                        SELECT id FROM exam_results WHERE exam_id = ?
                    )
                ''', (exam_id,))
                
                # Delete detailed evaluations
                cursor.execute('''
                    DELETE FROM detailed_evaluations 
                    WHERE answer_id IN (
                        SELECT ca.id FROM candidate_answers ca
                        JOIN exam_results er ON ca.result_id = er.id
                        WHERE er.exam_id = ?
                    )
                ''', (exam_id,))
                
                # Delete exam results
                cursor.execute('DELETE FROM exam_results WHERE exam_id = ?', (exam_id,))
                
                # Finally delete the exam
                cursor.execute('DELETE FROM exams WHERE id = ?', (exam_id,))
                
                conn.commit()
                print(f"✅ Exam {exam_id} deleted successfully")
                return True
        except sqlite3.Error as e:
            print(f"❌ Error deleting exam: {e}")
            return False

    def get_database_info(self) -> Dict:
        """Get general database information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count total exams
                cursor.execute('SELECT COUNT(*) FROM exams')
                total_exams = cursor.fetchone()[0]
                
                # Count total results
                cursor.execute('SELECT COUNT(*) FROM exam_results')
                total_results = cursor.fetchone()[0]
                
                # Count finalized exams
                cursor.execute('SELECT COUNT(*) FROM exams WHERE is_finalized = TRUE')
                finalized_exams = cursor.fetchone()[0]
                
                # Get database file size
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                return {
                    'total_exams': total_exams,
                    'finalized_exams': finalized_exams,
                    'total_results': total_results,
                    'database_size_bytes': db_size,
                    'database_size_mb': round(db_size / (1024 * 1024), 2),
                    'database_path': self.db_path
                }
        except sqlite3.Error as e:
            print(f"❌ Error getting database info: {e}")
            return {}
        
        # Add these new methods to your ExamDatabase class in db.py:

    def update_result_info(self, result_id: str, candidate_name: str, candidate_id: str, time_taken: str) -> bool:
        """Update basic result information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE exam_results 
                    SET candidate_name = ?, candidate_id = ?, time_taken = ?
                    WHERE id = ?
                ''', (candidate_name, candidate_id, time_taken, result_id))
                conn.commit()
                print(f"✅ Result info updated successfully for result {result_id}")
                return True
        except sqlite3.Error as e:
            print(f"❌ Error updating result info: {e}")
            return False

    def get_result_summary(self, result_id: str) -> Optional[Dict]:
        """Get basic result information for editing"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT er.candidate_name, er.candidate_id, er.time_taken, er.total_marks,
                        er.obtained_marks, er.percentage, er.performance_level, e.title
                    FROM exam_results er
                    JOIN exams e ON er.exam_id = e.id
                    WHERE er.id = ?
                ''', (result_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return {
                    'result_id': result_id,
                    'candidate_name': row[0],
                    'candidate_id': row[1],
                    'time_taken': row[2],
                    'total_marks': row[3],
                    'obtained_marks': row[4],
                    'percentage': row[5],
                    'performance_level': row[6],
                    'exam_title': row[7]
                }
        except sqlite3.Error as e:
            print(f"❌ Error getting result summary: {e}")
            return None


# Initialize database instance
db = ExamDatabase()

if __name__ == "__main__":
    # Test database functionality
    print("Testing exam database functionality...")
    
    # Test exam creation
    exam_id = db.create_exam(
        "Software Engineer Test",
        "Information Technology", 
        "Software Engineer",
        "Technical assessment for software engineer position",
        120,
        "Read all questions carefully before answering.",
        {"mcq_count": 5, "short_count": 3, "essay_count": 2, "mcq_marks": 2, "short_marks": 5, "essay_marks": 10}
    )
    
    if exam_id:
        print(f"Test exam created: {exam_id}")
        
        # Test getting database info
        info = db.get_database_info()
        print(f"Database info: {info}")
    
    print("✅ Database test completed")