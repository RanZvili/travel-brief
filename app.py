"""
Travel Brief Web App
Run locally:  python app.py
Deploy:       Railway / Render (set GEMINI_API_KEY env var)

Uses background threading + polling to avoid proxy/gateway timeouts.
"""

import os
import uuid
import threading
from flask import Flask, request, Response, jsonify
from travel_agent import run_agent, generate_html

app = Flask(__name__)

# In-memory job store  {job_id: {"status": "pending"|"done"|"error", "result": html}}
jobs = {}
jobs_lock = threading.Lock()

# ── Input form ──────────────────────────────────────────────────────────────

FORM_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>✈️ Travel Brief Generator</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{min-height:100%;font-family:'Inter',system-ui,sans-serif;color:#fff}
body{
  background:linear-gradient(135deg,#1a1a2e 0%,#16213e 40%,#0f3460 100%);
  background-attachment:fixed;min-height:100vh;
  display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;
}

.logo{font-size:48px;margin-bottom:8px;text-align:center}
h1{font-size:28px;font-weight:900;text-align:center;letter-spacing:-0.5px;margin-bottom:4px}
.subtitle{font-size:14px;color:rgba(255,255,255,0.45);text-align:center;margin-bottom:32px;font-weight:500}

.card{
  width:100%;max-width:520px;
  background:rgba(255,255,255,0.07);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border:1px solid rgba(255,255,255,0.12);border-radius:20px;padding:28px;
}

.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
.field:last-child{margin-bottom:0}
label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:rgba(255,255,255,0.4)}
input{
  background:rgba(255,255,255,0.08);border:1.5px solid rgba(255,255,255,0.15);
  border-radius:10px;padding:11px 13px;font-size:15px;font-family:'Inter',sans-serif;
  color:#fff;outline:none;width:100%;-webkit-appearance:none;
}
input::placeholder{color:rgba(255,255,255,0.25)}
input:focus{border-color:rgba(168,85,247,0.7);background:rgba(255,255,255,0.11)}
input[type=date]::-webkit-calendar-picker-indicator{filter:invert(1);opacity:.5;cursor:pointer}

.divider{height:1px;background:rgba(255,255,255,0.08);margin:18px 0}

.btn{
  width:100%;margin-top:18px;
  background:linear-gradient(135deg,#a855f7,#3b82f6);
  color:#fff;border:none;border-radius:12px;padding:15px;
  font-size:16px;font-weight:800;cursor:pointer;font-family:'Inter',sans-serif;
  transition:.2s;letter-spacing:.2px;
}
.btn:hover{opacity:.9;transform:translateY(-1px);box-shadow:0 8px 24px rgba(168,85,247,0.35)}
.btn:active{transform:none}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}

/* Loading overlay */
.overlay{
  display:none;position:fixed;inset:0;z-index:999;
  background:linear-gradient(135deg,#1a1a2e 0%,#16213e 40%,#0f3460 100%);
  flex-direction:column;align-items:center;justify-content:center;gap:20px;
}
.overlay.show{display:flex}
.spinner{
  width:56px;height:56px;border-radius:50%;
  border:4px solid rgba(255,255,255,0.1);
  border-top-color:#a855f7;
  animation:spin 0.8s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-title{font-size:22px;font-weight:800;color:#fff}
.loading-msg{font-size:14px;color:rgba(255,255,255,0.5);font-weight:500;min-height:20px;transition:.3s}
.loading-steps{display:flex;gap:8px;margin-top:8px}
.step{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,0.15)}
.step.done{background:#a855f7}
.step.active{background:#fff}

@media(max-width:480px){.row{grid-template-columns:1fr}}
</style>
</head><body>

<div class="logo">✈️</div>
<h1>Travel Brief</h1>
<p class="subtitle">Instant trip intel for insurance sales professionals</p>

<div class="card">
  <form id="form" onsubmit="submitForm(event)">

    <div class="row">
      <div class="field">
        <label>From</label>
        <input type="text" name="origin" id="origin" placeholder="Tel Aviv" required>
      </div>
      <div class="field">
        <label>To (City)</label>
        <input type="text" name="destination_city" id="destination_city" placeholder="London" required>
      </div>
    </div>

    <div class="field">
      <label>Country</label>
      <input type="text" name="destination_country" id="destination_country" placeholder="United Kingdom" required>
    </div>

    <div class="row">
      <div class="field">
        <label>Departure</label>
        <input type="date" name="start_date" id="start_date" required>
      </div>
      <div class="field">
        <label>Return</label>
        <input type="date" name="end_date" id="end_date" required>
      </div>
    </div>

    <div class="divider"></div>

    <div class="field">
      <label>Company visiting (optional)</label>
      <input type="text" name="company_name" id="company_name" placeholder="e.g. Lloyd's of London">
    </div>

    <button type="submit" class="btn" id="btn">Generate Brief ✈️</button>
  </form>
</div>

<!-- Loading overlay -->
<div class="overlay" id="overlay">
  <div class="spinner"></div>
  <div class="loading-title">Building your brief…</div>
  <div class="loading-msg" id="msg">Checking weather forecasts</div>
  <div class="loading-steps">
    <div class="step" id="s0"></div>
    <div class="step" id="s1"></div>
    <div class="step" id="s2"></div>
    <div class="step" id="s3"></div>
    <div class="step" id="s4"></div>
  </div>
</div>

<script>
const FIELDS = ['origin','destination_city','destination_country','start_date','end_date','company_name'];
const msgs = [
  "Checking weather forecasts",
  "Finding time zones & currency",
  "Researching restaurants & attractions",
  "Looking up transport & etiquette",
  "Compiling your dashboard",
];

// ── Restore saved form values ──────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  FIELDS.forEach(id => {
    const el = document.getElementById(id);
    const saved = localStorage.getItem('tb_' + id);
    if (el && saved) el.value = saved;
  });
});

// Save on change
FIELDS.forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('change', () => localStorage.setItem('tb_' + id, el.value));
});

