$(document).ready(function () {
    $(".dropdown").click(function (e) {
        e.stopPropagation(); // Evita que el clic se propague
        $(".menu").toggleClass("showMenu");
    });

    // Ocultar el menú si se hace clic fuera de la zona
    $(document).click(function () {
        $(".menu").removeClass("showMenu");
    });
});
