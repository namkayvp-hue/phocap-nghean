/* QUICK_SELECT_V1 */
(function () {
    "use strict";

    function norm(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/đ/g, "d")
            .replace(/Đ/g, "D")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, " ")
            .trim()
            .replace(/\s+/g, " ");
    }

    function addStyle() {
        if (document.getElementById("quick-select-v1-style")) {
            return;
        }

        var style = document.createElement("style");
        style.id = "quick-select-v1-style";
        style.textContent =
            ".quick-select-wrap{width:100%}" +
            ".quick-select-input{" +
            "width:100%;box-sizing:border-box;padding:10px;" +
            "border:1px solid #c8d6e3;border-radius:8px;" +
            "background:#fff;color:inherit;font:inherit}" +
            ".quick-select-input:focus{" +
            "outline:2px solid rgba(21,101,192,.18);" +
            "border-color:#1565c0}";
        document.head.appendChild(style);
    }

    function enhance(select, index) {
        if (!select || select.dataset.quickSearchReady === "1") {
            return;
        }

        select.dataset.quickSearchReady = "1";

        var options = Array.from(select.options).filter(function (o) {
            return String(o.value || "").trim() !== "";
        });

        if (!options.length) {
            return;
        }

        var wrapper = document.createElement("div");
        wrapper.className = "quick-select-wrap";

        var input = document.createElement("input");
        input.type = "text";
        input.className = "quick-select-input";
        input.autocomplete = "off";
        input.placeholder =
            select.dataset.quickSearchPlaceholder || "Gõ để tìm nhanh...";

        var listId =
            "quick-select-list-" +
            String(index) +
            "-" +
            Math.random().toString(36).slice(2, 8);

        input.setAttribute("list", listId);

        var datalist = document.createElement("datalist");
        datalist.id = listId;

        options.forEach(function (option) {
            var item = document.createElement("option");
            item.value = option.text.trim();
            datalist.appendChild(item);
        });

        var selected = select.options[select.selectedIndex];
        if (selected && String(selected.value || "").trim() !== "") {
            input.value = selected.text.trim();
        }

        var wasRequired = select.required;
        select.required = false;

        function clearValidity() {
            input.setCustomValidity("");
        }

        function matchValue(raw, allowUniquePrefix) {
            var key = norm(raw);

            if (!key) {
                select.value = "";
                clearValidity();
                return false;
            }

            var exact = options.filter(function (o) {
                return norm(o.text) === key;
            });

            if (exact.length === 1) {
                select.value = exact[0].value;
                input.value = exact[0].text.trim();
                clearValidity();
                return true;
            }

            if (allowUniquePrefix) {
                var prefix = options.filter(function (o) {
                    return norm(o.text).startsWith(key);
                });

                if (prefix.length === 1) {
                    select.value = prefix[0].value;
                    input.value = prefix[0].text.trim();
                    clearValidity();
                    return true;
                }
            }

            select.value = "";
            return false;
        }

        input.addEventListener("input", function () {
            clearValidity();
            matchValue(input.value, false);
        });

        input.addEventListener("change", function () {
            if (!matchValue(input.value, true)) {
                input.setCustomValidity(
                    "Hãy chọn đúng một mục trong danh sách gợi ý."
                );
            }
        });

        input.addEventListener("blur", function () {
            if (input.value.trim()) {
                matchValue(input.value, true);
            }
        });

        var form = select.closest("form");
        if (form) {
            form.addEventListener("submit", function (event) {
                if (select.disabled) {
                    return;
                }

                if (!matchValue(input.value, true) && wasRequired) {
                    input.setCustomValidity(
                        "Hãy gõ và chọn đúng một mục trong danh sách."
                    );
                    input.reportValidity();
                    event.preventDefault();
                    return;
                }

                clearValidity();
            });
        }

        if (select.disabled) {
            input.disabled = true;
        }

        select.style.display = "none";
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(input);
        wrapper.appendChild(datalist);
        wrapper.appendChild(select);
    }

    function init() {
        addStyle();

        document
            .querySelectorAll('select[data-quick-search="true"]')
            .forEach(function (select, index) {
                enhance(select, index);
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
