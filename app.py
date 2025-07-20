from flask import Flask, render_template, request, redirect, url_for, session
from openai import OpenAI
from werkzeug.utils import secure_filename
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from fuzzywuzzy import fuzz
from supabase import create_client, Client
import os
import re
import spacy

# --- Configuration ---
app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'resumes'
ALLOWED_EXTENSIONS = {'txt'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client = OpenAI(api_key="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")

# Supabase Setup
SUPABASE_URL = "https://gnfwahadltthkzygxhed.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImduZndhaGFkbHR0aGt6eWd4aGVkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI5OTA0OTYsImV4cCI6MjA2ODU2NjQ5Nn0.QDfLkXpgbuqZxLWOY-AsPD9XehHe3NVWfengMAhak9M"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ML models
model = SentenceTransformer('all-MiniLM-L6-v2')
nlp = spacy.load("en_core_web_sm")

SKILL_DATABASE = [
    'python', 'java', 'c++', 'html', 'css', 'javascript', 'js', 'c',
    'machine learning', 'deep learning', 'data analysis', 'sql',
    'flask', 'django', 'git', 'communication', 'problem solving',
    'teamwork', 'data science', 'nlp', 'excel', 'power bi'
]
SYNONYM_MAP = {'js': 'javascript', 'ml': 'machine learning', 'ds': 'data science', 'c': 'c++', 'cpp': 'c++'}

# --- Utility Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_text(text):
    return re.findall(r'\b\w+\b', text.lower())

def extract_skills(text):
    words = normalize_text(text)
    merged = ' '.join(words)
    extracted = set()
    for skill in SKILL_DATABASE:
        if ' ' in skill and skill in merged:
            extracted.add(skill)
        elif skill in words:
            extracted.add(skill)
    return list(extracted)

def calculate_skill_similarity(resume_skills, jd_skills):
    if not resume_skills or not jd_skills:
        return 0.0
    resume_vecs = model.encode(resume_skills)
    jd_vecs = model.encode(jd_skills)
    total_score = sum(max(cosine_similarity([jd], resume_vecs)[0]) for jd in jd_vecs)
    return round((total_score / len(jd_skills)) * 100, 2)

def missing_skills(resume_skills, jd_skills):
    return list(set(jd_skills) - set(resume_skills))

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    companies = supabase.table("companies").select("name").execute().data

    
    if request.method == "POST":
        company = request.form["company"]
        resume = request.files["resume"]
        if resume and allowed_file(resume.filename):
            filename = secure_filename(resume.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            resume.save(path)
            session["resume_path"] = path
            session["selected_company"] = company
            return redirect(url_for("compare"))

    return render_template("index.html", companies=[c["name"] for c in companies])  # Capital 'Name'

@app.route("/company-login", methods=["GET", "POST"])
def company_login():
    companies_data = supabase.table("companies").select("name").execute().data
    companies = [c["name"] for c in companies_data]

    if request.method == "POST":
        name = request.form["company"]
        password = request.form["password"]
        response = supabase.table("companies").select("*").eq("name", name).eq("password", password).execute()
        if response.data:
            session["company_logged_in"] = name
            return redirect(url_for("company_upload"))
        return render_template("company_login.html", error="Invalid credentials", companies=companies)

    return render_template("company_login.html", companies=companies)


@app.route("/company-register", methods=["GET", "POST"])
def company_register():
    if request.method == "POST":
        name = request.form["new_company"]
        password = request.form["new_password"]
        jd = request.form["jd"]
        if not (name and password and jd):
            return render_template("company_register.html", error="All fields required.")
        supabase.table("companies").insert({"name": name, "password": password, "jd": jd}).execute()
        session["company_logged_in"] = name
        return redirect(url_for("company_upload"))
    return render_template("company_register.html")

@app.route("/company-upload", methods=["GET", "POST"])
def company_upload():
    company = session.get("company_logged_in")
    if not company:
        return redirect(url_for("company_login"))
    if request.method == "POST":
        jd = request.form["jd"]
        supabase.table("companies").update({"jd": jd}).eq("name", company).execute()
        return render_template("company_upload.html", success="JD uploaded!", company=company)
    return render_template("company_upload.html", company=company)

@app.route("/compare")
def compare():
    resume_path = session.get("resume_path")
    company = session.get("selected_company")
    if not (resume_path and company):
        return redirect(url_for("index"))

    with open(resume_path, "r", encoding="utf-8", errors="ignore") as f:
        resume_text = f.read()

    jd_data = supabase.table("companies").select("jd").eq("name", company).execute()
    if not jd_data.data:
        return f"No JD uploaded for {company}"
    jd_text = jd_data.data[0]["jd"]

    resume_skills = extract_skills(resume_text)
    jd_skills = extract_skills(jd_text)
    similarity = calculate_skill_similarity(resume_skills, jd_skills)
    missing = missing_skills(resume_skills, jd_skills)

    return render_template("result.html", company=company, resume_skills=resume_skills, jd_skills=jd_skills, similarity=similarity, missing=missing)

@app.route("/chat", methods=["GET", "POST"])
def chat():
    resume_path = session.get("resume_path")
    company = session.get("selected_company")
    resume_text = jd_text = ""

    if resume_path:
        with open(resume_path, "r", encoding="utf-8", errors="ignore") as f:
            resume_text = f.read()

    jd_data = supabase.table("companies").select("jd").eq("name", company).execute()
    if jd_data.data:
        jd_text = jd_data.data[0]["jd"]

    if request.method == "POST":
        user_question = request.form.get("question", "").strip()
        if not user_question:
            return render_template("chat.html", error="Please enter a question.")

        prompt = f"""
You are a helpful assistant that evaluates resumes against job descriptions.

Job Description:
{jd_text}

Resume:
{resume_text}

User Question: {user_question}

Provide clear and helpful feedback.
        """

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.choices[0].message.content.strip()
            return render_template("chat.html", answer=answer, question=user_question)
        except Exception as e:
            return render_template("chat.html", error=f"OpenAI Error: {str(e)}")

    return render_template("chat.html")

if __name__ == "__main__":
    app.run(debug=True)
