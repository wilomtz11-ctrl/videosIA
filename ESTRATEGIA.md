# Estrategia del canal · investigación de octubre 2026

## Decisión: "Geografía explicada"

Cada video responde una pregunta que despierta curiosidad y la explica con mapas animados:
historia, geopolítica y economía. La pregunta es el gancho, y quien la escucha se queda hasta el final para saber la respuesta.

- En inglés esta fórmula funciona muy bien (Aaron Atlases, Borderline Wonders, el estilo de Johnny Harris).
  **En español casi no hay canales que la hagan con animación de calidad.**
- Tema que no pasa de moda, que genera debate en comentarios y que sirve en corto y en largo con el mismo código.
- Videos de historia y documental con público de EE. UU., Canadá o Europa: **$4–9 USD por cada mil vistas** (RPM).

### Próximos temas
1. ¿Por qué Bolivia no tiene mar? ✅ (`episodios/bolivia_mar.json`)
2. ¿Por qué Brasil habla portugués? (Tratado de Tordesillas)
3. ¿Por qué Panamá era parte de Colombia? (1903)
4. ¿Por qué México perdió la mitad de su territorio? (le interesa al público hispano de EE. UU.)
5. ¿Por qué Chile es tan largo y delgado?
6. ¿Por qué Paraguay tiene dos idiomas oficiales?
7. ¿Por qué casi nadie vive en la Patagonia?
8. Países que ya no existen
9. ¿Por qué Rusia es tan grande?
10. ¿Por qué Estados Unidos compró Alaska?

Cada cierto tiempo conviene un tema de economía en mapas (salarios, costo de vida, remesas): atrae anunciantes que pagan más.

## Dónde está el dinero

| Formato | Pago por cada mil vistas (aprox. 2026) | Rol |
|---|---|---|
| **YouTube largo (8–15 min), público de EE. UU.** | $4–9 | **Ingreso principal** |
| YouTube largo, público latino | ~$1 | Ingreso |
| YouTube Shorts | 3–14 % de lo que paga un largo (~$0.33 con público de EE. UU.) | Atraer gente al canal |
| Facebook (Ecuador es elegible) | $0.30–1 en Latinoamérica | Extra |
| TikTok | Ver la advertencia de abajo | Crecimiento |

**Plan:** 3–4 videos cortos y 1 largo por semana. El corto atrae, el largo paga.
Más adelante, un canal en inglés con el mismo código: se produce casi gratis y paga varias veces más.

## Riesgos y cómo los evitamos

| Riesgo | Medida |
|---|---|
| **TikTok con cuenta de EE. UU. viviendo en Ecuador.** El programa de pagos exige ser residente legal del país, prohíbe usar VPN y verifica identidad, datos fiscales, dispositivo y ubicación. Tener datos fiscales de EE. UU. no te hace residente | Usar TikTok solo para crecer y llevar gente a YouTube. Si en algún momento resides de verdad en un país elegible, se activa ahí |
| YouTube desmonetiza por "contenido genérico o repetitivo" (julio 2026; en enero 2026 cerró canales que sumaban 35 M de suscriptores) | Guion propio y verificado en cada video, tu voz (o tu voz clonada), fuentes en la descripción, y variar el gancho y el cierre. Calidad antes que volumen |
| No marcar el contenido hecho con IA | Activar "contenido alterado o sintético" en YouTube Studio y la etiqueta de IA en TikTok cuando la voz sea sintética. La etiqueta no quita la monetización; ocultarlo sí |
| Errores históricos | Cada dato con fuente en el JSON (`publicacion.fuentes`), y revisión antes de publicar |
| Música con reclamos de derechos | Solo música de la Biblioteca de audio de YouTube o con licencia comercial clara. Los efectos se generan con código |
| Datos de mapas (GPL-3.0) | Crédito visible en cada video; los mapas incluyen errores conocidos que corregimos con formas derivadas |

## Impuestos (consúltalo con un contador)

- El Programa de socios de YouTube está disponible en Ecuador.
- YouTube retiene impuestos de EE. UU. sobre lo que generan los espectadores de EE. UU. Para quien no es residente
  de EE. UU. y vive en un país sin tratado fiscal con ese país, la retención es del **30 %** de esa parte. Si no envías
  tus datos fiscales, la retención puede ser de hasta el 24 % de **todos** tus ingresos.
- Tu situación con datos fiscales de EE. UU. depende de tu estatus migratorio y fiscal (W-9 vs. W-8BEN). Un contador te dice qué formulario te toca.

## Lista antes de publicar

- [ ] Cada dato del guion tiene fuente
- [ ] La voz suena natural y se entiende a 1x
- [ ] Gancho en los primeros 2 segundos (texto + voz)
- [ ] Más de 60 s en la versión de TikTok
- [ ] Descripción con fuentes (`salida/*_descripcion.txt`)
- [ ] Etiqueta de contenido sintético activada si la voz es de IA
- [ ] Música con licencia comercial
- [ ] Miniatura y título con la pregunta

## Fuentes de esta investigación

- Términos del programa de pagos de TikTok: [EE. UU.](https://www.tiktok.com/legal/page/global/creator-rewards-program-us/en) · [Europa](https://www.tiktok.com/legal/page/global/tiktok-creator-rewards-program-eea/en) · [verificación de identidad](https://www.tiktok.com/creator-academy/article/verify-identity-to-collect-payouts)
- [Políticas de monetización de YouTube](https://support.google.com/youtube/answer/1311392) · [Disponibilidad del Programa de socios](https://support.google.com/youtube/answer/7101720?hl=es-419)
- [Cambio de política de YouTube, julio 2026](https://creatorblade.com/blog/youtube-inauthentic-content-policy-2026-stay-monetized) · [Cierres de canales 2026](https://flocker.tv/posts/youtube-inauthentic-content-ai-enforcement/)
- [Pago de Shorts vs. videos largos (274 canales)](https://air.io/en/air-data-findings/youtube-shorts-rpm-vs-long-form-how-much-do-shorts-earn-in-2026) · [RPM de canales de historia](https://fluxnote.io/blog/history-youtube-channel-guide-2026)
- [Canales de geografía sin rostro 2026](https://blog.autonolab.com/niches/2026-01-16-faceless-youtube-geography/)
- [Retenciones de impuestos de EE. UU. a creadores extranjeros](https://pbl.legal/insights/tax-guide-international-creators-youtubers/)
- [Chatterbox](https://huggingface.co/ResembleAI/chatterbox) · [Licencias de Piper y Coqui](https://www.promptquorum.com/power-local-llm/local-tts-voice-cloning-piper-coqui-xtts)
