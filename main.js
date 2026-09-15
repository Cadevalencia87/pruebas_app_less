document.querySelectorAll('form[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); });
});
document.querySelector('[data-easter]')?.addEventListener('click', (event) => {
  event.currentTarget.textContent = 'ESTADO: sonrisa detectada ✓';
});
