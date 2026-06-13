---
name: gerenteia-context
description: Use when working on GerenteIA — a Django 4.2 platform for managerial skills training with AI-powered chat simulations. Provides project architecture, database schema, templates, and conventions. Front-load with keywords: GerenteIA, MAE, gerente, diagnosis, chat IA, casos gerenciales, dashboard.
---

# GerenteIA — Contexto del Proyecto

## Stack
- **Backend:** Django 4.2, Python 3.11+
- **DB:** PostgreSQL 15 (Docker, puerto 5433, contenedor `gerente_ia_db`)
- **AI:** Google Gemini API (`gemini-3.5-flash`) con fallback simulado
- **Frontend:** Django templates + vanilla CSS/JS
- **Dependencias clave:** `psycopg2-binary`, `Pillow`, `python-decouple`

## Estructura del Proyecto

```
GerenteIA/
├── accounts/           # Auth, modelo User custom, ManagerProfile
│   ├── models.py       # User(AbstractUser) con roles: admin/mae/gerente
│   ├── forms.py        # CreateUserForm, ManagerProfileForm
│   ├── views.py        # Login, register, complete_profile, create_user
│   └── urls.py
├── cases/              # App principal: casos, diagnóstico, chat IA, panel MAE
│   ├── models.py       # ManagementCase, DiagnosisSession, DiagnosisMessage,
│   │                   #   CaseSession, ChatMessage, IAErrorLog
│   ├── views.py        # dashboard, diagnóstico, chatbox, panel MAE
│   ├── ai_engine.py    # Gemini API integration + simulated fallback
│   └── urls.py
├── gerente_ia/         # Config Django (settings.py, urls.py, wsgi/asgi)
├── templates/
│   ├── base.html       # Layout base con navbar, fuentes (Syne + Inter)
│   ├── accounts/       # login, register, complete_profile, create_user
│   └── cases/          # dashboard, chat, diagnosis_chat, mae_diagnosis_review, mae_review
├── static/
│   ├── css/main.css    # Estilos globales — dark theme, design system
│   └── js/main.js
└── docker-compose.yml
```

## Roles de Usuario
| Rol | Clave | Propósito |
|-----|-------|-----------|
| Administrador | `admin` | Gestión del sistema, usuarios, casos |
| MAE | `mae` | Revisor humano — aprueba/rechaza diagnósticos y sesiones de caso |
| Gerente | `gerente` | Usuario final — hace diagnóstico y casos con IA |

## Modelos Principales

### DiagnosisSession (`cases/models.py:33`)
- Diagnóstico de 5 preguntas situacionales para evaluar nivel del gerente
- Campos clave: `user` (OneToOne), `status`, `current_question` (1-5), `mae`, `mae_approved`, `mae_verdict`, `mae_reviewed_at`
- Estados: `en_progreso`, `completado`, `aprobado`, `rechazado`, `nivel_asignado`

### CaseSession (`cases/models.py:81`)
- Chatbox con IA sobre casos gerenciales (3 fases: ambigüedad, presión, dilema)
- Campos clave: `user`, `case` (FK ManagementCase), `status`, `current_phase`, `score`, `mae`, `mae_approved`, `mae_verdict`, `mae_reviewed_at`
- Estados: `en_progreso`, `completado`, `en_revision`, `evaluado`

### ChatMessage (`cases/models.py:120`)
- Mensajes del chat de casos
- **Campos de métricas:** `response_time_seconds` (Float), `total_pause_seconds` (Float)
- Tipos: `normal`, `quick_reply`, `error_ia`, `system_info`

### DiagnosisMessage (`cases/models.py:66`)
- Mensajes del chat de diagnóstico (solo `user`/`assistant`, sin métricas de tiempo)

## URLs Principales (`cases/urls.py`)
| URL | Vista | Descripción |
|-----|-------|-------------|
| `/` o `/dashboard/` | `dashboard` | Dashboard según rol |
| `/diagnostico/iniciar/` | `start_diagnosis` | Iniciar diagnóstico |
| `/diagnostico/chat/` | `diagnosis_chat` | Chat de diagnóstico |
| `/caso/iniciar/` | `start_case` | Iniciar caso |
| `/caso/<id>/chat/` | `chat_view` | Chatbox de caso |
| `/mae/revision/<id>/` | `mae_review` | MAE revisa sesión de caso |
| `/mae/diagnostico/<id>/` | `mae_diagnosis_review` | MAE revisa diagnóstico |

## Vistas del Panel MAE
- `mae_diagnosis_review(request, session_id)` — línea 486 de `cases/views.py`
- `mae_review(request, session_id)` — línea 459 de `cases/views.py`
- Ambas requieren `@login_required` y verifican `request.user.is_mae`
- Manejan GET (mostrar) y POST (aprobar/rechazar con `mae_verdict` y `mae_approved`)

## Convenciones de Código
- Idioma: español para UI, inglés para código (nombres de variables, modelos)
- Templates extienden `base.html`
- CSS usa variables CSS en `:root` (dark theme)
- JavaScript vanilla con `fetch` para llamadas AJAX al backend
- CSRF token en todas las peticiones POST
- Timezone: `America/Mexico_City`
- Fuentes: Syne (display), Inter (body)

## Sistema de Diseño (CSS variables)
- Fondo principal: `--bg: #0d0f14`
- Tarjetas: `--bg-card: #1e2232`
- Acento primario: `--accent: #4f8ef7`
- Acento secundario: `--accent-2: #7c6af5`
- Texto: `--text: #e8eaf0`
- Radio bordes: `--radius: 12px`, `--radius-lg: 20px`

## Archivos de Configuración
- `gerente_ia/settings.py` — Config DB, Gemini API key, email, locale
- `docker-compose.yml` — PostgreSQL 15
- `requirements.txt` — Dependencias Python
