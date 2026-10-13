(function () {
    'use strict';
    const field = id => document.getElementById(id);
    function grade() {
        const school = [field('school_name_reported')?.value,field('school_search')?.value].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
        if (/mam non|mau giao|nha tre|\bmn\b/.test(school)) return null;
        const selected = field('class_id');
        const choices = [selected && selected.value ? selected.options[selected.selectedIndex]?.textContent : '',
            field('class_name_reported')?.value, field('class_search')?.value, field('class_selected')?.textContent];
        for (const value of choices) {
            const text = (value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
            if (/tuoi|thang|mau giao|nha tre/.test(text)) continue;
            const match = text.match(/^(?:(?:lop|khoi)\s*)?(1[0-2]|[1-9])(?=\s|[a-z]|$)/);
            if (match) return Number(match[1]);
        }
        return null;
    }
    function show(box, visible) {
        if (!box) return;
        box.hidden = !visible;
        box.style.setProperty('display', visible ? 'block' : 'none', 'important');
        box.querySelectorAll('input,select').forEach(input => { input.disabled = !visible; });
    }
    function update() {
        const current = grade();
        const ageSection = field('age_completion_indicators');
        const referenceYear = ageSection?.dataset.schoolYear.match(/\d{4}/);
        const age = referenceYear && ageSection.dataset.birthYear ? Number(referenceYear[0]) - Number(ageSection.dataset.birthYear) : null;
        const ageGrade = age >= 11 && age <= 14 ? 5 : age >= 15 && age <= 18 ? 9 : null;
        if (ageSection) {
            ageSection.hidden = ageGrade === null;
            const target = field('age_completion_fields');
            document.querySelectorAll('[data-completion-grade],[data-completion-year]').forEach(box => {
                const expected = Number(box.dataset.completionGrade || (box.dataset.completionYear === 'completed_primary_program' ? 5 : 9));
                if (expected === ageGrade && target && box.parentNode !== target) target.appendChild(box);
            });
        }
        const school = [field('school_name_reported')?.value, field('school_search')?.value,
            field('school_selected')?.textContent].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        const upperSecondary = current !== null ? current >= 10 : /\bthpt\b|trung hoc pho thong/.test(school);
        show(field('post_lower_secondary_path_wrap'), !upperSecondary);
        document.querySelectorAll('[data-completion-grade]').forEach(box => show(box, current === Number(box.dataset.completionGrade) || ageGrade === Number(box.dataset.completionGrade)));
        document.querySelectorAll('[data-completion-year]').forEach(box => {
            const expected = box.dataset.completionYear === 'completed_primary_program' ? 5 : 9;
            const visible = (current === expected || ageGrade === expected) && field(box.dataset.completionYear)?.value === 'CO';
            show(box, visible);
            const input = box.querySelector('input');
            input.required = visible;
            input.max = new Date().getFullYear();
        });
        const location = field('study_location_scope')?.value;
        show(field('study_destination_wrap'), ['DI_HOC_NOI_KHAC','DI_HOC_TRONG_TINH','DI_HOC_NGOAI_TINH'].includes(location));
        show(field('study_origin_wrap'), location === 'NOI_KHAC_DEN');
    }
    document.addEventListener('change', () => setTimeout(update, 0));
    document.addEventListener('input', () => setTimeout(update, 0));
    field('year_record_form')?.addEventListener('submit', update, true);
    const selected = field('class_selected');
    if (selected) new MutationObserver(update).observe(selected, {childList:true,subtree:true,characterData:true});
    update();
    setTimeout(update, 500);
})();
