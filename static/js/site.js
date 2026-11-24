/* Progressive enhancement only: navigation, tabs and display filters. */
(() => {
  document.documentElement.classList.remove('no-js');
  const more = document.querySelector('#more-menu');
  const auction = document.querySelector('#auction-page');
  let dialogTrigger;
  const openDialog = (dialog, trigger) => {
    if (!dialog) return;
    document.querySelectorAll('dialog[open]').forEach(item => item.close());
    dialogTrigger = trigger || document.activeElement;
    dialog.showModal();
    document.body.classList.add('dialog-open');
  };
  document.querySelectorAll('[data-more-open]').forEach(button => button.addEventListener('click', () => openDialog(more, button)));
  document.querySelectorAll('dialog').forEach(dialog => {
    dialog.querySelectorAll('[data-dialog-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.addEventListener('close', () => {
      if (!document.querySelector('dialog[open]')) document.body.classList.remove('dialog-open');
      dialog.classList.remove('projector-mode');
      if (dialogTrigger instanceof HTMLElement && dialogTrigger.getClientRects().length) dialogTrigger.focus();
      else document.querySelector('.masthead .brand')?.focus();
    });
  });
  document.addEventListener('click', async event => {
    if (!event.target.closest('[data-projector]') || !auction) return;
    auction.classList.toggle('projector-mode');
    const enabled = auction.classList.contains('projector-mode');
    if (enabled && auction.requestFullscreen) await auction.requestFullscreen().catch(() => {});
    if (!enabled && document.fullscreenElement === auction) await document.exitFullscreen().catch(() => {});
  });
  document.addEventListener('fullscreenchange', () => {
    if (auction && !document.fullscreenElement) auction.classList.remove('projector-mode');
  });

  if (auction?.dataset.refreshActive === 'true') {
    const liveRegion = auction.querySelector('#auction-live-region');
    let refreshing = false;
    const refreshAuction = async () => {
      if (auction.dataset.refreshActive !== 'true') return;
      if (refreshing || document.visibilityState === 'hidden') return;
      refreshing = true;
      try {
        const response = await fetch(auction.dataset.refreshUrl, {
          headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'text/html' },
          cache: 'no-store',
          credentials: 'same-origin'
        });
        if (!response.ok) return;
        const html = await response.text();
        const fragmentDocument = new DOMParser().parseFromString(html, 'text/html');
        const fragment = fragmentDocument.querySelector('#auction-live-fragment');
        if (!fragment || !liveRegion) return;
        liveRegion.replaceChildren(...[...fragment.childNodes].map(node => document.importNode(node, true)));
        auction.dataset.refreshActive = ['ready', 'running', 'paused'].includes(fragment.dataset.auctionStatus) ? 'true' : 'false';
      } catch (_) {
        // Keep the last saved snapshot visible when a poll cannot reach the server.
      } finally {
        refreshing = false;
      }
    };
    window.setInterval(refreshAuction, 12000);
  }

  const activateTab = button => {
    const list = button.closest('[role="tablist"]');
    list.querySelectorAll('[role="tab"]').forEach(tab => {
      const active = tab === button;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
    });
  };
  document.querySelectorAll('[role="tablist"]').forEach(list => {
    const tabs = [...list.querySelectorAll('[role="tab"]')];
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activateTab(tab));
      tab.addEventListener('keydown', event => {
        let target;
        if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
        if (event.key === 'ArrowLeft') target = tabs[(index - 1 + tabs.length) % tabs.length];
        if (event.key === 'Home') target = tabs[0];
        if (event.key === 'End') target = tabs[tabs.length - 1];
        if (target) { event.preventDefault(); activateTab(target); target.focus(); }
      });
    });
  });
  document.querySelectorAll('.show-more').forEach(button => button.addEventListener('click', () => {
    const list = button.closest('.leaderboard-card')?.querySelector('.rank-list');
    if (!list) return;
    [...list.querySelectorAll('[hidden]')].slice(0, 10).forEach(row => row.hidden = false);
    if (!list.querySelector('[hidden]')) { button.textContent = 'All rankings shown'; button.disabled = true; }
  }));
  const handleImage = image => {
    if (!image.complete) return;
    image.classList.add(image.naturalWidth ? 'image-loaded' : 'image-failed');
  };
  document.querySelectorAll('img').forEach(image => {
    image.addEventListener('error', () => image.classList.add('image-failed'));
    image.addEventListener('load', () => image.classList.add('image-loaded'));
    handleImage(image);
  });
  document.querySelectorAll('.filter-panel').forEach(panel => {
    if (matchMedia('(min-width: 769px)').matches) panel.open = true;
  });

  document.querySelectorAll('[data-reveal-list]').forEach(list => {
    const limit = Number(list.dataset.limit || 12);
    const entries = [...list.children];
    const button = list.parentElement.querySelector('[data-reveal-button]');
    if (!button || entries.length <= limit) return;
    entries.slice(limit).forEach(entry => entry.hidden = true);
    button.hidden = false;
    button.addEventListener('click', () => {
      entries.filter(entry => entry.hidden).slice(0, limit).forEach(entry => entry.hidden = false);
      if (!entries.some(entry => entry.hidden)) button.hidden = true;
    });
  });

  const season = document.querySelector('#profile-season');
  if (season) {
    season.addEventListener('change', () => {
      const selected = season.value;
      const rows = [...document.querySelectorAll('[data-performance-row]')];
      rows.forEach(row => row.hidden = Boolean(selected && row.dataset.season !== selected));
      const visible = rows.filter(row => !row.hidden);
      // Display-only sums of the already supplied match records; no scoring writes.
      ['runs', 'wickets', 'dots'].forEach(field => {
        const target = document.querySelector(`[data-career="${field}"]`);
        if (target) target.textContent = visible.reduce((total, row) => total + Number(row.dataset[field] || 0), 0);
      });
      const matches = document.querySelector('[data-career="matches"]');
      if (matches) matches.textContent = visible.length;
      document.querySelectorAll('[data-season-filter]').forEach(element => { element.hidden = Boolean(selected && element.dataset.seasonFilter !== selected); });
      const status = document.querySelector('#profile-filter-status');
      if (status) status.textContent = selected ? `Showing Season ${selected}` : 'Showing all recorded seasons';
    });
  }
})();
