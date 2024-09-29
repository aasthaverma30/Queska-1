import os
import pathlib
import json
import requests
from flask import Flask, session, abort, redirect, request, url_for, render_template, send_file
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
import stripe  # For Stripe payments
import fitz  # PyMuPDF
import google.generativeai as gga
from fpdf import FPDF
from functools import wraps

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = "CodeSpecialist.com"

# Stripe API configuration (Use your actual secret key)
stripe.api_key = "sk_test_51Q3QnJCZ4K4rrIXQlmC43ZRGFY85pP3QimEXJ4eeDzj9dsu5MXCI1HLtggZNY8AlRHuP5SC25s4jmdoNEUkx5VlT00ZvkWWZ2t"

# Google OAuth 2.0 Setup
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
GOOGLE_CLIENT_ID = "1026031924285-26f8lv2bbrbkcsio5grhbfte99ql3bmt.apps.googleusercontent.com"
client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_uri="http://127.0.0.1:5000/callback"
)

# Google Generative AI API configuration
gga.configure(api_key='AIzaSyD26Re1PMGq9mL8m3R7u2ZeJURG3a9oXLM')

# PDF Reading Function
def read_pdf_lines(file_path):
    pdf_document = fitz.open(file_path)
    lines = []
    for page in pdf_document:
        text = page.get_text("text")
        lines.extend(text.splitlines())
    pdf_document.close()
    return lines

# Function to generate questions using Google Generative AI
def generate_questions(prompt):
    try:
        model = gga.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error in generating questions: {str(e)}"

# Function to save questions to a PDF
def save_question_paper_to_pdf(questions, file_name="question_paper.pdf"):
    if not questions:
        return None  # No questions to save
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        for question in questions:
            pdf.multi_cell(0, 10, txt=question)
        pdf.output(file_name)
        return file_name
    except Exception as e:
        return f"Error in generating PDF: {str(e)}"

# Decorator to ensure login is required
def login_is_required(function):
    @wraps(function)  # Use @wraps to retain the original function's metadata
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return abort(401)  # Authorization required
        return function(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    return render_template("index.html")

# Login Route for Google OAuth
@app.route("/login")
def login():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

# Google OAuth Callback
@app.route("/callback")
def callback():
    try:
        flow.fetch_token(authorization_response=request.url)
        
        if session["state"] != request.args["state"]:
            abort(500, description="State does not match!")
        
        credentials = flow.credentials
        request_session = requests.session()
        cached_session = cachecontrol.CacheControl(request_session)
        token_request = google.auth.transport.requests.Request(session=cached_session)

        id_info = id_token.verify_oauth2_token(
            id_token=credentials._id_token,
            request=token_request,
            audience=GOOGLE_CLIENT_ID
        )

        session["google_id"] = id_info.get("sub")
        session["name"] = id_info.get("name")
        
        return redirect("/payment")
    except Exception as e:
        return str(e), 400

# Stripe Payment Route
@app.route("/payment")
@login_is_required
def payment():
    try:
        session_data = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'AI Question Paper Generator',
                    },
                    'unit_amount': 1399,  # $13.99 in cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('question_generator', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('index', _external=True),
        )
        return redirect(session_data.url, code=303)
    except stripe.error.StripeError as e:
        return str(e), 400  # Handle Stripe errors properly

# Question Generation Route (Protected Area)
@app.route("/question_generator", methods=["GET", "POST"])
@login_is_required
def question_generator():
    if request.method == "POST":
        uploaded_file = request.files['file']
        if uploaded_file and uploaded_file.filename.endswith('.pdf'):
            file_path = os.path.join("uploads", uploaded_file.filename)
            uploaded_file.save(file_path)
            lines = read_pdf_lines(file_path)
            topics = "\n".join(lines)

            prompt = f'''
                Instructions for Question Generation:

        You are a highly intelligent AI designed to create educational content. Your task is to generate thoughtful and varied questions based on the syllabus provided below. The questions should cover a range of difficulty levels (easy, medium, and hard) and different types (multiple choice, short answer, and essay questions). Ensure that the questions are clear, concise, and directly related to the syllabus content.

        Syllabus:{topics}

        Requirements:
            Generate a total of 5 questions from each Unit given in the syllabus.
            Ensure the questions vary in difficulty.
            Questions should encourage critical thinking and application of knowledge.

        End of Instructions.
            '''
            output = generate_questions(prompt)
            questions = output.split('\n')

            pdf_file = save_question_paper_to_pdf(questions)
            return send_file(pdf_file, as_attachment=True)

    return render_template("inner_index.html")

# Logout Route
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    if not os.path.exists("uploads"):
        os.makedirs("uploads")
    app.run(debug=True)