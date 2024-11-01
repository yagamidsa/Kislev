document.addEventListener('DOMContentLoaded', function() {
    // Crear iconos de fondo
    const backgroundIcons = document.querySelector('.background-icons');
    const iconTypes = ['parking-icon', 'car-small'];
    const numIcons = 20;

    // Timeline principal
    const mainTL = gsap.timeline();

    // Animación del título y subtítulo
    mainTL.from('h1', {
        duration: 1,
        y: -50,
        opacity: 0,
        ease: "elastic.out(1, 0.8)"
    })
    .from('header p', {
        duration: 0.5,
        y: 20,
        opacity: 0,
        ease: "back.out(1.7)"
    }, "-=0.5");

    // Crear y animar iconos de fondo
    for (let i = 0; i < numIcons; i++) {
        const iconWrapper = document.createElement('div');
        iconWrapper.className = 'floating-icon';
        
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.style.width = '60px';
        svg.style.height = '60px';
        
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttributeNS(
            'http://www.w3.org/1999/xlink',
            'xlink:href',
            `#${iconTypes[i % iconTypes.length]}`
        );
        
        svg.appendChild(use);
        iconWrapper.appendChild(svg);
        backgroundIcons.appendChild(iconWrapper);

        // Posición inicial aleatoria
        gsap.set(iconWrapper, {
            x: Math.random() * window.innerWidth,
            y: Math.random() * window.innerHeight,
            scale: Math.random() * 0.5 + 0.5,
            opacity: 0,
            rotation: Math.random() * 360
        });

        // Animación de entrada
        gsap.to(iconWrapper, {
            duration: 1,
            opacity: 0.8,
            delay: i * 0.1,
            ease: "power2.inOut"
        });

        // Animación de brillo pulsante
        gsap.to(iconWrapper, {
            duration: gsap.utils.random(2, 4),
            filter: 'brightness(1.5)',
            repeat: -1,
            yoyo: true,
            ease: "sine.inOut"
        });

        // Animación flotante continua
        gsap.to(iconWrapper, {
            duration: gsap.utils.random(8, 12),
            y: "+=100",
            x: "+=50",
            rotation: "+=360",
            repeat: -1,
            yoyo: true,
            ease: "none",
            delay: Math.random() * 2
        });

        // Efecto de parpadeo aleatorio
        const blinkTL = gsap.timeline({
            repeat: -1,
            delay: Math.random() * 5
        });

        blinkTL
            .to(iconWrapper, {
                duration: 0.1,
                opacity: 0.3,
                ease: "none"
            })
            .to(iconWrapper, {
                duration: 0.1,
                opacity: 0.8,
                ease: "none"
            })
            .to(iconWrapper, {
                duration: gsap.utils.random(2, 8),
                opacity: 0.8,
                ease: "none"
            });
    }

    // Animación mejorada de las tarjetas
    gsap.from('.parking-card', {
        duration: 0.8,
        scale: 0.5,
        y: 100,
        opacity: 0,
        stagger: 0.2,
        ease: "elastic.out(1, 0.8)",
        delay: 0.5
    });

    // Manejar clicks en las tarjetas con animaciones mejoradas
    const parkingCards = document.querySelectorAll('.parking-card');
    
    parkingCards.forEach(card => {
        // Timeline para la animación de las ruedas
        const wheelsTL = gsap.timeline({ paused: true });
        const wheels = card.querySelectorAll('.wheel-spokes');
        
        wheels.forEach(wheel => {
            wheelsTL.to(wheel, {
                duration: 1,
                rotation: 360,
                repeat: -1,
                ease: "none"
            }, 0);
        });

        // Crear timeline para hover
        const hoverTL = gsap.timeline({ paused: true });
        
        hoverTL
            .to(card, {
                duration: 0.3,
                scale: 1.05,
                y: -10,
                ease: "power2.out"
            })
            .to(card.querySelector('.glow-effect'), {
                duration: 0.3,
                opacity: 1,
                ease: "power2.out"
            }, 0)
            .to(card.querySelector('.vehicle-icon'), {
                duration: 0.4,
                scale: 1.1,
                y: -5,
                filter: "drop-shadow(0 0 20px var(--neon-color))",
                ease: "back.out(1.7)"
            }, 0);

        // Eventos hover
        card.addEventListener('mouseenter', () => {
            hoverTL.play();
            wheelsTL.play();
        });

        card.addEventListener('mouseleave', () => {
            hoverTL.reverse();
            wheelsTL.pause();
            gsap.to(wheels, {
                duration: 0.5,
                rotation: "+=0",
                ease: "power1.out"
            });
        });

        // Click con animación mejorada
        card.addEventListener('click', function() {
            const url = this.dataset.url;
            if (url) {
                gsap.timeline()
                    .to(this, {
                        duration: 0.1,
                        scale: 0.95,
                        ease: "power2.in"
                    })
                    .to(this, {
                        duration: 0.2,
                        scale: 1.05,
                        ease: "power2.out"
                    })
                    .to(this, {
                        duration: 0.1,
                        scale: 1,
                        onComplete: () => {
                            gsap.to(this, {
                                duration: 0.3,
                                opacity: 0,
                                scale: 0.8,
                                y: -50,
                                ease: "power2.in",
                                onComplete: () => {
                                    window.location.href = url;
                                }
                            });
                        }
                    });
            }
        });
    });

    // Animación de luz de fondo
    gsap.to('.light-effect', {
        duration: 10,
        background: 'radial-gradient(circle at 80% 20%, rgba(190, 24, 93, 0.15) 0%, transparent 60%), radial-gradient(circle at 20% 80%, rgba(190, 24, 93, 0.15) 0%, transparent 60%)',
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut"
    });
});