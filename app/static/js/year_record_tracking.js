(function () {
    "use strict";

    const form = document.getElementById("year_record_form");
    const status = document.getElementById("learning_status");
    if (!form || !status) return;

    function updateVisibility() {
        // Chỉ đổi hiển thị, giữ dữ liệu khi lưu hoặc đổi lại trạng thái.
        form.classList.toggle(
            "not-tracking-learning",
            status.value === "KHONG_THUOC_DIEN"
        );
    }

    status.addEventListener("change", updateVisibility);
    status.addEventListener("input", updateVisibility);
    status.addEventListener("learning-tracking-updated", updateVisibility);
    window.addEventListener("pageshow", updateVisibility);
    document.addEventListener("DOMContentLoaded", updateVisibility);
    updateVisibility();
})();
