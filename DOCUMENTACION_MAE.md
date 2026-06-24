# GerenteIA — Documentación del Sistema MAE
## Plataforma de Entrenamiento en Habilidades Gerenciales con IA

---

## 1. Actores del Sistema

| Actor | Rol técnico | Propósito en el sistema |
|-------|-------------|------------------------|
| **Gerente** | `gerente` | Usuario final. Realiza un diagnóstico inicial y entrena con casos gerenciales simulados por IA. |
| **Docente Tutor (MAE)** | `mae` | Supervisor humano. Revisa diagnósticos y sesiones de caso, emite veredictos, escala problemas. |
| **Administrador** | `admin` | Gestiona usuarios, casos, configuración de IA y monitorea errores del sistema. |

---

## 2. Flujo Completo del Gerente

### 2.1 Diagnóstico Inicial (5 preguntas situacionales)
1. El gerente inicia sesión y ve un solo botón: **"Iniciar diagnóstico"**
2. El sistema (MAE-IA) le hace 5 preguntas abiertas sobre toma de decisiones, manejo de conflictos, delegación, comunicación y liderazgo
3. Al completar las 5, el diagnóstico queda en estado **"Esperando validación del Docente Tutor"**
4. El gerente no puede acceder al chatbox de casos hasta que un Docente Tutor apruebe su diagnóstico

**Estados del diagnóstico:** `En Progreso` → `Esperando validación` → `Aprobado` (habilita casos) o `Rechazado` (debe repetir)

### 2.2 Casos Gerenciales (Chatbox con IA)
1. Con diagnóstico aprobado, el gerente inicia un **caso gerencial** aleatorio según su nivel
2. Completa una **pre-evaluación** (control percibido, confianza en la IA, declaración del ego)
3. El chatbox simula 3 fases con el MAE-IA:
   - **Fase 1 — Ambigüedad:** detectar puntos ciegos del caso
   - **Fase 2 — Presión:** surge un agravante externo, margen reducido
   - **Fase 3 — Dilema:** solución eficiente pero con riesgo ético/reputacional
4. Cada respuesta del gerente es clasificada por la IA como **Ac** (Acoplamiento Exitoso), **Sm** (Sincronía Metódica) o **Ts** (Trauma Sistémico)
5. El algoritmo **NC_hs** calcula un índice de -1.000 a +1.000 en tiempo real
6. Al decir "evaluar", la sesión se completa y pasa al Docente Tutor para revisión
7. El gerente completa una **post-autopsia cognitiva** (reflexión del choque, estrategia, leyes de soberanía e identidad)

---

## 3. Flujo Completo del Docente Tutor (MAE)

### 3.1 Dashboard del Docente Tutor
Al ingresar, el MAE ve un panel unificado con:

**Barra de filtros global** (persistente entre vistas)
- Fecha desde/hasta, Estado, Prioridad, Categoría, Gerente
- Al aplicar filtros, **todo** el dashboard responde: diagnósticos, casos, directorio y exportación

**Tarjetas KPI** (clicables, bajan a la sección correspondiente)
- Diagnósticos por revisar | Casos pendientes | En revisión | Gerentes activos
- **SLA Vencidos** (rojo) | **Críticos** (naranja, alta prioridad + SLA vencido)
- **Escalados** (violeta) | **% Cumplimiento SLA** (verde/naranja/rojo)

**Secciones del dashboard:**
1. **SLA Vencido** — alerta roja con sesiones fuera de tiempo
2. **Bandeja de diagnósticos** — diagnósticos esperando validación, con antigüedad en cola y botones Detalle/Revisar
3. **En revisión** — sesiones que el MAE actual está evaluando
4. **Cola de revisión** — casos completados, con tiempo en cola, prioridad y observaciones previas. Botones: Expediente, Revisar y Escalar (⚠)
5. **Directorio de Gerentes** — tabla agregada por gerente: carga activa, pendientes, alertas SLA, NC_hs promedio y tendencia (▲/▼)
6. **Registro de Sesiones** — tabla detallada sesión por sesión con cronómetro SLA en vivo
7. **Casos Escalados** — casos que requieren atención de otro Docente Tutor
8. **Métricas** — serie temporal 7 días + segmentación por categoría de caso
9. **Alertas de Deserción** — sesiones abandonadas (>30 min sin actividad)
10. **Exportación CSV** — exporta los datos visibles según filtros activos

### 3.2 Revisión de Diagnóstico
1. El MAE hace clic en **Detalle** para ver el expediente completo:
   - Datos de la sesión con timestamps
   - Perfil del gerente (cargo, empresa, industria, experiencia, nivel)
   - Las 5 preguntas y respuestas completas
   - Resumen de la IA con nivel sugerido
   - **Bitácora de Auditoría** (creación → completado → veredicto)
2. Al hacer clic en **Revisar**, aprueba o rechaza con veredicto escrito
3. Si aprueba, el gerente queda habilitado para iniciar casos
4. Si rechaza, el gerente debe repetir el diagnóstico

