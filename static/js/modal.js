// static/modal.js
const Modal = (() => {
  let overlay = null;
  let confirmResolve = null;   // 存储 confirm 的 resolve 函数

  function ensureOverlay() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-box">
        <span class="modal-close-btn" id="modalCloseBtn">&times;</span>
        <div class="modal-body" id="modalBody"></div>
        <div class="modal-footer" id="modalFooter"></div>
      </div>
    `;
    document.body.appendChild(overlay);

    // 右上角 × 点击
    document.getElementById('modalCloseBtn').addEventListener('click', () => {
      if (confirmResolve) {
        confirmResolve(null);
        confirmResolve = null;
      }
      hide();
    });

    // 点击背景关闭
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        if (overlay.dataset.closable !== 'false' && !confirmResolve) {
          hide();
        } else if (confirmResolve) {
          confirmResolve(null);
          confirmResolve = null;
          hide();
        }
      }
    });
  }

  function show({ message, type = 'info', closable = true, duration = 0 }) {
    ensureOverlay();
    const body = document.getElementById('modalBody');
    const footer = document.getElementById('modalFooter');
    const closeBtn = document.getElementById('modalCloseBtn');

    closeBtn.style.display = closable ? 'block' : 'none';
    overlay.dataset.closable = closable;
    confirmResolve = null;   // 清除 confirm 回调

    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    else if (type === 'error') icon = '❌';
    else if (type === 'warning') icon = '⚠️';

    body.innerHTML = `<p style="white-space: pre-line;">${icon} ${message}</p>`;
    footer.innerHTML = '';

    overlay.style.display = 'flex';

    if (duration > 0) {
      setTimeout(hide, duration);
    }
  }

  function confirm({ message, confirmText = '确认', cancelText = '取消', type = 'warning' }) {
    ensureOverlay();
    const body = document.getElementById('modalBody');
    const footer = document.getElementById('modalFooter');
    const closeBtn = document.getElementById('modalCloseBtn');
    closeBtn.style.display = 'block';
    overlay.dataset.closable = true;
    
    let icon = '⚠️';
    if (type === 'danger') icon = '🔥';
    else if (type === 'info') icon = 'ℹ️';

    body.innerHTML = `<p style="white-space: pre-line;">${icon} ${message}</p>`;
    footer.innerHTML = `
      <button class="modal-btn modal-btn-cancel" id="modalCancelBtn">${cancelText}</button>
      <button class="modal-btn modal-btn-ok" id="modalOkBtn">${confirmText}</button>
    `;

    overlay.style.display = 'flex';

    return new Promise((resolve) => {
      confirmResolve = resolve;

      document.getElementById('modalOkBtn').addEventListener('click', () => {
        confirmResolve = null;
        hide();
        resolve(true);
      });
      document.getElementById('modalCancelBtn').addEventListener('click', () => {
        confirmResolve = null;
        hide();
        resolve(false);
      });
    });
  }

  function hide() {
    if (overlay) {
      overlay.style.display = 'none';
    }
  }

  return { show, confirm, hide };
})();