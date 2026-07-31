/* ------------------------------------------------------------------
   CISA study system — front end

   Vanilla JS on purpose: the project rule is stdlib only, offline, no build
   step. That constraint applies to the browser side too, so there is no
   framework, no bundler and nothing to install.
   ------------------------------------------------------------------ */

const S = {
  boot: null,
  profile: localStorage.getItem('profile') || '',
  view: null,
  run: null,      // active drill/game runner
  exam: null,     // active exam runner
  keys: null,     // active keyboard handler
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const main = () => $('#main');
const LETTERS = ['A', 'B', 'C', 'D'];

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const pct = (v, digits = 0) => v == null ? '—' : (v * 100).toFixed(digits) + '%';
const num = (v) => v == null ? '—' : String(v);

function hms(sec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
               : `${m}:${String(s).padStart(2, '0')}`;
}

function band(v) { return v == null ? '' : v < 0.55 ? 'low' : v < 0.75 ? 'mid' : 'high'; }

// ---------------------------------------------------------------- transport

async function req(path, opts = {}) {
  const headers = Object.assign({ 'X-Profile': S.profile }, opts.headers || {});
  if (opts.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}
const get = (p) => req(p);
const post = (p, body) => req(p, { method: 'POST', body: JSON.stringify(body || {}) });

let toastTimer = null;
function toast(msg, bad = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast' + (bad ? ' bad' : '');
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}

// ---------------------------------------------------------------- widgets

function barRow(label, sub, value, low, high, right) {
  const w = value == null ? 0 : value * 100;
  const ci = (low != null && high != null && high > low)
    ? `<div class="ci" style="left:${(low * 100).toFixed(1)}%;width:${((high - low) * 100).toFixed(1)}%"></div>` : '';
  return `<div class="bar-row">
    <div class="bar-label">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ''}</div>
    <div class="track"><div class="fill ${band(value)}" style="width:${w.toFixed(1)}%"></div>${ci}</div>
    <div class="bar-num">${right != null ? right : pct(value)}</div>
  </div>`;
}

function stat(label, value, foot) {
  return `<div class="stat"><div class="label">${esc(label)}</div>
    <div class="value">${value}</div>
    ${foot ? `<div class="foot">${esc(foot)}</div>` : ''}</div>`;
}

// ---------------------------------------------------------------- shell

function setActiveNav(view) {
  $$('#nav a').forEach(a => a.classList.toggle('active', a.dataset.view === view));
}

function renderProfiles() {
  const sel = $('#profile-select');
  const names = (S.boot.profiles || []).slice();
  if (S.profile && !names.includes(S.profile)) names.push(S.profile);
  sel.innerHTML = `<option value="">Shared (default)</option>` +
    names.map(n => `<option value="${esc(n)}"${n === S.profile ? ' selected' : ''}>${esc(n)}</option>`).join('');
}

async function switchProfile(name) {
  S.profile = name || '';
  localStorage.setItem('profile', S.profile);
  S.boot = await get('/api/bootstrap');
  renderProfiles();
  toast(S.profile ? `Studying as ${S.profile}` : 'Using the shared profile');
  route();
}

// ---------------------------------------------------------------- router

const VIEWS = {
  dashboard: viewDashboard,
  drill: viewDrill,
  exam: viewExam,
  games: viewGames,
  rules: viewRules,
  bank: viewBank,
};

function teardown() {
  if (S.keys) { window.removeEventListener('keydown', S.keys); S.keys = null; }
  if (S.exam && S.exam.timer) { clearInterval(S.exam.timer); }
  S.run = null;
  S.exam = null;
}

async function route() {
  teardown();
  const hash = (location.hash || '#/').slice(2);
  const [name, ...rest] = hash.split('/');
  const view = VIEWS[name] ? name : 'dashboard';
  S.view = view;
  setActiveNav(view);
  main().scrollTop = 0;
  try {
    await VIEWS[view](rest);
  } catch (e) {
    main().innerHTML = `<div class="wrap"><div class="callout"><b>Something went wrong.</b><br>${esc(e.message)}</div></div>`;
  }
}

// ================================================================ dashboard

async function viewDashboard() {
  main().innerHTML = `<div class="wrap"><div class="loading"><span class="spinner"></span>Loading…</div></div>`;
  const o = await get('/api/overview');

  const started = o.attempts > 0;
  const weakRules = o.rules.filter(r => r.attempts >= 4).slice(0, 4);
  const weakTopics = o.topics.filter(t => t.attempts >= 3).slice(0, 6);

  main().innerHTML = `<div class="wrap">
    <div class="page-head">
      <h1>Dashboard</h1>
      <p>${started
        ? 'Where you stand, and what to work on next.'
        : 'Nothing logged yet. Run a drill and the diagnostics below start working.'}</p>
    </div>

    <div class="grid c4">
      ${stat('Questions answered', num(o.attempts), `${o.study_days} study day${o.study_days === 1 ? '' : 's'}`)}
      ${stat('Overall accuracy', o.accuracy == null ? '—' : pct(o.accuracy),
             o.last7_attempts ? `${pct(o.last7)} in the last 7 days` : 'no recent activity')}
      ${stat('Bank coverage', `${o.coverage_seen}<small>/${o.coverage_total}</small>`, 'questions seen at least once')}
      ${stat('Weighted accuracy', o.weighted_accuracy == null ? '—' : pct(o.weighted_accuracy),
             'by exam weight — not a predicted score')}
    </div>

    <h2 class="section">By domain</h2>
    <div class="card">
      <p class="sub">Bars show accuracy; the thin whisker is the 95% confidence interval. A wide whisker means you have not answered enough to claim anything yet.</p>
      ${o.domains.map(d => barRow(
        `D${d.id} ${d.name}`,
        `${d.weight}% of exam · ${d.attempts} answered`,
        d.accuracy, d.low, d.high,
        d.attempts ? pct(d.accuracy) : '—')).join('')}
    </div>

    <div class="grid c2" style="margin-top:14px">
      <div class="card">
        <h3>Weakest decision rules</h3>
        <p class="sub">Reasoning habits, not topics. These cost marks across every domain.</p>
        ${weakRules.length ? weakRules.map(r => barRow(r.name, `${r.attempts} answered`, r.accuracy, r.low, r.high)).join('')
          : `<div class="empty">Answer about 20 questions to populate this.</div>`}
        ${weakRules.length ? `<div class="btn-row" style="margin-top:14px">
          <a class="btn" href="#/rules">Full diagnostic</a>
          <button class="btn primary" data-act="costumes">Drill the weakest rule</button></div>` : ''}
      </div>

      <div class="card">
        <h3>Weakest topics</h3>
        <p class="sub">Ranked by the lower bound, so untested topics surface too.</p>
        ${weakTopics.length ? weakTopics.map(t => barRow(t.label, `${t.attempts}`, t.accuracy, t.low, t.high)).join('')
          : `<div class="empty">Not enough data yet.</div>`}
      </div>
    </div>

    <h2 class="section">Quick start</h2>
    <div class="btn-row">
      <button class="btn primary" data-act="drill20">Drill 20 questions</button>
      <button class="btn" data-act="due">What I'm about to forget</button>
      <button class="btn" data-act="principle">Target weak rules</button>
      <a class="btn" href="#/exam">Mock exam</a>
      <a class="btn" href="#/games">Short form</a>
    </div>

    ${o.exams.length ? `<h2 class="section">Recent exams</h2>
    <div class="card"><div class="list">${o.exams.map(e => `
      <div class="list-row">
        <div class="grow"><div class="t">${e.submitted ? 'Submitted' : 'In progress'} · <span class="mono">${esc(e.id)}</span></div>
        <div class="s">${esc((e.created || '').slice(0, 16).replace('T', ' '))} · ${e.answered}/${e.total} answered · ${hms(e.elapsed)} used</div></div>
        <a class="btn" href="#/exam/${e.submitted ? 'result' : 'run'}/${esc(e.id)}">${e.submitted ? 'Review' : 'Resume'}</a>
      </div>`).join('')}</div></div>` : ''}
  </div>`;

  main().addEventListener('click', async (ev) => {
    const act = ev.target.dataset && ev.target.dataset.act;
    if (!act) return;
    if (act === 'drill20') startDrill({ mode: 'smart', n: 20 });
    if (act === 'due') startDrill({ mode: 'due', n: 20 });
    if (act === 'principle') startDrill({ mode: 'principle', n: 15 });
    if (act === 'costumes') startDrill({ mode: 'costumes', n: 5 });
  }, { once: true });
}

// ==================================================================== drill

async function viewDrill() {
  const domains = S.boot.domains;
  main().innerHTML = `<div class="wrap narrow">
    <div class="page-head"><h1>Drill</h1>
      <p>Full scenario questions with the reasoning behind every option. This is the core of the system; everything else supports it.</p></div>

    <div class="card">
      <div class="field"><label>How questions are chosen</label>
        <div class="seg" id="mode-seg">
          <button data-v="smart" class="on">Smart</button>
          <button data-v="due">Due for review</button>
          <button data-v="weakest">Weakest first</button>
          <button data-v="principle">Weak decision rules</button>
          <button data-v="random">Random</button>
        </div>
      </div>

      <div class="grid c3">
        <div class="field"><label>Domain</label>
          <select id="f-domain"><option value="">All domains</option>
            ${domains.map(d => `<option value="${d.id}">D${d.id} — ${esc(d.name)} (${d.weight}%)</option>`).join('')}
          </select></div>
        <div class="field"><label>Topic contains</label>
          <input type="text" id="f-topic" placeholder="e.g. encryption"></div>
        <div class="field"><label>How many</label>
          <select id="f-n">${[5, 10, 15, 20, 30, 50].map(n => `<option${n === 20 ? ' selected' : ''}>${n}</option>`).join('')}</select></div>
      </div>

      <div class="btn-row"><button class="btn primary" id="go">Start drill</button>
        <span class="dim" style="font-size:12.5px">Answer with <kbd>A</kbd>–<kbd>D</kbd> or <kbd>1</kbd>–<kbd>4</kbd>, then <kbd>Enter</kbd></span></div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3>Same rule, five costumes</h3>
      <p class="sub">One decision rule shown across every domain it appears in. The surface changes completely; the reasoning does not.</p>
      <div class="field"><select id="f-rule"><option value="">Your weakest rule</option>
        ${S.boot.principles.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></div>
      <button class="btn" id="go-costumes">Run costumes</button>
    </div>
  </div>`;

  let mode = 'smart';
  $('#mode-seg').addEventListener('click', (ev) => {
    if (!ev.target.dataset.v) return;
    mode = ev.target.dataset.v;
    $$('#mode-seg button').forEach(b => b.classList.toggle('on', b.dataset.v === mode));
  });
  $('#go').onclick = () => startDrill({
    mode, n: +$('#f-n').value,
    domain: $('#f-domain').value, topic: $('#f-topic').value.trim(),
  });
  $('#go-costumes').onclick = () => startDrill({ mode: 'costumes', principle: $('#f-rule').value });
}

async function startDrill(params) {
  main().innerHTML = `<div class="wrap"><div class="loading"><span class="spinner"></span>Building your set…</div></div>`;
  let data;
  try { data = await post('/api/drill/start', params); }
  catch (e) { toast(e.message, true); location.hash = '#/drill'; return; }

  S.run = {
    kind: 'drill', mode: params.mode, session: data.session,
    questions: data.questions, header: data.header,
    i: 0, answered: 0, right: 0, revealed: null, started: Date.now(), qStart: Date.now(),
  };
  bindRunnerKeys();
  renderDrill();
}

function bindRunnerKeys() {
  if (S.keys) window.removeEventListener('keydown', S.keys);
  S.keys = (ev) => {
    const r = S.run;
    if (!r) return;
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

    const k = ev.key.toUpperCase();
    if (r.kind === 'drill') {
      if (!r.revealed) {
        const idx = LETTERS.indexOf(k) >= 0 ? LETTERS.indexOf(k) : '1234'.indexOf(ev.key);
        if (idx >= 0) { ev.preventDefault(); answerDrill(LETTERS[idx]); }
      } else if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); nextDrill(); }
    }
    if (ev.key === 'Escape') { ev.preventDefault(); location.hash = '#/'; }
  };
  window.addEventListener('keydown', S.keys);
}

