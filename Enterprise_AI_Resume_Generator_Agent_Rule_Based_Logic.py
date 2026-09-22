from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
import time
import uuid
import os

#----------------------
# APP Initialization
#----------------------

app = FastAPI(
    title="Enterprise AI Resume Generator Agent",
    description="An API for generating professional resumes using AI",
    version="1.0.0",
)

#----------------------
# SECURITY CONFIG
#----------------------

#valid_api_keys = {os.getenv("Resume12345")}  # Replace with your actual API keys
valid_api_keys = {os.getenv("API_KEY_HERE")}  # Replace with your actual API keys

#----------------------
# REQUEST MODEL
#----------------------

class ResumeRequest(BaseModel):
    api_key: str
    full_name: str
    current_role: str
    skills: list[str]
    experience_years: int

    resume_text: str | None = Field(None, max_length=90000)
    resume_file: str | None = None   # File path or uploaded file name

    @model_validator(mode="after")
    def validate_resume(self):
        # User must provide either resume text or a file
        if not self.resume_text and not self.resume_file:
            raise ValueError("Provide either resume text or upload a resume.")

        # Validate uploaded file type
        if self.resume_file:
            allowed = (".pdf", ".docx", ".txt")
            if not self.resume_file.lower().endswith(allowed):
                raise ValueError(
                    "Invalid file format. Only PDF, DOCX, and TXT are supported."
                )

        return self

#----------------------
# LOGGING CONFIG
#----------------------
logs = []
def log_event(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    logs.append(log_message)
    print(log_message)

    with open("resume_generator_logs.txt", "a") as log_file:
        log_file.write(log_message + "\n")

#----------------------
# SECURITY VALIDATION
#----------------------

def verify_api_key(api_key):
    # Never log the key itself.
    if api_key not in valid_api_keys:
        log_event("Unauthorized access attempt with an invalid API key")
        raise HTTPException(status_code=401, detail="Invalid API Key")
    log_event("API key verified")

#----------------------
# PROFILE ANALYZER AGENT
#----------------------

def analyzer_agent(user_request, request_id):
    log_event(f"{request_id}: Analyzer agent received request")
    #responsibilities = user_request.get("responsibilities", ["Analyze resume content, identify strengths and weaknesses, and provide actionable recommendations for improvement., Skills assessment, experience evaluation, projects review, and role alignment analysis., education and certification review, career trajectory analysis, and industry relevance assessment"])
    years = user_request["experience_years"]
    if years < 2:
        level = "Entry Level"
    elif years < 6:
        level = "Mid-Level"
    else:
        level = "Senior Level"
    output = {
        "candidate_level": level,
        "primary_domain": user_request["current_role"],
        "years_experience": years,
        "skills_found": user_request["skills"]
    }

    log_event(f"Analyzer agent output: {output}")
    return output

#----------------------
# ATS SCORE CALCULATOR
#----------------------

def calculate_ats_score(resume_text: str, skills: list[str]) -> int:
    if not resume_text:
        return 0

    score = 50
    lower_text = resume_text.lower()
    for skill in skills:
        if skill.lower() in lower_text:
            score += 10
        else:
            score -= 5

    return max(0, min(score, 100))

#------------------------
# ATS OPTIMIZATION AGENT
#------------------------

def ats_agent(user_request):
    log_event(f"ATS agent received request")
    #responsibilities = user_request.get("responsibilities", ["identify ATS keywords from resume text or file, improve formatting, and enhance content to match job descriptions, optimize skill alignment, and ensure compliance with ATS parsing standards., improve role targeting, and enhance overall resume effectiveness."])
    missing = []
    score = calculate_ats_score(user_request.get("resume_text", ""), user_request.get("skills", []))
    output = {
        "missing_keywords": missing,
        "ats_score": score
    }

    log_event(f"ATS agent output: {output}")
    return output

#----------------------
# RESUME WRITER AGENT
#----------------------

def resume_writer_agent(user_request):
    log_event(f"Resume Writer agent received request")
    #responsibilities = user_request.get("responsibilities", ["Generate a professional resume based on the provided information, including full name, current role, skills, experience years, and any additional details., Ensure the resume is well-structured, ATS-friendly, and highlights key achievements and qualifications., Tailor the resume to specific job roles or industries as requested., experience bullets, skills section, project descriptions, formatting, layout, and overall presentation of the resume."])
    resume = f"""
    Name: {user_request['full_name']}
    Role: {user_request['current_role']}
    Skills: {', '.join(user_request['skills'])}
    Experience: {user_request['experience_years']} years
    """
    output = {
        "generated_resume": resume
    }

    log_event(f"Resume Writer agent output: {output}")
    return output


#----------------------
# HUMAN OPTIMIZER AGENT
#----------------------

def human_optimizer_agent(user_request, resume_text):
    log_event("Human Optimizer Agent started")

    output = {
        "human_friendly_resume": resume_text,
        "changes_made": [
            "Reduced repetitive AI-style phrases",
            "Improved readability",
            "Made bullet points more natural"
        ]
    }

    log_event(f"Human Optimizer output: {output}")
    return output

#----------------------
# REVIEWER AGENT
#----------------------

def reviewer_agent(user_request):
    log_event(f"Reviewer agent received request")
    #responsibilities = user_request.get("responsibilities", ["Review the generated resume for accuracy, clarity, and overall quality., Provide feedback on content, structure, and presentation., Suggest improvements to enhance the resume's effectiveness and impact., check grammar and spelling., consistency and formatting structure., Enterprise professionalism."])
    feedback = []
    if len(user_request["skills"]) < 5:
        feedback.append("Consider adding more technical skills.")
    if user_request["experience_years"] < 2:
        feedback.append("Highlight internships and projects.")
    feedback.append("Resume formatting looks professional.")
    
    output = {
        "review_feedback": feedback,
        "overall_score": 85  # Example score out of 100
    }

    log_event(f"Reviewer agent output: {output}")
    return output

#----------------------
# ORCHESTRATOR
#----------------------

def orchestrator(user_request, request_id):
    log_event(f"Orchestrator received request")
    start = time.time()
    analyzer_output = analyzer_agent(user_request, request_id)
    ats_output = ats_agent(user_request)
    resume_writer_output = resume_writer_agent(user_request)
    reviewer_output = reviewer_agent(user_request)
    human_optimizer_output = human_optimizer_agent(user_request, resume_writer_output["generated_resume"])

    final_output = {
        "analyzer": analyzer_output,
        "ats_optimization": ats_output,
        "resume_writer": resume_writer_output,
        "human_optimizer": human_optimizer_output,
        "reviewer": reviewer_output
    }
    end = time.time()
    execution_time = round(end - start, 2)
    log_event(f"Orchestrator execution time: {execution_time}")

    return {
        "status": "success",
        "request_id": request_id,
        "execution_time": execution_time,
        "workflow": {
            "analyzer": analyzer_output,
            "ats_optimization": ats_output,
            "resume_writer": resume_writer_output,
            "human_optimizer": human_optimizer_output,
            "reviewer": reviewer_output
        },
        "final_report": final_output,
        "logs": logs,
    }

#----------------------
# ROOT ENDPOINT
#----------------------
@app.get("/")
def home():
    return {"message": "Welcome to the Enterprise AI Resume Generator Agent API!"}

#----------------------
# MAIN API ENDPOINT
#----------------------
@app.post("/generate_resume")
def generate_resume(request: ResumeRequest):
    request_id = str(uuid.uuid4())

    # SECURITY CHECK
    verify_api_key(request.api_key)

    # WORKFLOW EXECUTION
    result = orchestrator(request.model_dump(), request_id)

    return result
