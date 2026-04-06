$(document).ready(function () {
    $(".dropholder").click(function (e) {
        e.stopPropagation();
        $(".menu").toggleClass("showMenu");
    });

    // Los clicks dentro del menú no cierran el menú ni bloquean la navegación
    $(".menu").click(function (e) {
        e.stopPropagation();
    });

    // Ocultar el menú si se hace clic fuera de la zona
    $(document).click(function () {
        $(".menu").removeClass("showMenu");
    });
});
