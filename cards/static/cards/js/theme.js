/*  MY-Card — Theme (dark/light) toggle
 *  Persists user preference in localStorage.
 *  Wire up any element with [data-mc-theme-toggle] to flip themes.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'mc-theme';
  var root = document.documentElement;

  function apply(theme) {
    root.setAttribute('data-theme', theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
    // Update toggle icons if present.
    document.querySelectorAll('[data-mc-theme-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
      var sun = btn.querySelector('[data-mc-theme-icon="sun"]');
      var moon = btn.querySelector('[data-mc-theme-icon="moon"]');
      if (sun && moon) {
        sun.style.display  = theme === 'light' ? 'inline' : 'none';
        moon.style.display = theme === 'light' ? 'none'  : 'inline';
      }
    });
  }

  function current() {
    return root.getAttribute('data-theme') || 'dark';
  }

  function toggle() {
    apply(current() === 'light' ? 'dark' : 'light');
  }

  function boot() {
    var saved = null;
    try { saved = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    if (saved === 'light' || saved === 'dark') {
      apply(saved);
    } else {
      // Default = whatever the server rendered (usually dark)
      apply(current());
    }
    document.querySelectorAll('[data-mc-theme-toggle]').forEach(function (btn) {
      btn.addEventListener('click', toggle);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.MCTheme = { apply: apply, toggle: toggle, current: current };
})();
