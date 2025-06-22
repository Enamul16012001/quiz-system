# Add this at the top of your main.py file with other constants
DEPARTMENTS = [
    "Human Resources",
    "Marketing", 
    "Software Engineering",
    "Sales",
    "Finance",
    "Customer Service",
    "Operations",
    "Data Science",
    "Project Management",
    "Machine Learning Engineer",
    "Pharmaceutical"
]

import google.generativeai as genai
import json
import re
from typing import Dict, List, Tuple, Optional


class JobQuizSystem:
    def __init__(self, api_key: str):
        """Initialize the quiz system with Gemini API key"""
        genai.configure(api_key=api_key)
        # Configure generation settings separately
        self.generation_config = genai.types.GenerationConfig(
            temperature=1.5
        )
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def generate_quiz(self, department: str) -> Optional[Dict]:
        """Generate a quiz with 10 MCQs for the specified department"""
        prompt = f"""
        Create a quiz for the {department} department with exactly 10 DIFFERENT multiple choice questions.
        Each question must be unique and cover different aspects of {department} work.

        For {department}, include questions about:
        - Technical skills and knowledge specific to {department}
        - Industry best practices and standards
        - Common scenarios and problem-solving
        - Tools and methodologies used in {department}
        - Professional responsibilities and ethics
        - Current trends and challenges in {department}

        Format your response as a JSON object with this exact structure:
        {{
            "department": "{department}",
            "questions": [
                {{
                    "id": 1,
                    "question": "Question text here",
                    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
                    "correct_answer": 0,
                    "explanation": "Brief explanation of why this is correct"
                }}
            ]
        }}

        IMPORTANT REQUIREMENTS:
        - All 10 questions must be completely different from each other
        - Each question should test different knowledge areas within {department}
        - Make questions specific to {department} work, not generic workplace questions
        - Ensure variety in question types (technical, scenario-based, conceptual)
        - correct_answer should be the index (0, 1, 2, or 3) of the correct option
        - Give each question a unique id from 1 to 10

        Return only the JSON object, no additional text.
        """

        try:
            print(f"🤖 Generating quiz for {department} using Gemini API...")
            # Use generation_config instead of temperature parameter
            response = self.model.generate_content(
                prompt, 
                generation_config=self.generation_config
            )

            # Clean the response to extract JSON
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]

            # Parse JSON
            quiz_data = json.loads(response_text.strip())

            # Validate the structure
            if not self._validate_quiz_structure(quiz_data):
                print("❌ Quiz structure validation failed")
                raise ValueError("Invalid quiz structure received from API")

            print("✅ Quiz generated successfully by Gemini API!")
            return quiz_data

        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {str(e)}")
            print(f"Raw response: {response.text}")
            return None
        except Exception as e:
            print(f"❌ Error generating quiz with Gemini API: {str(e)}")
            return None

    def _validate_quiz_structure(self, quiz_data: Dict) -> bool:
        """Validate that the quiz has the correct structure"""
        try:
            if 'questions' not in quiz_data:
                return False

            questions = quiz_data['questions']
            if len(questions) != 10:
                return False

            for q in questions:
                required_keys = ['id', 'question', 'options', 'correct_answer']
                if not all(key in q for key in required_keys):
                    return False
                if len(q['options']) != 4:
                    return False
                if not isinstance(q['correct_answer'], int) or q['correct_answer'] not in [0, 1, 2, 3]:
                    return False

            return True
        except:
            return False

    def calculate_score(self, quiz_data: Dict, user_answers: Dict) -> Tuple[int, List[Dict]]:
        """Calculate quiz score and return detailed results"""
        score = 0
        results = []

        for question in quiz_data['questions']:
            question_id = str(question['id'])
            user_answer = user_answers.get(question_id)
            correct_answer = question['correct_answer']
            
            is_correct = False
            if user_answer is not None:
                try:
                    user_answer_int = int(user_answer)
                    is_correct = user_answer_int == correct_answer
                    if is_correct:
                        score += 1
                except (ValueError, TypeError):
                    pass

            results.append({
                'question_id': question['id'],
                'question': question['question'],
                'options': question['options'],
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'correct_option': question['options'][correct_answer],
                'user_option': question['options'][int(user_answer)] if user_answer is not None and user_answer.isdigit() and 0 <= int(user_answer) <= 3 else 'No answer',
                'is_correct': is_correct,
                'explanation': question.get('explanation', 'No explanation provided')
            })

        return score, results