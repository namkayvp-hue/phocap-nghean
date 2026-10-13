(function () {
    'use strict';
    const field = id => document.getElementById(id);
    function show(box, visible) {
        if (!box) return;
        box.hidden = !visible;
        box.querySelectorAll('input,select,textarea').forEach(input => { input.disabled = !visible; });
    }
    function update() {
        const g3 = field('completed_grade_3')?.value;
        const g5 = field('completed_grade_5')?.value;
        const illiterate = field('is_literacy_target')?.value === 'CO' && g5 === 'KHONG' && ['CO', 'KHONG'].includes(g3);
        show(field('literacy_support_wrap'), illiterate);
        show(field('literacy_support_details'), illiterate && field('literacy_learning_support')?.value === 'CO');
    }
    document.addEventListener('change', () => setTimeout(update, 0));
    document.addEventListener('input', () => setTimeout(update, 0));
    field('year_record_form')?.addEventListener('submit', update, true);
    update();
    [150, 500, 800].forEach(delay => setTimeout(update, delay));
})();
