from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Dict, Optional, List
import json
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta


from main import ExamSystem
from db import db

app = FastAPI(title="Admin-Controlled Exam System")

templates = Jinja2Templates(directory="templates", auto_reload=True)

# Configuration
API_KEY = "AIzaSyAsxe-O0Md2OuXAcYNxf7Czs0WB8dyBk7Y"  # Replace with your actual API key
ADMIN_SECRET_KEY = "exam_admin_2025"  # Change this to your desired secret key
ADMIN_SESSION_TIMEOUT = 30  # Session timeout in minutes

# Initialize exam system
exam_system = ExamSystem(API_KEY)

# In-memory storage for exam sessions and admin sessions
exam_sessions = {}
admin_sessions = {}

# Security
security = HTTPBasic()

class ExamSession(BaseModel):
    session_id: str
    candidate_name: str
    candidate_id: str
    exam_id: str
    started_at: datetime
    time_limit: int  # in minutes

class AdminSession(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime

def create_admin_session() -> str:
    """Create a new admin session"""
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(minutes=ADMIN_SESSION_TIMEOUT)
    
    admin_sessions[session_id] = AdminSession(
        session_id=session_id,
        created_at=datetime.now(),
        expires_at=expires_at
    )
    return session_id

def verify_admin_session(session_id: str) -> bool:
    """Verify if admin session is valid and not expired"""
    if session_id not in admin_sessions:
        return False
    
    session = admin_sessions[session_id]
    if datetime.now() > session.expires_at:
        # Session expired, remove it
        del admin_sessions[session_id]
        return False
    
    # Extend session
    session.expires_at = datetime.now() + timedelta(minutes=ADMIN_SESSION_TIMEOUT)
    return True

def get_admin_session_from_request(request: Request) -> Optional[str]:
    """Get admin session ID from request cookies"""
    return request.cookies.get("admin_session")

async def verify_admin_access(request: Request):
    """Dependency to verify admin access"""
    session_id = get_admin_session_from_request(request)
    if not session_id or not verify_admin_session(session_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access required"
        )
    return session_id

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page for candidates"""
    return templates.TemplateResponse("candidate_home.html", {
        "request": request
    })

@app.get("/exam/{exam_link}", response_class=HTMLResponse)
async def exam_page(request: Request, exam_link: str):
    """Exam page for candidates"""
    exam = db.get_exam_by_link(exam_link)
    if not exam:
        return templates.TemplateResponse("candidate_home.html", {
            "request": request,
            "error": "This exam is either invalid, has been deactivated, or is no longer available. Please contact the administrator for assistance."
        })
    
    return templates.TemplateResponse("exam_start.html", {
        "request": request,
        "exam": exam,
        "exam_link": exam_link
    })

@app.post("/exam/{exam_link}/start", response_class=HTMLResponse)
async def start_exam(
    request: Request,
    exam_link: str
):
    """Start exam for candidate"""
    exam = db.get_exam_by_link(exam_link)
    if not exam:
        return templates.TemplateResponse("candidate_home.html", {
            "request": request,
            "error": "Invalid exam link. Please check the link and try again."
        })
    
    # Get form data
    form_data = await request.form()
    candidate_name = form_data.get("candidate_name", "").strip()
    candidate_id = form_data.get("candidate_id", "").strip()
    
    # Validate form data
    if not candidate_name or not candidate_id:
        return templates.TemplateResponse("exam_start.html", {
            "request": request,
            "exam": exam,
            "exam_link": exam_link,
            "error": "Please fill in both your name and candidate ID."
        })
    
    # Create exam session
    session_id = str(uuid.uuid4())
    exam_sessions[session_id] = ExamSession(
        session_id=session_id,
        candidate_name=candidate_name,
        candidate_id=candidate_id,
        exam_id=exam['id'],
        started_at=datetime.now(),
        time_limit=exam['time_limit']
    )
    
    # Get questions for the exam
    questions = db.get_exam_questions(exam['id'])
    
    return templates.TemplateResponse("exam_page.html", {
        "request": request,
        "session_id": session_id,
        "candidate_name": candidate_name,
        "candidate_id": candidate_id,
        "exam": exam,
        "questions": questions
    })

@app.post("/exam/submit", response_class=HTMLResponse)
async def submit_exam(request: Request):
    """Submit exam answers"""
    form_data = await request.form()
    session_id = form_data.get("session_id")
    time_taken = form_data.get("time_taken", "00:00")
    
    if not session_id or session_id not in exam_sessions:
        raise HTTPException(status_code=404, detail="Exam session not found")
    
    session = exam_sessions[session_id]
    exam = db.get_exam_by_id(session.exam_id)
    questions = db.get_exam_questions(session.exam_id)
    
    # Extract candidate answers
    candidate_answers = {}
    for key, value in form_data.items():
        if key.startswith("question_"):
            question_id = key.replace("question_", "")
            candidate_answers[question_id] = value
    
    # Evaluate answers using ExamSystem
    evaluation_result = exam_system.evaluate_exam(questions, candidate_answers)
    
    # Save results to database
    db.save_exam_result(
        session_id=session_id,
        exam_id=session.exam_id,
        candidate_name=session.candidate_name,
        candidate_id=session.candidate_id,
        answers=candidate_answers,
        evaluation=evaluation_result,
        time_taken=time_taken
    )
    
    # Clean up session
    if session_id in exam_sessions:
        del exam_sessions[session_id]
    
    return templates.TemplateResponse("candidate_results.html", {
        "request": request,
        "candidate_name": session.candidate_name,
        "candidate_id": session.candidate_id,
        "exam_title": exam['title'],
        "evaluation": evaluation_result,
        "time_taken": time_taken
    })

# Admin Routes
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Admin login page"""
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request, secret_key: str = Form(...)):
    """Process admin login"""
    if secret_key == ADMIN_SECRET_KEY:
        session_id = create_admin_session()
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(
            key="admin_session",
            value=session_id,
            max_age=ADMIN_SESSION_TIMEOUT * 60,
            httponly=True,
            secure=False,
            samesite="lax"
        )
        return response
    else:
        return templates.TemplateResponse("admin_login.html", {
            "request": request,
            "error": "Invalid secret key. Please try again."
        })