function renderDrill() {
  const r = S.run, q = r.questions[r.i];
  r.qStart = Date.now();
  main().innerHTML = `
    <div class="runner-top">
      <div class="progress"><span style="width:${(r.i / r.questions.length * 100).toFixed(1)}%"></span></div>
      <div class="meta">${r.i + 1} of ${r.questions.length}</div>
      <div class="meta">${r.answered ? `${r.right}/${r.answered} correct` : ''}</div>
      <div class="grow"></div>
      <button class="btn ghost" id="quit">End session</button>
    </div>
    <div class="wrap">
      ${r.header ? `<div class="callout info" style="margin-bottom:18px"><b>${esc(r.header)}</b></div>` : ''}
      <div class="qcard">
        <div class="qmeta">
          <span class="chip mono">${esc(q.tag)}</span>
          <span class="chip">${esc(q.topic)}</span>
          <span class="chip">${esc(q.difficulty)}</span>
        </div>
        <p class="stem">${esc(q.stem)}</p>
        <div class="options" id="opts">
          ${LETTERS.map(L => `<button class="opt" data-k="${L}">
            <span class="key">${L}</span><span class="body">${esc(q.options[L])}</span></button>`).join('')}
        </div>
        <div id="after"></div>
      </div>
    </div>`;

  $('#quit').onclick = endDrill;
  $('#opts').addEventListener('click', (ev) => {
    const btn = ev.target.closest('.opt');
    if (btn && !S.run.revealed) answerDrill(btn.dataset.k);
  });
}

