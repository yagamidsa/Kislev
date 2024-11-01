document.addEventListener('DOMContentLoaded', function() {
    // GSAP Animations
    gsap.registerPlugin(ScrollTrigger);
    
    // Animación de entrada para el título
    gsap.from('.title', {
        duration: 1.5,
        opacity: 0,
        y: -50,
        ease: 'power4.out'
    });
    
    // Animación para el subtítulo
    gsap.from('.subtitle', {
        duration: 1,
        opacity: 0,
        y: -20,
        ease: 'power3.out',
        delay: 0.5
    });
    
    // Animación de entrada para las tarjetas
    gsap.from('.zone-card', {
        duration: 1.2,
        scale: 0.8,
        opacity: 0,
        y: 100,
        ease: 'power3.out',
        stagger: 0.2,
        scrollTrigger: {
            trigger: '.zones-grid',
            start: 'top center+=100',
            toggleActions: 'play none none reverse'
        }
    });
    
    // Efectos de hover para las tarjetas
    const cards = document.querySelectorAll('.zone-card');
    
    cards.forEach(card => {
        let cardInner = card.querySelector('.card-inner');
        let glowEffect = card.querySelector('.glow-effect');
        
        // Efecto de movimiento 3D
        card.addEventListener('mousemove', (e) => {
            let rect = card.getBoundingClientRect();
            let x = e.clientX - rect.left;
            let y = e.clientY - rect.top;
            
            let midCardWidth = rect.width / 2;
            let midCardHeight = rect.height / 2;
            
            let angleY = -(x - midCardWidth) / 8;
            let angleX = (y - midCardHeight) / 8;
            
            cardInner.style.transform = `
                rotateX(${angleX}deg) 
                rotateY(${angleY}deg)
                scale3d(1.1, 1.1, 1.1)
            `;
            
            // Efecto de brillo siguiendo el cursor
            glowEffect.style.background = `
                radial-gradient(
                    circle at ${x}px ${y}px,
                    rgba(255, 20, 147, 0.4) 0%,
                    rgba(255, 20, 147, 0) 60%
                )
            `;
        });
        
        // Restaurar posición original
        card.addEventListener('mouseleave', () => {
            cardInner.style.transform = 'rotateX(0) rotateY(0) scale3d(1, 1, 1)';
            glowEffect.style.background = 'none';
        });
        
        // Efecto de clic con navegación
        card.addEventListener('click', () => {
            // Obtener la URL del atributo data-url
            const url = card.getAttribute('data-url');
            
            // Animación de clic
            gsap.to(cardInner, {
                duration: 0.1,
                scale: 0.95,
                yoyo: true,
                repeat: 1,
                ease: 'power2.inOut',
                onComplete: () => {
                    // Navegar a la URL después de que termine la animación
                    if (url && url !== '#') {
                        window.location.href = url;
                    }
                }
            });
        });
    });
    
    // Animación sutil del fondo
    const backgroundGrid = document.querySelector('.background-grid');
    gsap.to(backgroundGrid, {
        backgroundPosition: '100px 100px',
        duration: 20,
        repeat: -1,
        ease: 'none'
    });
});