// ── Loading animation ──────────────────────────────────────────────────────
let step = 0, msgTimer;
function startLoading(){
  step = 0;
  document.getElementById('overlay').classList.add('show');
  document.getElementById('s0').className = 'step active';
  document.getElementById('msg').textContent = msgs[0];
  msgTimer = setInterval(() => {
    if (step < msgs.length - 1) {
      document.getElementById('s' + step).className = 'step done';
      step++;
      document.getElementById('msg').textContent = msgs[step];
      if (step < 5) document.getElementById('s' + step).className = 'step active';
    }
  }, 8000);
}
function stopLoading(){
  clearInterval(msgTimer);
  document.getElementById('overlay').classList.remove('show');
}

// ── Submit with polling ────────────────────────────────────────────────────
function submitForm(e){
  e.preventDefault();
  const data = new URLSearchParams(new FormData(document.getElementById('form')));
  document.getElementById('btn').disabled = true;
  startLoading();

  // 1. Start the job
  fetch('/start', {method:'POST', body: data})
    .then(r => r.json())
    .then(({job_id}) => poll(job_id))
    .catch(() => { stopLoading(); document.getElementById('btn').disabled=false; alert('Could not start. Please try again.'); });
}

// 2. Poll until done
function poll(job_id){
  fetch('/status/' + job_id)
    .then(r => r.json())
    .then(data => {
      if (data.status === 'done') {
        clearInterval(msgTimer);
        document.open();
        document.write(data.result);
        document.close();
      } else if (data.status === 'error') {
        stopLoading();
        document.getElementById('btn').disabled = false;
        alert('Error: ' + data.result);
      } else {
        setTimeout(() => poll(job_id), 3000);
      }
    })
    .catch(() => setTimeout(() => poll(job_id), 3000));
}
</script>
</body></html>"""


# ── Background worker ────────────────────────────────────────────────────────

def run_job(job_id, origin, destination_city, destination_country, start_date, end_date, company_name):
    try:
        data = run_agent(
            origin=origin,
            destination_city=destination_city,
            destination_country=destination_country,
            start_date=start_date,
            end_date=end_date,
            company_name=company_name,
        )
        html = generate_html(data)
        with jobs_lock:
            jobs[job_id] = {"status": "done", "result": html}
    except Exception as e:
        with jobs_lock:
            jobs[job_id] = {"status": "error", "result": str(e)}


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return FORM_HTML


@app.route('/start', methods=['POST'])
def start():
    origin              = request.form.get('origin', '').strip()
    destination_city    = request.form.get('destination_city', '').strip()
    destination_country = request.form.get('destination_country', '').strip()
    start_date          = request.form.get('start_date', '').strip()
    end_date            = request.form.get('end_date', '').strip()
    company_name        = request.form.get('company_name', '').strip()

    if not all([origin, destination_city, destination_country, start_date, end_date]):
        return jsonify({"error": "Missing required fields"}), 400

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {"status": "pending", "result": None}

    t = threading.Thread(
        target=run_job,
        args=(job_id, origin, destination_city, destination_country, start_date, end_date, company_name),
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id})


@app.route('/status/<job_id>')
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "error", "result": "Job not found"}), 404
    return jsonify(job)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    print(f"\n✈️  Travel Brief running at http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)