async function answerDrill(letter) {
  const r = S.run, q = r.questions[r.i];
  if (r.revealed) return;
  r.revealed = 'pending';
  $$('#opts .opt').forEach(b => { b.disabled = true; if (b.dataset.k === letter) b.classList.add('selected'); });

  let res;
  try {
    res = await post('/api/drill/answer', {
      question_id: q.id, chosen: letter, session: r.session, mode: r.mode,
      seconds: (Date.now() - r.qStart) / 1000,
    });
  } catch (e) { toast(e.message, true); r.revealed = null; return; }

  r.revealed = res;
  r.answered++;
  if (res.correct) r.right++;

  $$('#opts .opt').forEach(b => {
    const L = b.dataset.k;
    b.classList.remove('selected');
    if (L === res.answer) b.classList.add('correct');
    else if (L === letter) b.classList.add('chosen-wrong');
    else b.classList.add('dimmed');

    const text = L === res.answer ? res.why_correct : res.why_wrong[L];
    if (text) {
      const div = document.createElement('div');
      div.className = 'why ' + (L === res.answer ? 'good' : 'bad');
      div.innerHTML = `<b>${L === res.answer ? 'Why this is right' : 'Why this is wrong'}</b> — ${esc(text)}`;
      b.appendChild(div);
    }
  });

  const p = res.principle;
  $('#after').innerHTML = `
    ${p ? `<div class="rule-note">
      <div class="kicker">The rule that decides this</div>
      <h4>${esc(p.name)}</h4>
      <p>${esc(p.statement)}</p>
      <div class="trap"><b>Trap</b> — ${esc(p.misapplication)}</div>
    </div>` : ''}
    <div class="runner-foot">
      <button class="btn primary" id="next">${r.i + 1 >= r.questions.length ? 'Finish' : 'Next question'}</button>
      <span class="kbd-hint">press <kbd>Enter</kbd></span>
    </div>`;
  $('#next').onclick = nextDrill;
  $('#next').focus();
}

function nextDrill() {
  const r = S.run;
  r.revealed = null;
  r.i++;
  if (r.i >= r.questions.length) return endDrill();
  renderDrill();
}

function endDrill() {
  const r = S.run;
  if (!r || !r.answered) { location.hash = '#/'; return; }
  const mins = (Date.now() - r.started) / 60000;
  const acc = r.right / r.answered;
  teardown();
  main().innerHTML = `<div class="wrap narrow">
    <div class="page-head"><h1>Session complete</h1></div>
    <div class="card">
      <div class="score-hero">
        <div class="big ${acc >= 0.7 ? 'good' : acc < 0.5 ? 'bad' : ''}">${r.right}/${r.answered}</div>
        <div><div style="font-size:19px">${pct(acc)}</div>
        <div class="dim" style="font-size:13px">${mins.toFixed(1)} min · ${(mins * 60 / r.answered).toFixed(0)}s per question</div></div>
      </div>
    </div>
    <div class="btn-row" style="margin-top:16px">
      <a class="btn primary" href="#/drill">Another drill</a>
      <a class="btn" href="#/">Dashboard</a>
      <a class="btn" href="#/rules">See what the misses have in common</a>
    </div>
  </div>`;
}

// ===================================================================== exam

async function viewExam(rest) {
  const [sub, id] = rest;
  if (sub === 'run' && id) return runExam(id);
  if (sub === 'result' && id) return showExamResult(id);

  const list = await get('/api/exams');
  const fmt = S.boot.exam || {};
  main().innerHTML = `<div class="wrap narrow">
    <div class="page-head"><h1>Mock exam</h1>
      <p>Blueprint-weighted, timed, no feedback until you submit. The real thing is
      ${fmt.questions || 150} questions in ${fmt.minutes || 240} minutes.</p></div>

    <div class="card">
      <div class="grid c3">
        <div class="field"><label>Questions</label>
          <select id="e-n">${[150, 100, 75, 50, 25].map(n => `<option${n === 150 ? ' selected' : ''}>${n}</option>`).join('')}</select></div>
        <div class="field"><label>Minutes</label>
          <select id="e-min">${[240, 160, 120, 80, 40].map(n => `<option${n === 240 ? ' selected' : ''}>${n}</option>`).join('')}</select></div>
        <div class="field"><label>Scope</label>
          <select id="e-domain"><option value="">All domains (weighted)</option>
            ${S.boot.domains.map(d => `<option value="${d.id}">D${d.id} only</option>`).join('')}</select></div>
      </div>
      <button class="btn primary" id="e-new">Start exam</button>
    </div>

    ${list.exams.length ? `<h2 class="section">Saved exams</h2><div class="card"><div class="list">
      ${list.exams.map(e => `<div class="list-row">
        <div class="grow"><div class="t">${e.submitted ? 'Submitted' : 'In progress'} · <span class="mono">${esc(e.id)}</span></div>
          <div class="s">${esc((e.created || '').slice(0, 16).replace('T', ' '))} · ${e.answered}/${e.total} answered · ${hms(e.elapsed)} of ${hms(e.duration)}</div></div>
        <a class="btn ${e.submitted ? '' : 'primary'}" href="#/exam/${e.submitted ? 'result' : 'run'}/${esc(e.id)}">${e.submitted ? 'Review' : 'Resume'}</a>
      </div>`).join('')}</div></div>` : ''}
  </div>`;

  $('#e-new').onclick = async () => {
    $('#e-new').disabled = true;
    try {
      const data = await post('/api/exam/new', {
        n: +$('#e-n').value, minutes: +$('#e-min').value, domain: $('#e-domain').value,
      });
      location.hash = `#/exam/run/${data.id}`;
    } catch (e) { toast(e.message, true); $('#e-new').disabled = false; }
  };
}

