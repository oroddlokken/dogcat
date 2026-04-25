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
    toggle.addEventListener("click", function () {
        dd.classList.toggle("open");
    });
    dd.addEventListener("click", function (e) {
        var item = e.target.closest(".dropdown-item");
        if (!item) return;
        dd.querySelectorAll(".dropdown-item").forEach(function (i) {
            i.classList.remove("active");
        });
        item.classList.add("active");
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
        dd.classList.remove("open");
    });
    document.addEventListener("click", function (e) {
        if (!dd.contains(e.target)) dd.classList.remove("open");
    });
})();
