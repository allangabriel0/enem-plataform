/* =======================================================================
   ENEM Study Platform — app.js
   ======================================================================= */

/* -----------------------------------------------------------------------
   1. Sidebar mobile toggle
   ----------------------------------------------------------------------- */
(function () {
  const toggle  = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  if (!toggle || !sidebar) return;

  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });

  // Fecha ao clicar fora da sidebar em mobile
  document.addEventListener('click', (e) => {
    if (
      sidebar.classList.contains('open') &&
      !sidebar.contains(e.target) &&
      e.target !== toggle
    ) {
      sidebar.classList.remove('open');
    }
  });
})();

/* -----------------------------------------------------------------------
   2. Toast notifications (global)
   ----------------------------------------------------------------------- */
function showToast(message, type = 'success', duration = 3000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

/* -----------------------------------------------------------------------
   3. formatTime utility (global) — converte segundos → M:SS ou H:MM:SS
   ----------------------------------------------------------------------- */
function formatTime(seconds) {
  const s = Math.floor(seconds || 0);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  const pad = n => String(n).padStart(2, '0');
  if (h > 0) return `${h}:${pad(m % 60)}:${pad(s % 60)}`;
  return `${m}:${pad(s % 60)}`;
}

/* -----------------------------------------------------------------------
   4. Collapsible sections (dashboard)
   ----------------------------------------------------------------------- */
document.querySelectorAll('.section-block__header').forEach((header) => {
  const block = header.closest('.section-block');
  if (!block) return;
  const list = block.querySelector('.video-list');
  if (!list) return;

  header.addEventListener('click', () => {
    const collapsed = list.style.display === 'none';
    list.style.display = collapsed ? '' : 'none';
    header.setAttribute('aria-expanded', String(collapsed));
  });

  // Acessibilidade: Enter/Space também colapsa
  header.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      header.click();
    }
  });
});