async function runExam(id) {
  const data = await get(`/api/exam/${encodeURIComponent(id)}`);
  if (data.submitted) return showExamResult(id);

  S.exam = {
    id, questions: data.questions, answers: Object.assign({}, data.answers),
    flagged: new Set(data.flagged), i: data.position || 0,
    duration: data.duration, elapsed: data.elapsed,
    qStart: Date.now(), sittingStart: Date.now(), timer: null, shortfall: data.shortfall,
  };

  S.exam.timer = setInterval(examTick, 1000);
  bindExamKeys();
  renderExam();
  if (S.exam.shortfall && Object.keys(S.exam.shortfall).length) {
    toast('Bank could not fill the blueprint — some domains are short.');
  }
}

function examElapsed() {
  return S.exam.elapsed + (Date.now() - S.exam.sittingStart) / 1000;
}

async function examTick() {
  const x = S.exam;
  if (!x) return;
  const left = x.duration - examElapsed();
  const el = $('#exam-timer');
  if (el) {
    el.textContent = hms(left);
    el.className = 'timer' + (left < 300 ? ' crit' : left < 900 ? ' warn' : '');
  }
  if (left <= 0) { clearInterval(x.timer); toast('Time expired — submitting.'); return submitExam(true); }
  if (Math.round(examElapsed()) % 20 === 0) {
    try { await post('/api/exam/update', { id: x.id, action: 'tick', elapsed: examElapsed() }); } catch (e) { /* keep going */ }
  }
}

