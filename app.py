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
<title>✈️ TripBrief</title>
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
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:14px;position:relative}
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
input[readonly]{opacity:.7;cursor:default}

/* Autocomplete dropdown */
.ac-drop{
  position:absolute;top:100%;left:0;right:0;z-index:200;margin-top:4px;
  background:#1e1e3a;border:1px solid rgba(168,85,247,0.4);border-radius:10px;
  overflow:hidden;display:none;box-shadow:0 8px 32px rgba(0,0,0,0.4);
}
.ac-drop.open{display:block}
.ac-item{
  padding:10px 14px;cursor:pointer;font-size:14px;font-weight:500;
  border-bottom:1px solid rgba(255,255,255,0.06);
}
.ac-item:last-child{border-bottom:none}
.ac-item:hover,.ac-item.active{background:rgba(168,85,247,0.2)}
.ac-city{color:#fff;font-weight:600}
.ac-country{color:rgba(255,255,255,0.45);font-size:12px;margin-left:6px}
.ac-auto{font-size:10px;color:#a855f7;margin-left:6px;font-weight:700;text-transform:uppercase}

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
.spinner{width:56px;height:56px;border-radius:50%;border:4px solid rgba(255,255,255,0.1);border-top-color:#a855f7;animation:spin 0.8s linear infinite}
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
<h1>TripBrief</h1>
<p class="subtitle">Instant trip intel for insurance sales professionals</p>

<div class="card">
  <form id="form" onsubmit="submitForm(event)">

    <div class="field">
      <label>From (City)</label>
      <input type="text" name="origin" id="origin" placeholder="Tel Aviv" autocomplete="off" required>
      <div class="ac-drop" id="ac-origin"></div>
    </div>

    <div class="field">
      <label>To (City)</label>
      <input type="text" name="destination_city" id="destination_city" placeholder="Stockholm" autocomplete="off" required>
      <div class="ac-drop" id="ac-dest"></div>
    </div>

    <div class="field">
      <label>Country <span style="color:rgba(168,85,247,0.8);font-size:10px">(auto-filled)</span></label>
      <input type="text" name="destination_country" id="destination_country" placeholder="Auto-filled from city" required>
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
const FIELDS = ['origin','destination_city','destination_country','start_date','end_date'];
const msgs = [
  "Checking weather forecasts",
  "Finding time zones & currency",
  "Researching restaurants & attractions",
  "Looking up transport & etiquette",
  "Compiling your dashboard",
];

// ── Restore saved form values + auto-detect origin ────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  FIELDS.forEach(id => {
    const el = document.getElementById(id);
    const saved = localStorage.getItem('tb_' + id);
    if (el && saved) el.value = saved;
  });

  // Auto-detect origin city if not already saved
  const originEl = document.getElementById('origin');
  if (originEl && !originEl.value && navigator.geolocation) {
    originEl.placeholder = '📍 Detecting location…';
    navigator.geolocation.getCurrentPosition(pos => {
      const {latitude: lat, longitude: lon} = pos.coords;
      fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`, {
        headers: {'Accept-Language': 'en', 'User-Agent': 'TripBrief/1.0'}
      })
      .then(r => r.json())
      .then(d => {
        const city = d.address?.city || d.address?.town || d.address?.village || d.address?.county || '';
        if (city) {
          originEl.value = city;
          localStorage.setItem('tb_origin', city);
        }
        originEl.placeholder = 'Tel Aviv';
      })
      .catch(() => { originEl.placeholder = 'Tel Aviv'; });
    }, () => { originEl.placeholder = 'Tel Aviv'; }, {timeout: 5000});
  }
});
FIELDS.forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('change', () => localStorage.setItem('tb_' + id, el.value));
});

// ── City autocomplete ──────────────────────────────────────────────────────
let acTimers = {};

function setupCityAC(inputId, dropId, onSelect) {
  const inp = document.getElementById(inputId);
  const drop = document.getElementById(dropId);
  let results = [], activeIdx = -1;

  function showDrop(items) {
    results = items;
    activeIdx = -1;
    if (!items.length) { drop.classList.remove('open'); return; }
    drop.innerHTML = items.map((r, i) =>
      `<div class="ac-item" data-i="${i}">
        <span class="ac-city">${r.name}</span>
        <span class="ac-country">${r.country}</span>
        ${r.auto ? '<span class="ac-auto">✓ auto</span>' : ''}
      </div>`
    ).join('');
    drop.classList.add('open');
    drop.querySelectorAll('.ac-item').forEach(el => {
      el.addEventListener('mousedown', e => { e.preventDefault(); selectItem(parseInt(el.dataset.i)); });
    });
  }

  function selectItem(i) {
    const r = results[i];
    inp.value = r.name;
    localStorage.setItem('tb_' + inputId, r.name);
    drop.classList.remove('open');
    if (onSelect) onSelect(r);
  }

  inp.addEventListener('input', () => {
    const v = inp.value.trim();
    if (!v) { drop.classList.remove('open'); return; }
    clearTimeout(acTimers[inputId]);
    acTimers[inputId] = setTimeout(() => {
      fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(v)}&count=6&language=en`)
        .then(r => r.json())
        .then(d => {
          const items = (d.results || []).map(r => ({
            name: r.name, country: r.country,
            admin1: r.admin1 || '', auto: false
          }));
          showDrop(items);
        }).catch(() => {});
    }, 300);
  });

  inp.addEventListener('keydown', e => {
    if (!drop.classList.contains('open')) return;
    const items = drop.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') { e.preventDefault(); activeIdx = Math.min(activeIdx+1, items.length-1); items.forEach((el,i) => el.classList.toggle('active', i===activeIdx)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); activeIdx = Math.max(activeIdx-1, 0); items.forEach((el,i) => el.classList.toggle('active', i===activeIdx)); }
    else if (e.key === 'Enter' && activeIdx >= 0) { e.preventDefault(); selectItem(activeIdx); }
    else if (e.key === 'Escape') { drop.classList.remove('open'); }
  });

  inp.addEventListener('blur', () => setTimeout(() => drop.classList.remove('open'), 150));
}

