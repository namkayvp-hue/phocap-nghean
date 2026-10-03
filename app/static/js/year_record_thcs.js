(function () {
    "use strict";

    function text(selector) {
        const field = document.querySelector(selector);
        if (!field) return "";
        if (field.tagName === "SELECT") {
            const option = field.options[field.selectedIndex];
            return option ? option.textContent : "";
        }
        return field.value || field.textContent || "";
    }

    function normalize(value) {
        return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
            .toLowerCase().trim();
    }

    // All existing visibility handlers use this same rule for the THCS card.
    // THPT students still need completion and post-THCS pathway information.
    window.showSurveyThcsIndicators = function (fallback) {
        for (const selector of ["#class_search", "#class_selected", '[name="class_name_reported"]']) {
            const value = normalize(text(selector));
            const match = value.match(/(?:^|\blop\s*|\bkhoi\s*)(1[0-2]|[1-9])(?=\s|[a-z]|$)/);
            if (match) return Number(match[1]) >= 6;
        }
        const school = normalize([
            text("#school_search"), text("#school_selected"),
            text('[name="school_name_reported"]')
        ].join(" "));
        if (/\b(thpt|thcs)\b|trung hoc (pho thong|co so)/.test(school)) return true;
        return fallback;
    };
})();
