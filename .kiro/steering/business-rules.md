---
inclusion: always
---

# Reglas de Negocio — Adventure Tracker

El archivo de referencia completo es `docs/business.rules.md`. Este archivo existe para que lo tengas **siempre en contexto** y puedas mantenerlo actualizado.

## Cómo usar este steering file

Cada vez que modifiques lógica de dominio en este proyecto, actualiza `docs/business.rules.md` reflejando el cambio. No documentes implementación interna; documenta **decisiones de negocio**: qué hace el sistema, por qué, y qué restricciones aplican.

---

## Resumen ejecutivo de las reglas (referencia rápida)

### Notificaciones
- Canal activo: **email únicamente** (Resend API). Telegram está descartado por ahora.
- No configurar `TELEGRAM_BOT_TOKEN` ni `TELEGRAM_CHAT_ID` en producción.
- Errores dentro del proceso → orquestador llama `send_error_report()` al final de `run()`.
- Crash total del CI job → job `notify-failure` en `tracker.yaml` llama `send_error_report()` con mensaje genérico.
- Secrets requeridos: `RESEND_API_KEY`, `EMAIL_TO`, `GIST_ID`, `GIST_TOKEN`.
- Rutas: **BAQ→MDE** (ida, jue/vie) y **MDE→BAQ** (vuelta, dom/lun).
- Precios son **one-way** por tramo. Umbral: 300,000 COP.
- Política de aerolíneas (orden de precedencia):
  1. LATAM (prioritaria) → incluir si precio ≤ umbral de ruta.
  2. Cualquier aerolínea si precio ≤ 110,000 COP (ganga).
  3. Reglas extra en `routes.yaml` (Wingo/JetSMART/Avianca ≤ 150k).
  4. Resto → descartar.
- Ventanas horarias — dependen del día en que empieza/termina la aventura en MDE (el usuario está en BAQ, hay tramo extra):
  - **Ida**: Jue 18-24h (aventura empieza jue/vie) · Vie 0-16h (aventura empieza vie o sáb).
  - **Vuelta**: Lun 0-10h si la aventura termina el domingo en MDE (~8PM, no es posible volar ese día) · **Martes** si la aventura termina el lunes en MDE.
  - Domingo **NO** es ventana válida de regreso. Vuelos fuera de ventana se descartan.
- Horizonte por defecto: **10 semanas** (~2.5 meses).

### Reporte consolidado
- Un `WeekendPair` por cada vuelo de ida barato encontrado.
- **Regla del domingo**: si hay eventos de agencia el domingo → solo mostrar vuelos de regreso del lunes.
- **Regla de preferencia LATAM en vuelta**: mantener LATAM salvo que otra aerolínea ahorre ≥ 100,000 COP.
- Máximo 3 opciones de vuelta por fin de semana.
- No se envían alertas individuales; solo el reporte final consolidado.

### Actividades (Instagram)
- El scraper de Instagram está **inoperativo** para este caso de uso: no encuentra las imágenes de calendarios de las agencias.
- El flujo real de eventos es **exclusivamente manual**: el usuario coloca imágenes en `inbox/<agencia>/` y el sistema las procesa con Gemini.
- El módulo `ActivityTrackerService` existe en el código pero no aporta valor hasta que se resuelva el acceso programático a esas imágenes.
- Cuentas de referencia: `brutaltravel.co` y `medellinbungee`.

### Extracción de imágenes
- Imágenes en `inbox/<agencia>/`, detectadas por magic bytes (no extensión).
- Proveedor: Gemini si `GEMINI_API_KEY` presente, sino Ollama local.
- Cache en `data/extraction_cache.yaml`. Precios válidos: 10,000 – 10,000,000 COP.

### Feriados y puentes
- Fuente: `config/holidays.yaml` (actualizar anualmente con `scripts/update_holidays.py`).
- Puente: lunes feriado, o viernes feriado, o jueves anterior feriado.

### Entornos
- **Local**: solo archivos YAML locales. Gist desactivado aunque esté en `.env`.
- **CI** (`GITHUB_ACTIONS=true`): estado adicional en GitHub Gist.

---

## Reglas que nunca debes romper

1. No activar ruta CTG sin evaluar el tiempo de traslado BAQ→CTG.
2. Nunca incluir destinos de playa en notificaciones.
3. No subir `MAX_CHECK_COUNT` (3) sin evaluar costos de API.
4. Actualizar `config/holidays.yaml` cada año.
5. Las imágenes en `inbox/` deben estar organizadas en subdirectorios por agencia.
6. Las alertas individuales de vuelo no se envían; siempre esperar al reporte consolidado del orquestador.

---

## Cuándo actualizar `docs/business.rules.md`

Actualiza el archivo cuando cambies cualquiera de estas cosas:

- Umbrales de precio (`price_threshold`, `bargain_threshold`, `max_price` de aerolíneas).
- Ventanas horarias por día (`TIME_FILTERS` en `flight_tracker.py`).
- Lógica del reporte consolidado (`_build_weekend_pairs` en `main.py`).
- Reglas de blacklist o categorías en `config/destinations.yaml`.
- Límite de revisiones de posts (`MAX_CHECK_COUNT` en `activity_history.py`).
- Horizonte temporal de búsqueda (`DEFAULT_WEEKS_AHEAD`).
- Nuevas aerolíneas prioritarias o extra.
- Nuevas cuentas de Instagram monitoreadas.
- Cualquier nueva regla de negocio que afecte qué se notifica y cuándo.

No actualizar el documento por: refactoring interno, cambios de tests, ajustes de formato, o mejoras de logging.