// Origin city AC (no auto-fill of country)
setupCityAC('origin', 'ac-origin', null);

// Destination city AC — auto-fills country
setupCityAC('destination_city', 'ac-dest', r => {
  const countryEl = document.getElementById('destination_country');
  countryEl.value = r.country;
  localStorage.setItem('tb_destination_country', r.country);
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
let pollStart = Date.now();
function poll(job_id){
  const elapsed = Math.round((Date.now() - pollStart) / 1000);
  if (elapsed > 30) {
    document.getElementById('msg').textContent = `Still working… (${elapsed}s) — rate limits may cause delays`;
  }
  fetch('/status/' + job_id)
    .then(r => r.json())
    .then(data => {
      if (data.status === 'done') {
        clearInterval(msgTimer);
        window.location.href = '/result/' + job_id;
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
    import concurrent.futures
    TIMEOUT = 240  # 4 minutes max

    def _work():
        data = run_agent(
            origin=origin,
            destination_city=destination_city,
            destination_country=destination_country,
            start_date=start_date,
            end_date=end_date,
            company_name=company_name,
        )
        return generate_html(data)

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = ex.submit(_work)
    ex.shutdown(wait=False)  # don't block — let the thread run independently
    try:
        html = future.result(timeout=TIMEOUT)
        with jobs_lock:
            jobs[job_id] = {"status": "done", "result": html}
    except concurrent.futures.TimeoutError:
        with jobs_lock:
            jobs[job_id] = {"status": "error", "result": "Timed out after 4 minutes — Gemini API is too slow right now. Please try again in a moment."}
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


@app.route('/models')
def list_models():
    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    names = [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
    return "<br>".join(names)


@app.route('/status/<job_id>')
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "error", "result": "Job not found"}), 404
    # Don't include full HTML in the status response — just signal done
    if job["status"] == "done":
        return jsonify({"status": "done"})
    return jsonify(job)


@app.route('/result/<job_id>')
def result(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return "Result not found or not ready.", 404
    return Response(job["result"], content_type="text/html")


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    print(f"\n✈️  Travel Brief running at http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)
