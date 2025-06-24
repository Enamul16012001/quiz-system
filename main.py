import google.generativeai as genai
import json
import re
from typing import Dict, List, Tuple, Optional


class ExamSystem:
    def __init__(self, api_key: str):
        """Initialize the exam system with Gemini API key"""
        genai.configure(api_key=api_key)
        self.generation_config = genai.types.GenerationConfig(
            temperature=0.8
        )
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def generate_exam_questions(self, department: str, position: str, question_structure: Dict) -> Optional[List[Dict]]:
        """Generate exam questions based on department, position and structure"""
        mcq_count = question_structure['mcq_count']
        short_count = question_structure['short_count']
        essay_count = question_structure['essay_count']
        mcq_marks = question_structure['mcq_marks']
        short_marks = question_structure['short_marks']
        essay_marks = question_structure['essay_marks']
        
        prompt = f"""
        Create an exam for the position of {position} in the {department} department.

        Generate exactly:
        - {mcq_count} Multiple Choice Questions (MCQ) - {mcq_marks} marks each
        - {short_count} Short Answer Questions - {short_marks} marks each  
        - {essay_count} Essay/Long Answer Questions - {essay_marks} marks each

        For {position} in {department}, include questions about:
        - Technical skills and knowledge specific to {position}
        - Industry best practices and standards
        - Problem-solving scenarios relevant to {position}
        - Tools and methodologies used in {department}
        - Professional responsibilities and ethics
        - Current trends and challenges in {department}

        Format your response as a JSON array with this exact structure:
        [
            {{
                "type": "mcq",
                "question": "Question text here",
                "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
                "correct_answer": 0,
                "marks": {mcq_marks},
                "explanation": "Brief explanation of why this is correct"
            }},
            {{
                "type": "short",
                "question": "Short answer question text here",
                "marks": {short_marks},
                "expected_answer": "Expected answer or key points",
                "evaluation_criteria": "Criteria for evaluating the answer"
            }},
            {{
                "type": "essay",
                "question": "Essay question text here",
                "marks": {essay_marks},
                "expected_answer": "Expected answer structure and key points",
                "evaluation_criteria": "Detailed criteria for evaluating the essay"
            }}
        ]

        IMPORTANT REQUIREMENTS:
        - All questions must be unique and relevant to {position} in {department}
        - Make questions challenging but fair for the position level
        - For MCQs, correct_answer should be the index (0, 1, 2, or 3) of the correct option
        - For short and essay questions, provide clear evaluation criteria
        - Questions should test different competency levels (knowledge, application, analysis)

        Return only the JSON array, no additional text.
        """

        try:
            print(f"🤖 Generating exam questions for {position} in {department}...")
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
            questions = json.loads(response_text.strip())

            # Validate the structure
            if not self._validate_questions_structure(questions, question_structure):
                print("❌ Questions structure validation failed")
                raise ValueError("Invalid questions structure received from API")

            print("✅ Exam questions generated successfully!")
            return questions

        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {str(e)}")
            print(f"Raw response: {response.text}")
            return None
        except Exception as e:
            print(f"❌ Error generating questions: {str(e)}")
            return None

    def _validate_questions_structure(self, questions: List[Dict], structure: Dict) -> bool:
        """Validate that the questions have the correct structure"""
        try:
            mcq_count = len([q for q in questions if q['type'] == 'mcq'])
            short_count = len([q for q in questions if q['type'] == 'short'])
            essay_count = len([q for q in questions if q['type'] == 'essay'])
            
            if (mcq_count != structure['mcq_count'] or 
                short_count != structure['short_count'] or 
                essay_count != structure['essay_count']):
                return False

            for q in questions:
                required_keys = ['type', 'question', 'marks']
                if not all(key in q for key in required_keys):
                    return False
                
                if q['type'] == 'mcq':
                    if ('options' not in q or 'correct_answer' not in q or 
                        len(q['options']) != 4 or 
                        not isinstance(q['correct_answer'], int) or 
                        q['correct_answer'] not in [0, 1, 2, 3]):
                        return False
                elif q['type'] in ['short', 'essay']:
                    if 'expected_answer' not in q or 'evaluation_criteria' not in q:
                        return False

            return True
        except:
            return False

    def evaluate_exam(self, questions: List[Dict], candidate_answers: Dict) -> Dict:
        """Evaluate candidate answers and return detailed results"""
        total_marks = 0
        obtained_marks = 0
        question_results = []

        for question in questions:
            question_id = str(question['id'])
            candidate_answer = candidate_answers.get(question_id, "")
            
            if question['type'] == 'mcq':
                # Auto-evaluate MCQ
                result = self._evaluate_mcq(question, candidate_answer)
            else:
                # Use LLM to evaluate short/essay answers
                result = self._evaluate_subjective(question, candidate_answer)
            
            total_marks += question['marks']
            obtained_marks += result['marks_obtained']
            question_results.append(result)

        percentage = (obtained_marks / total_marks) * 100 if total_marks > 0 else 0
        
        # Generate overall feedback
        overall_feedback = self._generate_overall_feedback(percentage, question_results)
        
        return {
            'total_marks': total_marks,
            'obtained_marks': obtained_marks,
            'percentage': percentage,
            'question_results': question_results,
            'overall_feedback': overall_feedback,
            'performance_level': self._get_performance_level(percentage)
        }

    def _evaluate_mcq(self, question: Dict, candidate_answer: str) -> Dict:
        """Evaluate MCQ answer"""
        is_correct = False
        marks_obtained = 0
        
        if candidate_answer and candidate_answer.isdigit():
            selected_option = int(candidate_answer)
            is_correct = selected_option == question['correct_answer']
            if is_correct:
                marks_obtained = question['marks']
        
        return {
            'question_id': question['id'],
            'question_type': 'mcq',
            'question_text': question['question'],
            'candidate_answer': candidate_answer,
            'correct_answer': question['correct_answer'],
            'is_correct': is_correct,
            'marks_total': question['marks'],
            'marks_obtained': marks_obtained,
            'feedback': question.get('explanation', 'No explanation provided'),
            'selected_option': question['options'][int(candidate_answer)] if candidate_answer and candidate_answer.isdigit() and 0 <= int(candidate_answer) <= 3 else 'No answer'
        }

    def _evaluate_subjective(self, question: Dict, candidate_answer: str) -> Dict:
        """Evaluate short/essay answer using LLM"""
        if not candidate_answer.strip():
            return {
                'question_id': question['id'],
                'question_type': question['type'],
                'question_text': question['question'],
                'candidate_answer': candidate_answer,
                'marks_total': question['marks'],
                'marks_obtained': 0,
                'feedback': 'No answer provided.',
                'evaluation_details': 'Answer was not provided by the candidate.'
            }

        evaluation_prompt = f"""
        You are an expert examiner. Evaluate the following answer:

        QUESTION: {question['question']}
        QUESTION TYPE: {question['type']}
        TOTAL MARKS: {question['marks']}
        
        EXPECTED ANSWER: {question.get('expected_answer', 'Not provided')}
        EVALUATION CRITERIA: {question.get('evaluation_criteria', 'Standard evaluation criteria')}
        
        CANDIDATE'S ANSWER: {candidate_answer}

        Please evaluate this answer and provide:
        1. Marks out of {question['marks']} (as a number)
        2. Detailed feedback explaining the marks awarded
        3. Areas where the answer could be improved

        Format your response as JSON:
        {{
            "marks_awarded": <number between 0 and {question['marks']}>,
            "feedback": "Detailed feedback explaining the evaluation",
            "strengths": "What the candidate did well",
            "improvements": "Areas for improvement"
        }}

        Be fair but thorough in your evaluation. Consider accuracy, completeness, clarity, and relevance.
        """

        try:
            response = self.model.generate_content(
                evaluation_prompt,
                generation_config=self.generation_config
            )
            
            # Clean and parse response
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            evaluation = json.loads(response_text.strip())
            
            # Validate marks
            marks_awarded = min(max(0, evaluation.get('marks_awarded', 0)), question['marks'])
            
            return {
                'question_id': question['id'],
                'question_type': question['type'],
                'question_text': question['question'],
                'candidate_answer': candidate_answer,
                'marks_total': question['marks'],
                'marks_obtained': marks_awarded,
                'feedback': evaluation.get('feedback', 'Evaluation completed'),
                'strengths': evaluation.get('strengths', ''),
                'improvements': evaluation.get('improvements', ''),
                'evaluation_details': f"AI Evaluation: {evaluation.get('feedback', '')}"
            }
            
        except Exception as e:
            print(f"❌ Error evaluating subjective answer: {str(e)}")
            # Fallback evaluation
            return {
                'question_id': question['id'],
                'question_type': question['type'],
                'question_text': question['question'],
                'candidate_answer': candidate_answer,
                'marks_total': question['marks'],
                'marks_obtained': question['marks'] // 2,  # Give 50% marks as fallback
                'feedback': 'Answer provided but could not be evaluated automatically. Manual review recommended.',
                'evaluation_details': 'Automatic evaluation failed. Please review manually.'
            }

    def _generate_overall_feedback(self, percentage: float, question_results: List[Dict]) -> str:
        """Generate overall feedback for the candidate"""
        if percentage >= 85:
            base_feedback = "Excellent performance! You have demonstrated strong knowledge and understanding."
        elif percentage >= 70:
            base_feedback = "Good performance overall. You have shown solid understanding with room for improvement."
        elif percentage >= 50:
            base_feedback = "Average performance. You have basic understanding but need to strengthen your knowledge."
        else:
            base_feedback = "Below average performance. Significant improvement needed in your preparation."

        # Add specific feedback based on question types
        mcq_correct = len([r for r in question_results if r['question_type'] == 'mcq' and r.get('is_correct', False)])
        mcq_total = len([r for r in question_results if r['question_type'] == 'mcq'])
        
        if mcq_total > 0:
            mcq_percentage = (mcq_correct / mcq_total) * 100
            if mcq_percentage < 60:
                base_feedback += " Focus on improving your theoretical knowledge for multiple choice questions."

        return base_feedback

    def _get_performance_level(self, percentage: float) -> str:
        """Get performance level based on percentage"""
        if percentage >= 85:
            return "Excellent"
        elif percentage >= 70:
            return "Good"
        elif percentage >= 50:
            return "Average"
        else:
            return "Poor"