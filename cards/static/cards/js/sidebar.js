/* Shared app-sidebar drawer toggle (mobile).
   Loaded from base.html; no-ops on pages that don't render `.dash-shell`. */
(function () {
    var shell    = document.querySelector('[data-dash-shell]');
    if (!shell) return;

    var openBtn  = document.querySelector('[data-dash-open]');
    var closeBtn = document.querySelector('[data-dash-close]');
    var scrim    = document.querySelector('[data-dash-scrim]');

    function open()  { shell.classList.add('is-menu-open'); }
    function close() { shell.classList.remove('is-menu-open'); }

    if (openBtn)  openBtn.addEventListener('click', open);
    if (closeBtn) closeBtn.addEventListener('click', close);
    if (scrim)    scrim.addEventListener('click', close);

    document.querySelectorAll('.dash-sidebar__link').forEach(function (a) {
        a.addEventListener('click', function () {
            if (window.matchMedia('(max-width: 960px)').matches) close();
        });
    });
})();
