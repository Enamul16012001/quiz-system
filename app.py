from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Dict, Optional
import json
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta

from main import JobQuizSystem, DEPARTMENTS  # Import DEPARTMENTS from main.py
from db import db

app = FastAPI(title="Job Department Quiz System")

templates = Jinja2Templates(directory="templates", auto_reload=True)

# Configuration
API_KEY = "AIzaSyAsxe-O0Md2OuXAcYNxf7Czs0WB8dyBk7Y"  # Replace with your actual API key
ADMIN_SECRET_KEY = "quiz_admin_2024"  # Change this to your desired secret key
ADMIN_SESSION_TIMEOUT = 30  # Session timeout in minutes

# Initialize quiz system
quiz_system = JobQuizSystem(API_KEY)

# In-memory storage for quiz sessions and admin sessions
quiz_sessions = {}
admin_sessions = {}

# Security
security = HTTPBasic()

class QuizSession(BaseModel):
    session_id: str
    name: str
    user_id: str
    department: str
    quiz_data: Dict
    created_at: datetime

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
    """Home page with user information form"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": DEPARTMENTS
    })

@app.post("/start-quiz", response_class=HTMLResponse)
async def start_quiz(
    request: Request,
    name: str = Form(...),
    user_id: str = Form(...),
    department: str = Form(...),
    custom_department: str = Form("")
):
    """Start a new quiz session"""
    # Use custom department if provided
    if department == "custom" and custom_department.strip():
        department = custom_department.strip()
    elif department == "custom":
        return templates.TemplateResponse("index.html", {
            "request": request,
            "departments": DEPARTMENTS,
            "error": "Please enter a custom department name."
        })
    
    # Generate quiz
    quiz_data = quiz_system.generate_quiz(department)
    
    if not quiz_data:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "departments": DEPARTMENTS,
            "error": "Failed to generate quiz. Please check your API key and try again."
        })
    
    # Create quiz session
    session_id = str(uuid.uuid4())
    quiz_sessions[session_id] = QuizSession(
        session_id=session_id,
        name=name,
        user_id=user_id,
        department=department,
        quiz_data=quiz_data,
        created_at=datetime.now()
    )
    
    return templates.TemplateResponse("quiz.html", {
        "request": request,
        "session_id": session_id,
        "name": name,
        "user_id": user_id,
        "department": department,
        "quiz_data": quiz_data
    })

@app.post("/submit-quiz", response_class=HTMLResponse)
async def submit_quiz(request: Request):
    """Submit quiz answers and show results"""
    form_data = await request.form()
    session_id = form_data.get("session_id")
    time_taken = form_data.get("time_taken", "00:00")  # Get time taken from form
    
    if not session_id or session_id not in quiz_sessions:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    
    session = quiz_sessions[session_id]
    
    # Extract user answers
    user_answers = {}
    for key, value in form_data.items():
        if key.startswith("question_"):
            question_id = key.replace("question_", "")
            user_answers[question_id] = value
    
    # Calculate score
    score, results = quiz_system.calculate_score(session.quiz_data, user_answers)
    total_questions = len(session.quiz_data['questions'])
    percentage = (score / total_questions) * 100
    
    # Performance message
    if percentage >= 80:
        performance_msg = "🎉 Excellent performance!"
        performance_class = "excellent"
    elif percentage >= 60:
        performance_msg = "👍 Good job!"
        performance_class = "good"
    elif percentage >= 40:
        performance_msg = "📖 Room for improvement."
        performance_class = "average"
    else:
        performance_msg = "📚 Consider additional study."
        performance_class = "poor"
    
    # Save user information to database
    db.save_user(session.user_id, session.name)
    
    # Save complete quiz session to database
    db_save_success = db.save_quiz_session(
        session_id=session_id,
        user_id=session.user_id,
        name=session.name,
        department=session.department,
        quiz_data=session.quiz_data,
        results=results,
        score=score,
        time_taken=time_taken
    )
    
    if not db_save_success:
        print("⚠️ Warning: Failed to save quiz results to database")
    
    # Clean up session from memory after saving to database
    if session_id in quiz_sessions:
        del quiz_sessions[session_id]
    
    return templates.TemplateResponse("results.html", {
        "request": request,
        "name": session.name,
        "user_id": session.user_id,
        "department": session.department,
        "score": score,
        "total_questions": total_questions,
        "percentage": percentage,
        "performance_msg": performance_msg,
        "performance_class": performance_class,
        "results": results,
        "time_taken": time_taken
    })

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now()}

@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify API is working"""
    return {"message": "API is working", "timestamp": datetime.now()}

@app.get("/api/test-admin")
async def test_admin_endpoint(session_id: str = Depends(verify_admin_access)):
    """Test admin-protected endpoint"""
    return {"message": "Admin API is working", "session_id": session_id, "timestamp": datetime.now()}

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Admin login page"""
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request, secret_key: str = Form(...)):
    """Process admin login"""
    if secret_key == ADMIN_SECRET_KEY:
        # Create admin session
        session_id = create_admin_session()
        
        # Redirect to admin dashboard with session cookie
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(
            key="admin_session",
            value=session_id,
            max_age=ADMIN_SESSION_TIMEOUT * 60,  # Convert to seconds
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
        return response
    else:
        # Invalid secret key
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
    """Admin dashboard to view all quiz results (protected)"""
    all_results = db.get_all_quiz_results(50)  # Get last 50 results
    db_info = db.get_database_info()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "results": all_results,
        "db_info": db_info,
        "departments": DEPARTMENTS
    })

# Protect all admin API endpoints
@app.get("/api/user-history/{user_id}")
async def get_user_history(user_id: str, session_id: str = Depends(verify_admin_access)):
    """Get quiz history for a specific user (protected)"""
    history = db.get_user_quiz_history(user_id)
    return {"user_id": user_id, "history": history}

@app.get("/api/quiz-details/{quiz_session_id}")
async def get_quiz_details(quiz_session_id: str, session_id: str = Depends(verify_admin_access)):
    """Get detailed results for a specific quiz session (protected)"""
    details = db.get_quiz_details(quiz_session_id)
    if not details:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    return details

@app.get("/api/all-results")
async def get_all_results(limit: int = 100, session_id: str = Depends(verify_admin_access)):
    """Get all quiz results with pagination (protected)"""
    results = db.get_all_quiz_results(limit)
    return {"results": results, "total": len(results)}

@app.get("/api/department-stats/{department}")
async def get_department_statistics(department: str, session_id: str = Depends(verify_admin_access)):
    """Get statistics for a specific department (protected)"""
    stats = db.get_department_statistics(department)
    if not stats:
        raise HTTPException(status_code=404, detail="No data found for this department")
    return stats

@app.get("/api/database-info")
async def get_database_info(session_id: str = Depends(verify_admin_access)):
    """Get general database information (protected)"""
    info = db.get_database_info()
    return info

@app.delete("/api/quiz-session/{quiz_session_id}")
async def delete_quiz_session(quiz_session_id: str, session_id: str = Depends(verify_admin_access)):
    """Delete a quiz session and all related data (protected)"""
    success = db.delete_quiz_session(quiz_session_id)
    if success:
        return {"message": "Quiz session deleted successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete quiz session")

# Optional: API endpoint to get available departments
@app.get("/api/departments")
async def get_departments():
    """Get list of available departments"""
    return {"departments": DEPARTMENTS}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7902)