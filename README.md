# NEXUS AI - Plataforma Multi-IA Universal

Plataforma completa multi-IA para Windows y Android que combina:

## 🎯 **Capacidades principales:**

1. **Navegador multi-IA:** Uso unificado de proveedores compatibles
2. **Colaboración entre modelos:** Tarea única → respuestas múltiples → síntesis verificada
3. **Agente de desarrollo autónomo:** Análisis, creación, modificación y pruebas de proyectos reales
4. **Cerebro de orquestación observable:** Estado real de tareas, agentes, herramientas y resultados
5. **Aprendizaje progresivo:** Memoria de experiencias verificadas, enrutamiento adaptativo

## 🏗️ **Arquitectura técnica:**

### Frontend
- React + TypeScript + Vite
- Editor de código integrado (Monaco)
- Panel cerebro visual interactivo
- Temas claro/oscuro adaptables

### Backend
- Python + FastAPI + Pydantic
- Servicios asíncronos concurrentes
- Adaptadores independientes por proveedor
- Orquestador basado en estados y eventos

### Datos
- PostgreSQL (local o remoto) + pgvector opcional
- SQLite para desarrollo local
- Migraciones versionadas

### Aplicaciones nativas
- **Windows:** Tauri 2 + instalador .exe/.msi
- **Android:** Capacitor + APK firmado
- Comunicación segura entre dispositivos

## 🔒 **Política FREE MODE:**

Priorizamos integraciones con rutas autorizadas de coste cero:
- DeepSeek v3.2 (integración verificada)
- Google Gemini (cuota gratuita)
- Proveedores con API gratuita/cuota gratuita
- Sin llamadas facturables por defecto
- Protección de claves y secretos

## 🚀 **Flujo de trabajo:**

1. **Selección de proveedores** - Catálogo verificable de modelos disponibles
2. **Conversación individual o colaborativa** - Modos A/B según necesidad
3. **Desarrollo autónomo** - Análisis → planificación → implementación → pruebas
4. **Observación en tiempo real** - Panel cerebro con métricas reales
5. **Memoria y aprendizaje** - Experiencias verificadas para mejora continua

## 📋 **Estado actual:**

✅ **Fase 1: Fundación** - Estructura base implementada
🔧 **Fase 2: Frontend/Backend base** - En desarrollo
🔜 **Fase 3: Primer proveedor funcional** - DeepSeek v3.2
🔜 **Fase 4: Sistema multi-IA** - Concurrencia y comparador
🔜 **Fase 5: Agente local Windows** - Explorador y terminal seguros
🔜 **Fase 6: Desarrollo autónomo** - Planificador y agentes
🔜 **Fase 7: Cerebro visual** - Panel interactivo
🔜 **Fase 8: Memoria y aprendizaje** - Persistencia y adaptación
🔜 **Fase 9: Aplicación Windows** - Tauri e instaladores
🔜 **Fase 10: Aplicación Android** - Capacitor y APK
🔜 **Fase 11: Validación final** - Tests y documentación

## 🛠️ **Instalación y desarrollo:**

```bash
# Instalar dependencias
npm install
pip install -r requirements.txt

# Desarrollo frontend
npm run dev

# Desarrollo backend
python -m uvicorn backend.api.main:app --reload

# Base de datos
docker-compose up -d postgres  # o usar SQLite local
```

## 📞 **Contacto y contribución:**

Este proyecto sigue un desarrollo incremental con funcionalidades verificables. Cada fase entrega componentes funcionales y pruebas ejecutables.

---

*"No simulamos conexiones. Verificamos integraciones reales."*