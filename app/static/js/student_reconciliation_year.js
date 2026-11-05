(function () {
    'use strict';
    const year = document.getElementById('reconciliation_target_year');
    if (!year || !year.form) return;
    // Reload the existing GET filter so the source year, source state and
    // upload form all refer to the same selected comparison year.
    year.addEventListener('change', function () {
        year.form.requestSubmit();
    });
})();