function bindExamKeys() {
  if (S.keys) window.removeEventListener('keydown', S.keys);
  S.keys = (ev) => {
    const x = S.exam;
    if (!x || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    const k = ev.key.toUpperCase();
    const idx = LETTERS.indexOf(k) >= 0 ? LETTERS.indexOf(k) : '1234'.indexOf(ev.key);
    if (idx >= 0) { ev.preventDefault(); return examAnswer(LETTERS[idx]); }
    if (ev.key === 'ArrowRight' || ev.key === 'Enter') { ev.preventDefault(); return examGo(x.i + 1); }
    if (ev.key === 'ArrowLeft') { ev.preventDefault(); return examGo(x.i - 1); }
    if (k === 'F') { ev.preventDefault(); return examFlag(); }
  };
  window.addEventListener('keydown', S.keys);
}

function renderExam() {
  const x = S.exam, q = x.questions[x.i];
  x.qStart = Date.now();
  const answeredCount = Object.keys(x.answers).length;

  main().innerHTML = `
    <div class="runner-top">
      <div class="timer" id="exam-timer">${hms(x.duration - examElapsed())}</div>
      <div class="meta">Q ${x.i + 1} / ${x.questions.length}</div>
      <div class="meta">${answeredCount} answered · ${x.flagged.size} flagged</div>
      <div class="grow"></div>
      <button class="btn ghost" id="ex-save">Save &amp; exit</button>
      <button class="btn primary" id="ex-submit">Submit</button>
    </div>
    <div class="wrap">
      <div class="qcard">
        <div class="qmeta">
          <span class="chip mono">${x.i + 1}</span>
          <button class="chip ${x.flagged.has(q.id) ? 'warn' : ''}" id="ex-flag">${x.flagged.has(q.id) ? '● Flagged' : '○ Flag for review'}</button>
        </div>
        <p class="stem">${esc(q.stem)}</p>
        <div class="options" id="opts">
          ${LETTERS.map(L => `<button class="opt ${x.answers[q.id] === L ? 'selected' : ''}" data-k="${L}">
            <span class="key">${L}</span><span class="body">${esc(q.options[L])}</span></button>`).join('')}
        </div>
        <div class="runner-foot">
          <button class="btn" id="ex-prev" ${x.i === 0 ? 'disabled' : ''}>← Previous</button>
          <button class="btn" id="ex-next" ${x.i >= x.questions.length - 1 ? 'disabled' : ''}>Next →</button>
          <button class="btn ghost" id="ex-clear">Clear answer</button>
          <span class="kbd-hint"><kbd>A</kbd>–<kbd>D</kbd> answer · <kbd>F</kbd> flag · <kbd>←</kbd><kbd>→</kbd> move</span>
        </div>
      </div>

      <h2 class="section">Question palette</h2>
      <div class="card"><div class="palette" id="pal">
        ${x.questions.map((qq, n) => `<button class="pal ${x.answers[qq.id] ? 'answered' : ''} ${x.flagged.has(qq.id) ? 'flagged' : ''} ${n === x.i ? 'current' : ''}" data-n="${n}">${n + 1}</button>`).join('')}
      </div></div>
    </div>`;

  $('#opts').addEventListener('click', (ev) => {
    const b = ev.target.closest('.opt');
    if (b) examAnswer(b.dataset.k);
  });
  $('#pal').addEventListener('click', (ev) => {
    const b = ev.target.closest('.pal');
    if (b) examGo(+b.dataset.n);
  });
  $('#ex-prev').onclick = () => examGo(x.i - 1);
  $('#ex-next').onclick = () => examGo(x.i + 1);
  $('#ex-flag').onclick = examFlag;
  $('#ex-clear').onclick = () => examAnswer('');
  $('#ex-submit').onclick = () => submitExam(false);
  $('#ex-save').onclick = async () => {
    await post('/api/exam/update', { id: x.id, action: 'tick', elapsed: examElapsed() });
    toast('Saved. The clock is stopped.');
    location.hash = '#/exam';
  };
}

async function examAnswer(letter) {
  const x = S.exam, q = x.questions[x.i];
  if (letter) x.answers[q.id] = letter; else delete x.answers[q.id];
  $$('#opts .opt').forEach(b => b.classList.toggle('selected', b.dataset.k === letter));
  const cell = $(`#pal .pal[data-n="${x.i}"]`);
  if (cell) cell.classList.toggle('answered', !!letter);
  try {
    await post('/api/exam/update', {
      id: x.id, action: 'answer', question_id: q.id, chosen: letter,
      seconds: (Date.now() - x.qStart) / 1000,
    });
  } catch (e) { toast(e.message, true); }
  x.qStart = Date.now();
  if (letter && x.i < x.questions.length - 1) setTimeout(() => examGo(x.i + 1), 130);
}

async function examFlag() {
  const x = S.exam, q = x.questions[x.i];
  if (x.flagged.has(q.id)) x.flagged.delete(q.id); else x.flagged.add(q.id);
  renderExam();
  try { await post('/api/exam/update', { id: x.id, action: 'flag', question_id: q.id }); }
  catch (e) { toast(e.message, true); }
}

function examGo(n) {
  const x = S.exam;
  if (n < 0 || n >= x.questions.length) return;
  x.i = n;
  renderExam();
  post('/api/exam/update', { id: x.id, action: 'position', position: n }).catch(() => {});
}

async function submitExam(auto) {
  const x = S.exam;
  const blank = x.questions.length - Object.keys(x.answers).length;
  if (!auto && blank > 0 &&
      !confirm(`${blank} question${blank === 1 ? '' : 's'} unanswered. They will score as incorrect. Submit anyway?`)) return;
  clearInterval(x.timer);
  try {
    await post('/api/exam/submit', { id: x.id, elapsed: examElapsed() });
    location.hash = `#/exam/result/${x.id}`;
  } catch (e) { toast(e.message, true); }
}

async function showExamResult(id) {
  const r = await get(`/api/exam/${encodeURIComponent(id)}/result`);
  const weak = r.by_domain.filter(d => d.asked >= 5 && d.accuracy < 0.65)
                          .sort((a, b) => b.cost - a.cost);

  main().innerHTML = `<div class="wrap">
    <div class="page-head"><h1>Exam result</h1><p class="mono">${esc(r.id)}</p></div>

    <div class="card">
      <div class="score-hero">
        <div class="big ${r.passed ? 'good' : 'bad'}">${r.scaled}</div>
        <div>
          <div style="font-size:17px">estimated scaled score</div>
          <div class="dim" style="font-size:13px">${r.correct}/${r.total} raw (${pct(r.raw, 1)}) · ${hms(r.elapsed)} of ${hms(r.duration)}${r.unanswered ? ` · ${r.unanswered} unanswered` : ''}</div>
        </div>
      </div>
      <div class="callout" style="margin-top:16px">
        <b>This is an approximation, not ISACA's number.</b> ISACA scales raw scores
        with an undisclosed psychometric process and the raw threshold moves between
        exam forms. The pass mark is ${r.pass_mark}; treat anything within about 50
        points of it as too close to call.
      </div>
    </div>

    <h2 class="section">By domain</h2>
    <div class="card">
      ${r.by_domain.map(d => barRow(`D${d.domain} ${d.name}`, `${d.weight}% of exam`, d.accuracy, null, null,
        `${d.correct}/${d.asked}`)).join('')}
    </div>

    ${weak.length ? `<h2 class="section">Where the lost marks actually are</h2>
    <div class="card"><p class="sub">Accuracy gap multiplied by exam weight. A 60% in a 26% domain costs more than a 50% in a 12% one.</p>
      ${weak.map(d => `<div class="list-row"><div class="grow"><div class="t">D${d.domain} ${esc(d.name)}</div>
        <div class="s">${pct(d.accuracy)} accuracy · ${d.weight}% of the exam</div></div>
        <div class="right"><div class="t" style="color:var(--bad)">−${d.cost.toFixed(1)}%</div>
        <div class="s">of the exam</div></div></div>`).join('')}</div>` : ''}

    ${r.guessed_right.length ? `<h2 class="section">Flagged but correct (${r.guessed_right.length})</h2>
      <div class="card"><p class="sub">You were unsure and got there anyway. Worth revisiting even though the score looks fine.</p>
      ${r.guessed_right.map(g => `<div class="list-row"><span class="mono">${esc(g.id)}</span><div class="grow"><div class="s">${esc(g.topic)}</div></div></div>`).join('')}</div>` : ''}

    <h2 class="section">Review the ${r.missed.length} you missed</h2>
    <div id="review"></div>
    <div class="btn-row" style="margin-top:20px"><a class="btn" href="#/exam">Back to exams</a></div>
  </div>`;

  $('#review').innerHTML = r.missed.map(q => `
    <div class="card" style="margin-bottom:12px">
      <div class="qmeta"><span class="chip mono">${esc(q.tag)}</span><span class="chip">${esc(q.topic)}</span>
        ${q.chosen ? `<span class="chip bad">you chose ${esc(q.chosen)}</span>` : `<span class="chip warn">left blank</span>`}
        <span class="chip good">answer ${esc(q.answer)}</span></div>
      <p class="stem" style="font-size:15.5px">${esc(q.stem)}</p>
      <div class="options">
        ${LETTERS.map(L => `<div class="opt ${L === q.answer ? 'correct' : (L === q.chosen ? 'chosen-wrong' : 'dimmed')}" style="cursor:default">
          <span class="key">${L}</span><span class="body">${esc(q.options[L])}
          <div class="why ${L === q.answer ? 'good' : 'bad'}"><b>${L === q.answer ? 'Why this is right' : 'Why this is wrong'}</b> — ${esc(L === q.answer ? q.why_correct : (q.why_wrong[L] || ''))}</div>
          </span></div>`).join('')}
      </div>
      ${q.principle ? `<div class="rule-note" style="margin-top:14px"><div class="kicker">Rule</div>
        <h4>${esc(q.principle.name)}</h4><p>${esc(q.principle.statement)}</p></div>` : ''}
    </div>`).join('') || `<div class="empty">Nothing missed.</div>`;
}

// ==================================================================== games

async function viewGames(rest) {
  if (rest && rest[0]) return startGame(rest[0]);
  const gs = await get('/api/games/stats');

  main().innerHTML = `<div class="wrap narrow">
    <div class="page-head"><h1>Short form</h1>
      <p>Two-minute drills that sharpen the substrate the judgment runs on. Results are kept
      out of your real accuracy on purpose — a five-second answer is not the same evidence as a worked scenario.</p></div>

    <div class="grid c2">
      <div class="card">
        <h3>Cold Read</h3>
        <p class="sub">Options hidden. Name what the question is <em>asking for</em>, predict the answer, then look.</p>
        <p style="font-size:13.5px;color:var(--text-dim)">Targets the most common way to lose marks on material you actually know: answering a question you misread.</p>
        <div class="btn-row" style="margin-top:14px"><button class="btn primary" data-game="coldread">Start · 10 items</button></div>
      </div>
      <div class="card">
        <h3>Autopsy</h3>
        <p class="sub">The answer is given. Match each wrong option to the explanation of why it fails.</p>
        <p style="font-size:13.5px;color:var(--text-dim)">Teaches how the traps are built, which is the part that transfers to questions you have never seen.</p>
        <div class="btn-row" style="margin-top:14px"><button class="btn primary" data-game="autopsy">Start · 8 items</button></div>
      </div>
    </div>

    ${gs.total ? `<h2 class="section">Results</h2>
    <div class="card">
      ${gs.by_game.map(g => barRow(g.game === 'coldread' ? 'Cold Read' : 'Autopsy',
        `${g.n} items · ${(g.secs / g.n).toFixed(0)}s each`, g.accuracy, null, null, pct(g.accuracy))).join('')}
      ${gs.misreads.length ? `<h2 class="section">Most common misreads</h2>
        <p class="sub" style="margin-top:-6px">What the question was asking, versus how you read it.</p>
        ${gs.misreads.map(m => `<div class="list-row"><div class="grow"><div class="t">
          <span style="color:var(--good)">${esc(m.expected)}</span>
          <span class="dim"> read as </span>
          <span style="color:var(--bad)">${esc(m.read)}</span></div></div>
          <span class="chip">${m.count}×</span></div>`).join('')}` : ''}
    </div>` : ''}
  </div>`;

  main().addEventListener('click', (ev) => {
    const g = ev.target.dataset && ev.target.dataset.game;
    if (g) location.hash = `#/games/${g}`;
  }, { once: true });
}

async function startGame(which) {
  main().innerHTML = `<div class="wrap"><div class="loading"><span class="spinner"></span>Preparing…</div></div>`;
  let data;
  try { data = await post('/api/game/start', { game: which, n: which === 'autopsy' ? 8 : 10 }); }
  catch (e) { toast(e.message, true); location.hash = '#/games'; return; }

  S.run = {
    kind: which, session: data.session, questions: data.questions,
    askTypes: data.ask_types || [], i: 0, answered: 0, right: 0,
    stage: 'ask', revealed: null, started: Date.now(), qStart: Date.now(), mapping: {},
  };
  if (which === 'coldread') renderColdRead(); else renderAutopsy();
}

function gameTop(r, label) {
  return `<div class="runner-top">
    <div class="progress"><span style="width:${(r.i / r.questions.length * 100).toFixed(1)}%"></span></div>
    <div class="meta">${label} · ${r.i + 1} of ${r.questions.length}</div>
    <div class="meta">${r.answered ? `${r.right}/${r.answered}` : ''}</div>
    <div class="grow"></div>
    <button class="btn ghost" onclick="location.hash='#/games'">End</button>
  </div>`;
}

function renderColdRead() {
  const r = S.run, q = r.questions[r.i];
  r.qStart = Date.now();
  main().innerHTML = gameTop(r, 'Cold Read') + `<div class="wrap narrow">
    <div class="qcard">
      <div class="qmeta"><span class="chip mono">${esc(q.tag)}</span><span class="chip">${esc(q.topic)}</span></div>
      <p class="stem">${esc(q.stem)}</p>
      <div class="callout info" style="margin-bottom:16px">The options are hidden. What is this question <b>asking for</b>?</div>
      <div class="options" id="asks">
        ${r.askTypes.map((a, n) => `<button class="opt" data-id="${esc(a.id)}">
          <span class="key">${n + 1}</span>
          <span class="body"><b>${esc(a.label)}</b><br><span class="dim" style="font-size:13px">${esc(a.gloss)}</span></span>
        </button>`).join('')}
      </div>
      <div id="after"></div>
    </div></div>`;
  $('#asks').addEventListener('click', (ev) => {
    const b = ev.target.closest('.opt');
    if (b) coldReadAnswer(b.dataset.id);
  });
}

async function coldReadAnswer(readId) {
  const r = S.run, q = r.questions[r.i];
  $$('#asks .opt').forEach(b => b.disabled = true);
  let res;
  try {
    res = await post('/api/game/answer', {
      game: 'coldread', question_id: q.id, session: r.session, read: readId,
      seconds: (Date.now() - r.qStart) / 1000,
    });
  } catch (e) { toast(e.message, true); return; }

  r.answered++;
  if (res.read_correct) r.right++;

  $$('#asks .opt').forEach(b => {
    if (b.dataset.id === res.expected) b.classList.add('correct');
    else if (b.dataset.id === readId) b.classList.add('chosen-wrong');
    else b.classList.add('dimmed');
  });

  $('#after').innerHTML = `
    <div class="callout ${res.read_correct ? 'info' : ''}" style="margin:18px 0">
      ${res.read_correct ? '<b>Right.</b> Now say your answer out loud before you look.'
                         : '<b>Misread.</b> Commit to an answer anyway, then look.'}
    </div>
    <button class="btn primary" id="show">Reveal the options</button>`;
  $('#show').onclick = () => coldReadReveal(res);
  $('#show').focus();
}

function coldReadReveal(res) {
  const r = S.run, q = r.questions[r.i];
  $('#after').innerHTML = `
    <div class="options" style="margin-top:18px">
      ${LETTERS.map(L => `<div class="opt ${L === res.answer ? 'correct' : 'dimmed'}" style="cursor:default">
        <span class="key">${L}</span><span class="body">${esc(res.options[L])}
        ${L === res.answer ? `<div class="why good"><b>Why this is right</b> — ${esc(res.why_correct)}</div>` : ''}</span></div>`).join('')}
    </div>
    <div class="card" style="margin-top:16px">
      <h3>Did your prediction match?</h3>
      <p class="sub">Self-reported and kept separate from the graded part.</p>
      <div class="btn-row">
        <button class="btn" data-sr="y">Matched</button>
        <button class="btn" data-sr="c">Close</button>
        <button class="btn" data-sr="n">Missed it</button>
      </div>
    </div>`;
  $('#after').addEventListener('click', async (ev) => {
    const sr = ev.target.dataset && ev.target.dataset.sr;
    if (!sr) return;
    try {
      await post('/api/game/answer', {
        game: 'coldread', question_id: q.id, session: r.session,
        read: res.read, self_report: sr, seconds: 0,
      });
    } catch (e) { /* the graded part already landed */ }
    r.i++;
    if (r.i >= r.questions.length) return gameDone('Cold Read');
    renderColdRead();
  });
}

function renderAutopsy() {
  const r = S.run, q = r.questions[r.i];
  r.qStart = Date.now();
  r.mapping = {};
  const labels = q.explanations.map(e => e.label);

  main().innerHTML = gameTop(r, 'Autopsy') + `<div class="wrap">
    <div class="qcard">
      <div class="qmeta"><span class="chip mono">${esc(q.tag)}</span><span class="chip">${esc(q.topic)}</span>
        <span class="chip good">answer ${esc(q.answer)}</span></div>
      <p class="stem">${esc(q.stem)}</p>
      <div class="options">
        ${LETTERS.map(L => `<div class="opt ${L === q.answer ? 'correct' : ''}" style="cursor:default">
          <span class="key">${L}</span><span class="body">${esc(q.options[L])}
          ${L !== q.answer && q.distractors.includes(L) ? `<div class="why" style="border-top-style:solid">
            <b>Which explanation fits ${L}?</b>
            <div class="seg" style="margin-top:7px" data-opt="${L}">
              ${labels.map(lab => `<button data-lab="${lab}">${lab}</button>`).join('')}
            </div></div>` : ''}</span></div>`).join('')}
      </div>

      <h2 class="section">The three reasons, scrambled</h2>
      <div class="card">
        ${q.explanations.map(e => `<div class="list-row"><span class="key" style="width:26px;height:26px;border-radius:6px;background:var(--raised);border:1px solid var(--line);display:grid;place-items:center;font-family:var(--mono);font-size:12.5px">${esc(e.label)}</span>
          <div class="grow" style="font-size:13.5px;color:var(--text-dim)">${esc(e.text)}</div></div>`).join('')}
      </div>

      <div class="runner-foot"><button class="btn primary" id="check" disabled>Check</button>
        <span class="kbd-hint">assign a letter to every wrong option</span></div>
      <div id="after"></div>
    </div></div>`;

  main().addEventListener('click', (ev) => {
    const b = ev.target.closest('.seg button');
    if (!b) return;
    const opt = b.parentElement.dataset.opt;
    S.run.mapping[opt] = b.dataset.lab;
    $$(`.seg[data-opt="${opt}"] button`).forEach(x => x.classList.toggle('on', x === b));
    $('#check').disabled = Object.keys(S.run.mapping).length < q.distractors.length;
  });
  $('#check').onclick = autopsyCheck;
}

async function autopsyCheck() {
  const r = S.run, q = r.questions[r.i];
  let res;
  try {
    res = await post('/api/game/answer', {
      game: 'autopsy', question_id: q.id, session: r.session,
      mapping: r.mapping, seconds: (Date.now() - r.qStart) / 1000,
    });
  } catch (e) { toast(e.message, true); return; }

  r.answered++;
  if (res.correct) r.right++;
  $$('.seg button').forEach(b => b.disabled = true);
  $('#check').disabled = true;

  $('#after').innerHTML = `<div class="card" style="margin-top:16px">
    <div class="score-hero"><div class="big ${res.correct ? 'good' : ''}">${res.matched}/${res.total}</div>
      <div class="dim">matched correctly</div></div>
    <div class="list" style="margin-top:12px">
      ${Object.entries(res.truth).map(([opt, lab]) => {
        const mine = r.mapping[opt];
        const ok = mine === lab;
        return `<div class="list-row"><span class="chip mono">${esc(opt)}</span>
          <div class="grow"><span class="${ok ? '' : 'dim'}">you said <b>${esc(mine)}</b></span>
          ${ok ? '<span class="chip good" style="margin-left:8px">correct</span>'
               : `<span class="chip bad" style="margin-left:8px">should be ${esc(lab)}</span>`}</div></div>`;
      }).join('')}
    </div>
    <div class="btn-row" style="margin-top:16px"><button class="btn primary" id="next">${r.i + 1 >= r.questions.length ? 'Finish' : 'Next'}</button></div>
  </div>`;
  $('#next').onclick = () => {
    r.i++;
    if (r.i >= r.questions.length) return gameDone('Autopsy');
    renderAutopsy();
  };
  $('#next').focus();
}

function gameDone(label) {
  const r = S.run;
  const acc = r.answered ? r.right / r.answered : 0;
  teardown();
  main().innerHTML = `<div class="wrap narrow">
    <div class="page-head"><h1>${esc(label)} complete</h1></div>
    <div class="card"><div class="score-hero">
      <div class="big ${acc >= 0.7 ? 'good' : ''}">${r.right}/${r.answered}</div>
      <div><div style="font-size:19px">${pct(acc)}</div>
      <div class="dim" style="font-size:13px">kept out of your drill and exam accuracy</div></div>
    </div></div>
    <div class="btn-row" style="margin-top:16px">
      <a class="btn primary" href="#/games">Back to short form</a>
      <a class="btn" href="#/">Dashboard</a></div>
  </div>`;
}

// ==================================================================== rules

async function viewRules(rest) {
  if (rest && rest[0] === 'card') return viewCard();
  const o = await get('/api/overview');
  const tested = o.rules.filter(r => r.attempts >= 4);
  const thin = o.rules.filter(r => r.attempts < 4);
  const actionable = tested.filter(r => r.accuracy < 0.8).slice(0, 3);

  main().innerHTML = `<div class="wrap">
    <div class="page-head"><h1>Decision rules</h1>
      <p>A different question from the dashboard. Not which topics you are weak on, but which
      reasoning habits are costing you marks across all of them — the only axis here that
      transfers to questions that do not exist yet.</p></div>

    <div class="btn-row" style="margin-bottom:20px">
      <a class="btn" href="#/rules/card">Study card</a>
      <button class="btn primary" id="drill-weak" ${tested.length ? '' : 'disabled'}>Drill the weakest rule</button>
    </div>

    ${tested.length ? `<h2 class="section">Ranked weakest first</h2>
    <div class="card">${tested.map(r => barRow(r.name, `${r.attempts} answered · ${r.seen}/${r.total} questions seen`,
      r.accuracy, r.low, r.high)).join('')}</div>` : ''}

    ${actionable.length ? `<h2 class="section">What to actually fix</h2>
    ${actionable.map(r => `<div class="card">
      <h3>${esc(r.name)} <span class="chip bad" style="margin-left:6px">${pct(r.accuracy)}</span></h3>
      <p class="sub">You are likely doing this instead</p>
      <p style="font-size:13.5px;color:var(--text-dim);margin:0 0 12px">${esc(r.misapplication)}</p>
      <p class="sub" style="margin:0">Watch the boundary</p>
      <p style="font-size:13.5px;color:var(--text-dim);margin:0 0 14px">${esc(r.scope)}</p>
      <button class="btn" data-rule="${esc(r.id)}">Drill this rule across every domain</button>
    </div>`).join('')}` : (tested.length ? `<div class="callout info">Nothing under 80% with enough evidence to act on. Keep drilling and check back.</div>` : '')}

    ${thin.length ? `<h2 class="section">Not yet tested</h2>
    <div class="card"><p class="sub">Fewer than 4 attempts — no claim either way.</p>
      ${thin.map(r => `<div class="list-row"><div class="grow"><div class="t">${esc(r.name)}</div>
        <div class="s">${r.seen} of ${r.total} questions seen</div></div>
        <button class="btn" data-rule="${esc(r.id)}">Test it</button></div>`).join('')}</div>` : ''}
  </div>`;

  main().addEventListener('click', (ev) => {
    const rule = ev.target.dataset && ev.target.dataset.rule;
    if (rule) return startDrill({ mode: 'costumes', principle: rule });
    if (ev.target.id === 'drill-weak') return startDrill({ mode: 'costumes' });
  });
}

async function viewCard() {
  const data = await get('/api/card');
  main().innerHTML = `<div class="wrap">
    <div class="page-head"><h1>Decision rules — study card</h1>
      <p>Generated from the taxonomy, so it cannot drift from the rules actually being tested.</p></div>
    <div class="btn-row" style="margin-bottom:14px">
      <a class="btn" href="#/rules">← Back</a>
      <button class="btn" id="copy">Copy to clipboard</button>
      <button class="btn" id="print">Print</button>
    </div>
    <pre class="card-text">${esc(data.text)}</pre>
  </div>`;
  $('#copy').onclick = async () => {
    try { await navigator.clipboard.writeText(data.text); toast('Copied.'); }
    catch (e) { toast('Could not copy — select and copy manually.', true); }
  };
  $('#print').onclick = () => window.print();
}

// ===================================================================== bank

async function viewBank() {
  const it = await get('/api/items');
  const pairs = S.boot.pairs;

  main().innerHTML = `<div class="wrap">
    <div class="page-head"><h1>Question bank</h1>
      <p>This page is about the <em>questions</em>, not about you. It surfaces items whose
      own statistics suggest they are badly written.</p></div>

    <div class="grid c4">
      ${stat('Questions', num(it.total), `${it.served} served, ${it.never_served} untouched`)}
      ${stat('With statistics', num(it.with_stats), 'enough attempts to judge')}
      ${stat('Mean difficulty', it.mean_p == null ? '—' : it.mean_p.toFixed(2), 'proportion correct')}
      ${stat('Mean discrimination', it.mean_discrimination == null ? '—' : (it.mean_discrimination >= 0 ? '+' : '') + it.mean_discrimination.toFixed(2), 'higher is better')}
    </div>

    ${it.with_stats ? `<h2 class="section">Difficulty spread</h2>
    <div class="card">${Object.entries(it.spread).map(([k, v]) =>
      barRow(k, null, it.with_stats ? v / it.with_stats : 0, null, null, String(v))).join('')}</div>` : ''}

    ${it.suspect.length ? `<h2 class="section">Questions worth rewriting</h2>
    <div class="card"><p class="sub">These flags describe the question, not you. Tell me the IDs and I will fix them.</p>
      ${it.suspect.map(s => `<div class="list-row">
        <span class="mono">${esc(s.id)}</span>
        <div class="grow"><div class="s">${esc(s.topic)}</div></div>
        <span class="chip mono">p=${s.p == null ? '—' : s.p.toFixed(2)}</span>
        ${s.flags.map(f => `<span class="chip warn">${esc(f)}</span>`).join('')}
      </div>`).join('')}</div>` : `<div class="callout info" style="margin-top:20px">Not enough attempts yet to flag any questions. This fills in as you drill.</div>`}

    <h2 class="section">Confusable pairs</h2>
    <div class="card"><p class="sub">${pairs.length} documented confusions. The discriminator is what separates them; the trap is how the exam exploits it.</p>
      ${pairs.map(p => `<details style="border-top:1px solid var(--line-soft);padding:10px 0">
        <summary style="cursor:pointer;font-size:14px">${esc(p.label)}
          <span class="chip" style="margin-left:8px">D${esc(p.domain)}</span>
          ${p.questions ? `<span class="chip">${p.questions} q</span>` : `<span class="chip warn">no coverage</span>`}</summary>
        <p style="font-size:13.5px;color:var(--text-dim);margin:9px 0 6px">${esc(p.discriminator)}</p>
        <p style="font-size:13px;color:var(--text-mute);margin:0"><b style="color:var(--warn)">Trap</b> — ${esc(p.trap)}</p>
      </details>`).join('')}</div>
  </div>`;
}

// ===================================================================== boot

(async function boot() {
  try {
    S.boot = await get('/api/bootstrap');
  } catch (e) {
    main().innerHTML = `<div class="wrap"><div class="callout"><b>Could not reach the server.</b><br>${esc(e.message)}</div></div>`;
    return;
  }
  $('#brand-cert').textContent = S.boot.cert;
  $('#brand-sub').textContent = `${S.boot.questions} questions`;
  renderProfiles();

  $('#profile-select').onchange = (ev) => switchProfile(ev.target.value);
  $('#profile-add').onclick = () => {
    const name = prompt('Name for the new study profile (e.g. a first name):');
    if (name && name.trim()) switchProfile(name.trim());
  };

  window.addEventListener('hashchange', route);
  route();
})();
