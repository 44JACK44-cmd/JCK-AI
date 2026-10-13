# Desarrollo de NEXUS AI

## Estado: Fase 4 en curso — 4.1-4.3 completadas (Monaco, terminal persistente, Git); 4.5 APK Android compilado; 4.4 Tauri requiere Rust

### Fase 1 (Fundación) — completada
- Estructura del repositorio, FastAPI + Vite/React, adaptador DeepSeek base

### Fase 2 (Base funcional) — completada
- Modelos SQLAlchemy, JWT, endpoints completos, terminal segura, explorador de archivos, SSE cerebro, emparejamiento de dispositivos

### Fase 3 (Multi-IA completa) — completada
- **Keystore cifrado** (`services/keystore.py`): API keys cifradas con Fernet (AES-128-CBC+HMAC), nunca expuestas en claro. Endpoint `/api/v1/keys/` con guardado, listado enmascarado, verificación real y borrado.
- **Adaptador Google Gemini real** (`adapters/google.py`): API oficial `generativelanguage.googleapis.com`, con streaming nativo (`streamGenerateContent?alt=sse`), detección de rate-limit (429), y verificación de clave. **Tier gratuito genuino** vía AI Studio (15 RPM flash).
- **Clasificación honesta de DeepSeek**: verificado con llamada real → 402 "Insufficient Balance". DeepSeek API es prepago, NO tiene tier gratuito. Clasificado `PAID_ROUTE_BLOCKED` en FREE MODE.
- **Streaming SSE** (`services/streaming.py`): endpoint `/api/v1/tasks/chat/stream` con eventos `start`/`chunk`/`done`/`error`. Adaptadores con `supports_native_stream=True` usan streaming real; el resto usa fallback con chunks progresivos.
- **Modo C — Orquestador de objetivos** (`services/orchestestr_c.py`): descompone un objetivo en un DAG de subtareas usando un proveedor LLM, ejecuta respetando dependencias en paralelo, reintenta fallos transitorios (hasta `task_max_retries`), cancela subtareas con dependencias fallidas, y produce un informe con resultados, errores, intentos y latencia. Endpoint `/api/v1/tasks/orchestrate`.
- **Enrutamiento adaptativo (Nivel 2)** (`services/routing.py`): registra éxitos/fallos/latencia por proveedor y clase de tarea. Calcula score compuesto (0.7·éxito + 0.3·latencia) con rampa de confianza. Compara con baseline uniforme y muestra mejora esperada. Endpoint `/api/v1/brain/routing`.
- **Frontend actualizado**: gestión de claves en Configación (con enlaces a AI Studio), chat con streaming en tiempo real, selector de Modo A/B/C, panel de subtareas del orquestador.

## Proveedores — estado verificado (2026-10-12)

