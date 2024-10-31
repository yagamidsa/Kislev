document.addEventListener('DOMContentLoaded', function() {
    // Crear partículas flotantes
    const particlesContainer = document.querySelector('.floating-particles');
    for (let i = 0; i < 5; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particlesContainer.appendChild(particle);
    }

    // Manejar clicks en las tarjetas
    const parkingCards = document.querySelectorAll('.parking-card');
    
    parkingCards.forEach(card => {
        card.addEventListener('click', function() {
            const url = this.dataset.url;
            if (url) {
                // Añadir efecto de click
                this.style.transform = 'scale(0.98)';
                setTimeout(() => {
                    this.style.transform = 'scale(1)';
                    window.location.href = url;
                }, 150);
            }
        });

        // Añadir efecto de hover suave
        card.addEventListener('mouseenter', function() {
            const glowEffect = this.querySelector('.glow-effect');
            glowEffect.style.opacity = '1';
        });

        card.addEventListener('mouseleave', function() {
            const glowEffect = this.querySelector('.glow-effect');
            glowEffect.style.opacity = '0';
        });
    });
});