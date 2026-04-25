(function () {
    var form = document.getElementById("propose-form");
    var btn = document.getElementById("submit-btn");
    var nsCustom = document.getElementById("ns-custom");
    form.addEventListener("submit", function () {
        if (
            nsCustom &&
      !nsCustom.classList.contains("hidden") &&
      nsCustom.value.trim()
        ) {
            document.getElementById("namespace").value = nsCustom.value.trim();
        }
        btn.disabled = true;
        btn.textContent = "Submitting…";
    });

    var dd = document.getElementById("ns-dropdown");
    var toggle = document.getElementById("ns-toggle");
    var hidden = document.getElementById("namespace");

    function setOpen(open) {
        dd.classList.toggle("open", open);
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
    }

    toggle.addEventListener("click", function () {
        setOpen(!dd.classList.contains("open"));
    });
    toggle.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen(!dd.classList.contains("open"));
        } else if (e.key === "Escape") {
            setOpen(false);
        }
    });
    dd.addEventListener("click", function (e) {
        var item = e.target.closest(".dropdown-item");
        if (!item) return;
        dd.querySelectorAll(".dropdown-item").forEach(function (i) {
            i.classList.remove("active");
            i.setAttribute("aria-selected", "false");
        });
        item.classList.add("active");
        item.setAttribute("aria-selected", "true");
        if (item.dataset.value === "__new__") {
            nsCustom.classList.remove("hidden");
            nsCustom.focus();
            toggle.textContent = "New…";
        } else {
            nsCustom.classList.add("hidden");
            nsCustom.value = "";
            hidden.value = item.dataset.value;
            toggle.textContent = item.dataset.value;
        }
        setOpen(false);
    });
    document.addEventListener("click", function (e) {
        if (!dd.contains(e.target)) setOpen(false);
    });
})();
