document.querySelectorAll('.alert').forEach(alert => {
  setTimeout(() => {
    alert.style.transition = 'opacity .5s';
    alert.style.opacity = '0';
    setTimeout(() => alert.remove(), 500);
  }, 4000);
});

document.querySelectorAll('.stat-card[href]').forEach(card => {
  card.addEventListener('click', e => {
    e.preventDefault();
    const targetId = card.getAttribute('href').slice(1);
    const target = document.getElementById(targetId);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    target.style.transition = 'box-shadow .5s, border-color .5s';
    target.style.boxShadow = '0 0 0 3px rgba(79,142,247,.15)';
    target.style.borderColor = 'var(--accent)';
    setTimeout(() => {
      target.style.boxShadow = '';
      target.style.borderColor = '';
    }, 2000);
  });
});