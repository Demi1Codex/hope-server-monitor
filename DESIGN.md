 ---

## Prompt del diseño

> **Dashboard neon — servidores privados**  
> Diseño de dashboard oscuro con estética neon futurista, 2 tarjetas de monitoreo de servidores con animaciones al seleccionar.
>
> **Paleta de color:**
> - Fondo: `#0a0a0f` con grilla de líneas sutiles verdes/azules
> - Superficie: `#111118`, bordes `#1e1e2e`
> - Neon verde: `#00ff41` (requests, uptime, métricas en vivo)
> - Neon azul: `#00d4ff` (usuarios, sesiones, actividad)
> - Sombras glow: `0 0 20px rgba(0,255,65,0.3)` y `0 0 20px rgba(0,212,255,0.3)`
> - Tipografía: Inter (300-800)
>
> **Estructura:**
> - Header con logo gradient (verde→azul) e indicador de estado con pulso
> - Grid responsivo de 2 columnas → 1 col en mobile
> - Cada tarjeta tiene: badge, título, descripción, minigráfico de barras (20 bars random), fila de stats, lista de actividad
>
> **Animaciones al seleccionar tarjeta (click):**
> 1. **Ring burst** — anillo que se expande desde la tarjeta y se desvanece (0.8s)
> 2. **Línea glow** — línea superior que barre horizontalmente con gradiente neon
> 3. **Partículas** — 24 partículas neon que explotan radialmente desde posiciones aleatorias (0.5-1.1s)
> 4. **Barras del chart** se iluminan con glow al activarse
> 5. **Sombra exterior** intensa con glow del color correspondiente
> 6. **Indicador de selección** (punto glow animado esquina superior derecha)
> 7. Transición suave `cubic-bezier(0.22, 1, 0.36, 1)` en todo

---