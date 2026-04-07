// ── Flash toast ────────────────────────────────────────────────────────────────
(function () {
  const params = new URLSearchParams(window.location.search);
  const msg = params.get('flash');
  if (!msg) return;
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
  const clean = new URL(window.location.href);
  clean.searchParams.delete('flash');
  history.replaceState(null, '', clean.toString());
})();

// ── Modal helpers ──────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.classList.remove('open');
  });
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
  }
});

// ── Edit card ──────────────────────────────────────────────────────────────────
function editCard(id, front, back, topicId) {
  const form = document.getElementById('edit-card-form');
  if (!form) return;
  form.action = `/learn/cards/${id}/edit`;
  document.getElementById('edit-card-front').value = front;
  document.getElementById('edit-card-back').value = back;
  openModal('modal-edit-card');
}

// ── Edit decision ──────────────────────────────────────────────────────────────
function editDecision(id, title, context, options, choice, reasoning) {
  document.getElementById('edit-dec-title').value = title;
  document.getElementById('edit-dec-context').value = context;
  document.getElementById('edit-dec-options').value = options;
  document.getElementById('edit-dec-choice').value = choice;
  document.getElementById('edit-dec-reasoning').value = reasoning;
  openModal('modal-edit-decision');
}

// ── Session timer ──────────────────────────────────────────────────────────────
let _timerInterval = null;
let _timerSeconds  = 0;

function timerStart() {
  if (_timerInterval) return;
  const startTime = Date.now() - _timerSeconds * 1000;
  _timerInterval = setInterval(() => {
    _timerSeconds = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(_timerSeconds / 60);
    const s = _timerSeconds % 60;
    const el = document.getElementById('timer-display');
    if (el) el.textContent = m + ':' + String(s).padStart(2, '0');
  }, 500);
  const startBtn = document.getElementById('timer-start-btn');
  const stopBtn  = document.getElementById('timer-stop-btn');
  if (startBtn) startBtn.style.display = 'none';
  if (stopBtn)  stopBtn.style.display  = 'inline-flex';
}

function timerStop() {
  clearInterval(_timerInterval);
  _timerInterval = null;
  const minutes = Math.max(1, Math.round(_timerSeconds / 60));
  const input = document.getElementById('duration-input');
  if (input) input.value = minutes;
  _timerSeconds = 0;
  const el = document.getElementById('timer-display');
  if (el) el.textContent = '0:00';
  const startBtn = document.getElementById('timer-start-btn');
  const stopBtn  = document.getElementById('timer-stop-btn');
  if (startBtn) startBtn.style.display = 'inline-flex';
  if (stopBtn)  stopBtn.style.display  = 'none';
}

// ── Quiz card flip ─────────────────────────────────────────────────────────────
const flashcard = document.getElementById('flashcard');
const flipBtn   = document.getElementById('flip-btn');
const ratingRow = document.getElementById('rating-row');

if (flashcard && flipBtn) {
  function flipCard() {
    flashcard.classList.add('flipped');
    flipBtn.style.display = 'none';
    ratingRow.classList.add('visible');
  }
  flipBtn.addEventListener('click', flipCard);
  flashcard.addEventListener('click', flipCard);

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === ' ' && !flashcard.classList.contains('flipped')) {
      e.preventDefault();
      flipCard();
    }
    if (['1','2','3','4','5'].includes(e.key) && flashcard.classList.contains('flipped')) {
      e.preventDefault();
      const btn = document.querySelector(`.rating-btn[data-r="${e.key}"]`);
      if (btn) btn.closest('form').submit();
    }
  });
}

// ── Inline tabs ────────────────────────────────────────────────────────────────
document.querySelectorAll('.tabs').forEach(tabGroup => {
  const buttons = tabGroup.querySelectorAll('.tab-btn');
  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      buttons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      tabGroup.parentElement.querySelectorAll('.tab-content').forEach(c => {
        c.classList.toggle('active', c.dataset.tab === target);
      });
    });
  });
});