### 3.3 Revisión de Caso
1. Al abrir un caso desde la cola, la sesión pasa automáticamente a **"En Validación"** (registrado en bitácora)
2. El MAE ve:
   - Metadatos del caso (categoría, dificultad, fase, NC_hs, contadores Ac/Sm/Ts)
   - Retroalimentación de la IA sobre el desempeño del gerente
   - **Transcripción completa** con métricas por mensaje: tiempo de lectura (ms), ejecución (ms), backspaces, clasificación IA
   - **Bitácora de Auditoría** con cada evento de la sesión (creación → cambio de estado → revisión → veredicto)
3. El MAE emite su **dictamen**:
   - ✅ **Aprobar** → caso cerrado, registrado como `approved`
   - ❌ **Rechazar** → caso observado, el gerente debe corregir y reenviar
4. Opción de **⚠️ Escalar caso** si requiere intervención de otro Docente Tutor

### 3.4 Escalamiento
1. El MAE escribe el **motivo** del escalamiento
2. Opcionalmente selecciona otro Docente Tutor para **reasignar** el caso
3. El caso pasa a estado **Escalado** y aparece en la sección dedicada del dashboard
4. Se registra doble entrada en bitácora: transición de estado + reasignación

### 3.5 Expediente del Caso (Vista detallada)
Accesible desde el botón **📋 Expediente** en cualquier lista. Muestra:
- **Panel de información**: tipo, dificultad, prioridad, estado, fase, SLA con deadline y tiempo restante
- **Perfil del gerente**: cargo, empresa, industria, experiencia, nivel asignado
- **Métricas NC_hs**: índice, interacciones, Ac, Sm, Ts
- **Pre-evaluación y Post-autopsia** lado a lado
- **Historial de Auditoría** completo con fechas, usuarios, acciones, estados y observaciones
- **Transcripción completa** de la conversación gerente-MAE

### 3.6 Directorio de Gerentes
Tabla de productividad con **métricas agregadas por gerente**:
- Total de sesiones | Carga activa (en progreso) | Pendientes de revisión
- Alertas SLA (sesiones vencidas) | NC_hs promedio
- **Tendencia** (▲ subió / ▼ bajó respecto a la sesión anterior)

---

## 4. Máquina de Estados de CaseSession

```
nuevo ────────► en_progreso ──────► completado ──────► en_validacion
                    │                                      │
                    │ (abandono)                  ┌────────┼────────┐
                    ▼                            ▼        ▼        ▼
                abandoned                    observado  cerrado  escalado
                                                │                   │
                                                ▼                   │
                                            corregido ──────────────┘
                                                │
                                                ▼
                                          en_validacion
```

Cada transición está validada por `ALLOWED_TRANSITIONS`. Intentar una ruta inválida (ej: `completado → cerrado` sin pasar por revisión) lanza `ValueError`. Cada transición genera automáticamente una entrada en `CaseAudit` con: fecha, usuario, acción, estado anterior, estado nuevo y observación.

---

## 5. SLA (Acuerdo de Nivel de Servicio)

- Cada caso tiene un `sla_hours` configurable (default 48h)
- Al iniciar una sesión se calcula `sla_deadline = ahora + sla_hours`
- **Cronómetro visual** en el dashboard: cuenta regresiva en vivo ("3h 15m restantes"), se pone naranja al bajar de 1h, rojo al vencer
- Comando `python manage.py check_sla` (para cron) marca automáticamente `sla_breached = True` y registra en bitácora
- El dashboard muestra alerta roja de SLA Vencidos y KPIs de cumplimiento

---

## 6. Nuevas Vistas y URLs

| URL | Vista | Acceso |
|-----|-------|--------|
| `/mae/diagnostico/<id>/detalle/` | Expediente de diagnóstico | MAE, Admin |
| `/mae/escalar/<id>/` | Escalar caso con reasignación | MAE |
| `/mae/exportar/csv/` | Exportación filtrada | MAE, Admin |

---

## 7. Cobertura de la Matriz de Auditoría

| # | Módulo | Estado | Implementación |
|---|--------|--------|---------------|
| 1 | KPIs avanzados | ✅ | Vencidos, críticos, escalados, % cumplimiento SLA en tarjetas del dashboard |
| 2 | Bandeja de diagnósticos | ✅ | Filtrada por gerente/fecha, con antigüedad, detalle y revisión |
| 3 | Cola de revisión | ✅ | Tiempo en cola, prioridad, observaciones previas, botón de escalar |
| 4 | Directorio de gerentes | ✅ | Carga de trabajo, alertas, productividad (NC_hs), tendencia ▲/▼ |
| 5 | Métricas de respuesta | ✅ | Serie temporal 7 días, segmentación por categoría |
| 6 | Exportación | ✅ | CSV respeta filtros activos, nombre de archivo dinámico |
| 7 | Flujo de estados | ✅ | Máquina de 9 estados con transiciones validadas y auditadas |
| 8 | Trazabilidad | ✅ | Bitácora de auditoría en cada cambio de estado, visible en review y expediente |
| 9 | SLA | ✅ | Cronómetro visual, detección automática de vencidos, alertas y KPIs |
| 10 | Escalamiento | ✅ | Workflow completo con motivo, reasignación y sección dedicada |
| 11 | Filtros globales | ✅ | Barra persistente que afecta diagnósticos, casos, directorio y exportación |
| 12 | Vista detalle expediente | ✅ | Historial completo, evidencias (pre/post), transcripción, bitácora, acciones |
