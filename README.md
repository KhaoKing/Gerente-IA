# Gerente IA 🧠

Plataforma de capacitación y certificación gerencial con IA.

**Stack:** Django 4.2 · PostgreSQL (Docker) · Python 3.11+

---

## Requisitos previos

Asegúrate de tener instalado en tu sistema:

- [Docker](https://docs.docker.com/engine/install/) + [Docker Compose](https://docs.docker.com/compose/install/)
- Python 3.11+
- Git

Verifica que los servicios estén activos:

```bash
python3 --version
docker --version
docker compose version
```

---

## 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd gerente_ia
```

---

## 2. Crear el entorno virtual

```bash
# Crear entorno con Python 3.11
python3 -m venv GerenteIA

# Activar el entorno
source GerenteIA/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

> Para desactivar el entorno cuando termines: `deactivate`  
> Para eliminarlo si lo necesitas: `rm -rf GerenteIA`

---

## 3. Levantar PostgreSQL con Docker

Crea el archivo `docker-compose.yml` en la raíz del proyecto:

```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    container_name: gerente_ia_db
    restart: unless-stopped
    environment:
      POSTGRES_DB: gerente_ia_db
      POSTGRES_USER: gerente_user
      POSTGRES_PASSWORD: gerente_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Levanta el contenedor:

```bash
docker compose up -d
```

Verifica que esté corriendo:

```bash
docker ps
# Deberías ver: gerente_ia_db   Up X seconds
```

---

## 4. Configurar la conexión a la base de datos

Edita `gerente_ia/settings.py` y ajusta el bloque `DATABASES` para que coincida con las credenciales del `docker-compose.yml`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'gerente_ia_db',
        'USER': 'gerente_user',
        'PASSWORD': 'gerente_pass',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## 5. Migraciones y datos iniciales

Con el entorno virtual activo y el contenedor Docker corriendo:

```bash
# Generar migraciones
python manage.py makemigrations accounts
python manage.py makemigrations cases
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate

# Cargar casos y usuarios de prueba
python manage.py load_initial_data
```

---

## 6. Levantar el servidor

```bash
python manage.py runserver
```

Abre en tu navegador: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Ejecutar como servicio en segundo plano

```bash
nohup python manage.py runserver > server.log 2>&1 &
```

- Los logs se guardan en `server.log`
- Para verlos en vivo: `tail -f server.log`
- Para detenerlo: `kill $(pgrep -f "manage.py runserver")`

---

## Usuarios de prueba

| Usuario | Contraseña | Rol | Notas |
|---------|-----------|-----|-------|
| `admin` | `admin123` | Administrador | Acceso a `/admin/` |
| `mae1` | `mae123` | MAE | Vista de gerentes y sesiones |
| `gerente1` | `gerente123` | Gerente | Sin perfil completado (flujo completo) |

> Al hacer login con `gerente1` se redirige automáticamente al formulario de perfil antes de ver el dashboard.

---

## Flujo de la aplicación

```
Login
  ├── Admin    → Dashboard con métricas + panel /admin/
  ├── MAE    → Dashboard con lista de gerentes y sesiones
  └── Gerente
        ├── (primer login) → Completar perfil
        └── Dashboard → Iniciar caso → Chatbox con IA
```

---

## Comandos útiles del día a día

```bash
# Activar entorno
source GerenteIA/bin/activate

# Iniciar base de datos (si el contenedor está detenido)
docker compose up -d

# Ver logs de la base de datos
docker compose logs -f db

# Detener el contenedor sin borrar datos
docker compose stop

# Eliminar contenedor Y datos (cuidado en producción)
docker compose down -v

# Crear un superusuario manualmente
python manage.py createsuperuser

# Abrir shell de Django
python manage.py shell

# Conectarse directo a PostgreSQL
docker exec -it gerente_ia_db psql -U gerente_user -d gerente_ia_db
```

---

## Estructura del proyecto

```
gerente_ia/
├── gerente_ia/                  # Configuración principal
│   ├── settings.py              # Base de datos, apps, Claude API key
│   └── urls.py
├── accounts/                    # Autenticación y perfiles
│   ├── models.py                # User (custom) + ManagerProfile
│   ├── views.py                 # login, logout, complete_profile
│   ├── forms.py
│   └── urls.py
├── cases/                       # Casos gerenciales y chatbox
│   ├── models.py                # ManagementCase, CaseSession, ChatMessage
│   ├── views.py                 # dashboard, start_case, chat, send_message
│   ├── ai_engine.py             # Motor IA — simulado / Claude API
│   ├── urls.py
│   └── management/commands/
│       └── load_initial_data.py # Carga casos y usuarios de prueba
├── templates/
│   ├── base.html
│   ├── accounts/
│   │   ├── login.html
│   │   └── complete_profile.html
│   └── cases/
│       ├── dashboard.html
│       └── chat.html
├── static/
│   ├── css/main.css
│   └── js/main.js
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Conectar Claude API (siguiente fase)

1. Obtén tu API key en [https://console.anthropic.com](https://console.anthropic.com)

2. Agrega la key en `gerente_ia/settings.py`:

```python
CLAUDE_API_KEY = 'sk-ant-...'
```

3. En `cases/ai_engine.py`, comenta el bloque `SIMULATED MODE` y descomenta el bloque `CLAUDE API MODE`. No hay que tocar ningún otro archivo.

---

## Solución de problemas comunes

**Error: `could not connect to server`**
→ El contenedor de Docker no está corriendo. Ejecuta `docker compose up -d`.

**Error: `python3: command not found`**
→ Python no está instalado o no está en el PATH. Instala Python 3.11+.

**Error: `relation does not exist`**
→ Faltan migraciones. Ejecuta `python manage.py migrate`.

**Puerto 5432 ocupado**
→ Tienes otra instancia de PostgreSQL corriendo. Detén el servicio local: `sudo systemctl stop postgresql`.