| Proveedor | Tier gratuito | Estado | Método de acceso | Notas |
|-----------|--------------|--------|------------------|-------|
| Google Gemini | **Sí** (verificado con llamadas reales) | `FREE_AVAILABLE` | API key desde [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Clave configurada y operativa |
| DeepSeek | **No** (verificado: 402) | `PAID_ROUTE_BLOCKED` | API key + prepago | Sin saldo = 402. Ruta de pago. |
| Anthropic | Parcial (créditos iniciales) | `AUTH_REQUIRED` | API key | Sin tier gratuito permanente |
| OpenAI | No | `PAID_ROUTE_BLOCKED` | API key | Pago obligatorio |

### Cuotas gratuitas de Gemini (medidas empíricamente)

| Modelo | Límite observado | Estado |
|--------|------------------|--------|
| `gemini-3.8-flash` (principal) | **20 solicitudes** por ventana (~2h) | Cuota agotada en pruebas → failover |
| `gemini-3-flash-preview` | Cuota propia, sin agotar | Operativo |
| `gemini-3.1-flash-lite` | Cuota propia, sin agotar | Operativo |
| `gemini-flash-latest` | Agotada (mismo grupo que principal) | 429 en pruebas |

**Failover automático**: si el modelo principal devuelve 429/404/5xx, el adaptador
prueba en cadena los demás modelos gratuitos (solo antes de emitir el primer chunk
en streaming) y reporta el modelo realmente usado.

### Enrutamiento adaptativo persistente
- Cada llamada a un proveedor se registra en memoria (Nivel 1, `memory_entries`) con
  proveedor, clase de tarea, latencia y resultado.
- Los contadores del router se **rehidratan desde la BD al arrancar**: las métricas
  sobreviven reinicios del backend.
- `GET /api/v1/brain/routing` devuelve scores compuestos (0.7·éxito + 0.3·latencia),
  confianza por muestra y recomendación por clase de tarea con mejora esperada frente
  a la línea base uniforme.

## Comandos de desarrollo

```bash
# Backend
cd backend
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# Frontend
npm install
npm run dev --workspace=frontend
npm run build --workspace=frontend

# Pruebas
python -m pytest tests -v
```

## Fase 4 — estado (2026-10-12)

| # | Entrega | Estado |
|---|---------|--------|
| 4.1 | Editor Monaco + vista de diferencias | ✅ |
| 4.2 | Terminal integrada con historial persistente | ✅ |
| 4.3 | Integración Git (status, diff, commit, init) | ✅ verificado E2E |
| 4.4 | Empaquetado Tauri (Windows) | ⚠️ scaffold + iconos listos; **falta instalar Rust (`rustup`)** |
| 4.5 | APK Android (Capacitor) | ✅ `app-debug.apk` compilada (~4.2 MB) |

### Detalles

- **Monaco**: `@monaco-editor/react` en `Projects.tsx` — `Editor` + `DiffEditor` (original vs modificado), detección de lenguaje por extensión, indicador "● sin guardar", tema claro/oscuro.
- **Terminal persistente**: `GET /api/v1/terminal/history` (tabla `ExecutionLog`, ≤200 entradas, stdout truncado a 4000 chars). `Agent.tsx` muestra historial del servidor + rechazos locales, selector de cwd (`policy.authorized_roots`), recall ↑/↓ y quick commands.
- **Git**: `backend/api/endpoints/git.py` — `GET /projects/git/status`, `GET /projects/git/diff`, `POST /projects/git/commit`, `POST /projects/git/init`. Todo vía argv fijo sin shell + `resolve_and_check_cwd` (paths fuera de raíces → 403; paths que empiezan por `-` o contienen `..` → 400). `GitPanel` en `Projects.tsx` con stage por checkbox, diff raw y form de commit. Sin upstream → ahead/behind = 0 (no es error).
- **Android (Capacitor 6)**: workspace `apps/android`. La UI se empaqueta desde `frontend/dist` con `VITE_BACKEND_URL` (IP LAN del PC embebida en el build) — alternativa editable: `localStorage.nexus_backend_url`. El backend debe escuchar en la LAN: `uvicorn ... --host 0.0.0.0 --port 8000`. CORS incluye orígenes WebView en `config.py cors_origins`.
- **Tauri**: scaffold en `apps/windows/src-tauri` (`Cargo.toml`, `tauri.conf.json`, `main.rs`, iconos generados con `npx tauri icon`). El cliente detecta Tauri (`IS_TAURI` en `api.ts`) y llama a `http://127.0.0.1:8000/api/v1`. **No compilable en esta máquina: no hay `cargo`/`rustc`.** Instalar Rust con `rustup` y luego `npm run build --workspace=apps/windows`.

### Comandos nuevos

```bash
# Android — sincronizar UI y compilar APK debug
npm run sync --workspace=apps/android     # cap sync (copia frontend/dist)
npm run apk --workspace=apps/android      # gradlew assembleDebug
# APK resultante: apps/android/android/app/build/outputs/apk/debug/app-debug.apk

# Windows — requiere Rust (rustup) instalado
npm run build --workspace=apps/windows    # tauri build → instalador .msi/.nsis

# Backend accesible desde el móvil (misma red)
cd backend && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```
