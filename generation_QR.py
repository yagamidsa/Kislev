import qrcode

# Define el enlace estático
enlace = "http://127.0.0.1:8000/validar_enlace"

try:
    # Crea el objeto QR
    qr = qrcode.QRCode(
        version=1,  # Controla el tamaño del QR (1-40)
        error_correction=qrcode.constants.ERROR_CORRECT_L,  # Corrección de errores
        box_size=10,  # Tamaño de cada cuadro en píxeles
        border=4,  # Tamaño del borde
    )

    # Agrega el enlace al QR
    qr.add_data(enlace)
    qr.make(fit=True)

    # Crea una imagen del QR
    img = qr.make_image(fill_color="black", back_color="white")

    # Guarda la imagen
    img.save("codigo_qr_escanner.png")

    print("Código QR generado y guardado como 'codigo_qr_escanner.png'")
except Exception as e:
    print(f"Ocurrió un error al generar el código QR: {e}")