@app.get("/admin/logout")
async def admin_logout(request: Request):
    """Logout admin user"""
    session_id = get_admin_session_from_request(request)
    if session_id and session_id in admin_sessions:
        del admin_sessions[session_id]
    
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("admin_session")
    return response

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, session_id: str = Depends(verify_admin_access)):
    """Admin dashboard"""
    try:
        exams = db.get_all_exams()
        recent_results = db.get_recent_exam_results(20)
        
        # Debug: Print exam data to see the structure
        print("=== ADMIN DASHBOARD DEBUG ===")
        print(f"Number of exams found: {len(exams)}")
        for exam in exams:
            print(f"Exam: {exam.get('title')} - Finalized: {exam.get('is_finalized')} - Active: {exam.get('is_active')}")
        print(f"Number of recent results: {len(recent_results)}")
        print("=============================")
        
        return templates.TemplateResponse("simple_admin_dashboard.html", {
            "request": request,
            "exams": exams,
            "recent_results": recent_results
        })
    except Exception as e:
        print(f"❌ Error in admin dashboard: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return a simple error page
        return HTMLResponse(f"""
        <html>
        <body>
            <h1>Admin Dashboard Error</h1>
            <p>Error: {str(e)}</p>
            <p><a href="/admin/login">Back to Login</a></p>
            <pre>{traceback.format_exc()}</pre>
        </body>
        </html>
        """, status_code=500)

@app.get("/admin/create-exam", response_class=HTMLResponse)
async def create_exam_page(request: Request, session_id: str = Depends(verify_admin_access)):
    """Create new exam page"""
    return templates.TemplateResponse("create_exam.html", {
        "request": request
    })

@app.post("/admin/create-exam", response_class=HTMLResponse)
async def create_exam(
    request: Request,
    session_id: str = Depends(verify_admin_access)
):
    """Create exam and generate questions"""
    # Get form data
    form_data = await request.form()
    
    # Extract form fields
    try:
        department = form_data.get("department", "").strip()
        position = form_data.get("position", "").strip()
        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip()
        
        # Convert numeric fields with defaults
        mcq_count = int(form_data.get("mcq_count", "0"))
        short_count = int(form_data.get("short_count", "0"))
        essay_count = int(form_data.get("essay_count", "0"))
        mcq_marks = int(form_data.get("mcq_marks", "1"))
        short_marks = int(form_data.get("short_marks", "5"))
        essay_marks = int(form_data.get("essay_marks", "10"))
        time_limit = int(form_data.get("time_limit", "60"))
        instructions = form_data.get("instructions", "").strip()
        
        # Validate required fields
        if not department or not position or not title:
            return templates.TemplateResponse("create_exam.html", {
                "request": request,
                "error": "Please fill in all required fields: Department, Position, and Title."
            })
        
        # Validate at least one question type
        if mcq_count + short_count + essay_count == 0:
            return templates.TemplateResponse("create_exam.html", {
                "request": request,
                "error": "Please specify at least one question type with count greater than 0."
            })
            
    except (ValueError, TypeError) as e:
        return templates.TemplateResponse("create_exam.html", {
            "request": request,
            "error": f"Invalid input format: {str(e)}"
        })
    # Generate questions using LLM
    question_structure = {
        'mcq_count': mcq_count,
        'short_count': short_count,
        'essay_count': essay_count,
        'mcq_marks': mcq_marks,
        'short_marks': short_marks,
        'essay_marks': essay_marks
    }
    
    generated_questions = exam_system.generate_exam_questions(
        department, position, question_structure
    )
    
    if not generated_questions:
        return templates.TemplateResponse("create_exam.html", {
            "request": request,
            "error": "Failed to generate questions. Please try again."
        })
    
    # Create exam in database
    exam_id = db.create_exam(
        title=title,
        department=department,
        position=position,
        description=description,
        time_limit=time_limit,
        instructions=instructions,
        question_structure=question_structure
    )
    
    # Save generated questions
    for question in generated_questions:
        db.save_exam_question(exam_id, question)
    
    return RedirectResponse(url=f"/admin/edit-exam/{exam_id}", status_code=303)

@app.get("/admin/edit-exam/{exam_id}", response_class=HTMLResponse)
async def edit_exam_page(request: Request, exam_id: str, session_id: str = Depends(verify_admin_access)):
    """Edit exam questions page"""
    exam = db.get_exam_by_id(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    questions = db.get_exam_questions(exam_id)
    
    return templates.TemplateResponse("edit_exam.html", {
        "request": request,
        "exam": exam,
        "questions": questions
    })

@app.post("/admin/finalize-exam/{exam_id}")
async def finalize_exam(exam_id: str, session_id: str = Depends(verify_admin_access)):
    """Finalize exam and generate link"""
    exam_link = db.finalize_exam(exam_id)
    return {"success": True, "exam_link": exam_link}

@app.get("/admin/exam-results/{exam_id}", response_class=HTMLResponse)
async def exam_results(request: Request, exam_id: str, session_id: str = Depends(verify_admin_access)):
    """View exam results"""
    exam = db.get_exam_by_id(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    results = db.get_exam_results(exam_id)
    
    return templates.TemplateResponse("exam_results.html", {
        "request": request,
        "exam": exam,
        "results": results
    })

# API Endpoints
@app.post("/api/update-question/{question_id}")
async def update_question(
    question_id: str,
    request: Request,
    session_id: str = Depends(verify_admin_access)
):
    """Update a question"""
    try:
        question_data = await request.json()
        success = db.update_question(question_id, question_data)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/delete-question/{question_id}")
async def delete_question(question_id: str, session_id: str = Depends(verify_admin_access)):
    """Delete a question"""
    try:
        success = db.delete_question(question_id)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/add-question/{exam_id}")
async def add_question(
    exam_id: str,
    request: Request,
    session_id: str = Depends(verify_admin_access)
):
    """Add a new question to exam"""
    try:
        question_data = await request.json()
        question_id = db.save_exam_question(exam_id, question_data)
        return {"success": True, "question_id": question_id}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/admin/download-result")
async def download_result_pdf(request: Request, session_id: str = Depends(verify_admin_access)):
    """Generate and download PDF for a specific result"""
    try:
        form_data = await request.form()
        result_id = form_data.get("result_id")
        
        if not result_id:
            raise HTTPException(status_code=400, detail="Result ID is required")
        
        # Get result details
        result_details = db.get_result_details(result_id)
        if not result_details:
            raise HTTPException(status_code=404, detail="Result not found")
        
        # Generate HTML content for PDF
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Exam Results - {result_details['candidate_name']}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                .header {{ text-align: center; margin-bottom: 30px; border-bottom: 2px solid #333; padding-bottom: 20px; }}
                .info {{ background: #f5f5f5; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
                .question {{ margin-bottom: 25px; border: 1px solid #ddd; padding: 15px; border-radius: 8px; }}
                .question-header {{ background: #e9ecef; padding: 10px; margin: -15px -15px 15px -15px; font-weight: bold; }}
                .answer {{ background: #f8f9fa; padding: 10px; border-left: 4px solid #007bff; margin: 10px 0; }}
                .marks {{ float: right; background: #28a745; color: white; padding: 5px 10px; border-radius: 4px; }}
                .feedback {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; margin-top: 10px; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Exam Results Report</h1>
                <h2>{result_details['exam_title']}</h2>
                <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="info">
                <h3>Candidate Information</h3>
                <p><strong>Name:</strong> {result_details['candidate_name']}</p>
                <p><strong>ID:</strong> {result_details['candidate_id']}</p>
                <p><strong>Department:</strong> {result_details['department']}</p>
                <p><strong>Position:</strong> {result_details['position']}</p>
                <p><strong>Score:</strong> {result_details['obtained_marks']}/{result_details['total_marks']} ({result_details['percentage']:.1f}%)</p>
                <p><strong>Performance Level:</strong> {result_details['performance_level']}</p>
                <p><strong>Time Taken:</strong> {result_details['time_taken']}</p>
                <p><strong>Submitted At:</strong> {result_details['submitted_at']}</p>
            </div>
            
            <h3>📝 Question-wise Performance</h3>
        """
        
        # Add questions
        for i, question in enumerate(result_details['questions'], 1):
            is_correct = question.get('is_correct', False) or (question.get('marks_obtained', 0) == question.get('marks_total', 0))
            
            html_content += f"""
            <div class="question">
                <div class="question-header">
                    Question {i} ({question['question_type'].upper()})
                    <span class="marks">{question.get('marks_obtained', 0)}/{question.get('marks_total', 0)} marks</span>
                </div>
                
                <p><strong>Question:</strong> {question['question_text']}</p>
                
                <div class="answer">
                    <strong>Student Answer:</strong><br>
                    {question.get('candidate_answer', 'No answer provided')}
                </div>
            """
            
            if question['question_type'] == 'mcq' and not is_correct:
                html_content += f"""
                <div class="answer">
                    <strong>Correct Answer:</strong><br>
                    {question.get('correct_option', 'N/A')}
                </div>
                """
            
            if question.get('feedback'):
                html_content += f"""
                <div class="feedback">
                    <strong>💡 Feedback:</strong><br>
                    {question['feedback']}
                </div>
                """
            
            html_content += "</div>"
        
        html_content += """
            </body>
        </html>
        """
        
        # Create filename
        safe_name = "".join(c for c in result_details['candidate_name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"exam_result_{safe_name}_{result_id[:8]}.html"
        
        # Return as downloadable HTML file
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        print(f"❌ Error generating PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")

@app.get("/admin/debug-templates")
async def debug_templates(session_id: str = Depends(verify_admin_access)):
    """Debug route to check what templates and routes we have"""
    import os
    
    # Check what templates exist
    templates_dir = "templates"
    templates = []
    if os.path.exists(templates_dir):
        templates = [f for f in os.listdir(templates_dir) if f.endswith('.html')]
    
    # Get some sample result data
    exams = db.get_all_exams()
    sample_exam = exams[0] if exams else None
    sample_results = []
    
    if sample_exam:
        sample_results = db.get_exam_results(sample_exam['id'])
    
    return {
        "templates_found": templates,
        "sample_exam": sample_exam,
        "sample_results": sample_results[:2] if sample_results else [],
        "routes_that_should_exist": [
            "/admin/exam-results/{exam_id}",
            "/api/result-details/{result_id}",
            "/admin/download-result"
        ]
    }

@app.get("/admin/test-view/{result_id}")
async def test_view_result(result_id: str, session_id: str = Depends(verify_admin_access)):
    """Test endpoint to directly test result viewing"""
    try:
        details = db.get_result_details(result_id)
        return {
            "success": details is not None,
            "result_id": result_id,
            "has_data": details is not None,
            "candidate_name": details.get('candidate_name') if details else None,
            "question_count": len(details.get('questions', [])) if details else 0,
            "full_data": details
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/admin/test-results/{result_id}")
async def test_result_details(result_id: str, session_id: str = Depends(verify_admin_access)):
    """Test endpoint to check result details"""
    try:
        details = db.get_result_details(result_id)
        return {
            "success": details is not None,
            "result_id": result_id,
            "data": details
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/result-details/{result_id}")
async def get_result_details(result_id: str, session_id: str = Depends(verify_admin_access)):
    """Get detailed results for a specific candidate"""
    try:
        print(f"🔍 Fetching result details for ID: {result_id}")
        details = db.get_result_details(result_id)
        if not details:
            print(f"❌ No result found for ID: {result_id}")
            raise HTTPException(status_code=404, detail="Result not found")
        
        print(f"✅ Result details found: {details['candidate_name']}")
        return details
    except Exception as e:
        print(f"❌ Error in get_result_details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/toggle-exam-status/{exam_id}")
async def toggle_exam_status(exam_id: str, request: Request, session_id: str = Depends(verify_admin_access)):
    """Toggle exam active/inactive status"""
    try:
        data = await request.json()
        is_active = data.get('is_active', True)
        success = db.toggle_exam_status(exam_id, is_active)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/update-question-marks")
async def update_question_marks(request: Request, session_id: str = Depends(verify_admin_access)):
    """Update marks for a specific question"""
    try:
        data = await request.json()
        question_id = data.get('question_id')
        result_id = data.get('result_id')
        new_marks = float(data.get('new_marks', 0))
        
        success = db.update_question_marks(question_id, result_id, new_marks)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/delete-exam/{exam_id}")
async def delete_exam(exam_id: str, session_id: str = Depends(verify_admin_access)):
    """Delete an exam and all related data"""
    try:
        success = db.delete_exam(exam_id)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/admin/simple")
async def simple_admin_page(session_id: str = Depends(verify_admin_access)):
    """Simple admin page for testing"""
    try:
        exams = db.get_all_exams()
        return {
            "status": "success",
            "exams_count": len(exams),
            "exams": exams[:3],  # Show first 3 exams
            "message": "If you see this, the backend is working"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/admin/debug-exams")
async def debug_exams(session_id: str = Depends(verify_admin_access)):
    """Debug endpoint to check exam statuses"""
    try:
        import sqlite3
        with sqlite3.connect("exam_system.db") as conn:
            cursor = conn.cursor()
            
            # Check if is_active column exists
            try:
                cursor.execute("SELECT id, title, is_finalized, is_active FROM exams")
                exams = cursor.fetchall()
                
                result = {"exams": []}
                for exam in exams:
                    result["exams"].append({
                        "id": exam[0],
                        "title": exam[1],
                        "is_finalized": exam[2],
                        "is_active": exam[3]
                    })
                
                return result
                
            except sqlite3.OperationalError as e:
                return {"error": f"Column issue: {str(e)}", "suggestion": "Run migration"}
                
    except Exception as e:
        return {"error": str(e)}

@app.post("/admin/fix-exam-statuses")
async def fix_exam_statuses(session_id: str = Depends(verify_admin_access)):
    """Fix all finalized exams to be active"""
    try:
        import sqlite3
        with sqlite3.connect("exam_system.db") as conn:
            cursor = conn.cursor()
            
            # Update all finalized exams to be active
            cursor.execute("UPDATE exams SET is_active = TRUE WHERE is_finalized = TRUE")
            affected_rows = cursor.rowcount
            conn.commit()
            
            return {"success": True, "updated_exams": affected_rows}
            
    except Exception as e:
        return {"error": str(e)}
    
@app.post("/api/update-result-info")
async def update_result_info(request: Request, session_id: str = Depends(verify_admin_access)):
    """Update basic result information (candidate name, ID, time taken)"""
    try:
        data = await request.json()
        result_id = data.get('result_id')
        candidate_name = data.get('candidate_name')
        candidate_id = data.get('candidate_id')
        time_taken = data.get('time_taken')
        
        if not result_id:
            raise HTTPException(status_code=400, detail="Result ID is required")
        
        success = db.update_result_info(result_id, candidate_name, candidate_id, time_taken)
        return {"success": success}
    except Exception as e:
        print(f"❌ Error updating result info: {str(e)}")
        return {"success": False, "error": str(e)}

@app.get("/api/get-result-summary/{result_id}")
async def get_result_summary(result_id: str, session_id: str = Depends(verify_admin_access)):
    """Get quick summary of a result for editing"""
    try:
        summary = db.get_result_summary(result_id)
        if not summary:
            raise HTTPException(status_code=404, detail="Result not found")
        return summary
    except Exception as e:
        print(f"❌ Error getting result summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7902)