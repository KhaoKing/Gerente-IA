from django.core.management.base import BaseCommand
from cases.models import ManagementCase
from accounts.models import User


class Command(BaseCommand):
    help = 'Carga casos y usuarios de prueba'

    def handle(self, *args, **kwargs):
        self.load_cases()
        self.create_users()
        self.stdout.write(self.style.SUCCESS('✅ Datos iniciales cargados.'))

    def load_cases(self):
        cases = [
            {'title':'El equipo dividido','description':'Eres gerente de un equipo de 8 personas. Dos colaboradores clave, Ana y Roberto, tienen un conflicto personal que está afectando la dinámica del equipo. Los demás miembros se están tomando bandos y la productividad ha bajado un 20% en dos semanas. Ana amenaza con renunciar si Roberto no es removido. Ambos son altamente competentes. ¿Cómo manejarías esta situación?','category':'conflicto','difficulty':'basico','key_competencies':'Resolución de conflictos, mediación, comunicación asertiva'},
            {'title':'La comunicación que no llega','description':'Tu equipo de ventas no cumple los objetivos del trimestre. Al investigar, descubres que muchos no conocen el nuevo proceso de cotización que enviaste por correo hace 3 semanas. Algunos dicen que no lo recibieron, otros que no lo entendieron. El director te presiona por resultados. ¿Qué haces ahora y cómo evitas que esto vuelva a pasar?','category':'comunicacion','difficulty':'basico','key_competencies':'Comunicación efectiva, canales, seguimiento'},
            {'title':'Delegar sin soltar el control','description':'Llevas meses trabajando horas extra porque es más rápido hacerlo yo mismo. Tu jefe te pide que desarrolles al equipo. Identificaste a Mariana como candidata para asumir la coordinación de reportes semanales, pero la última vez que delegaste una tarea importante, la persona cometió errores costosos. ¿Cómo procedes?','category':'delegacion','difficulty':'basico','key_competencies':'Delegación efectiva, desarrollo de talento, seguimiento sin microgestión'},
            {'title':'El colaborador desmotivado','description':'Carlos era tu mejor colaborador hace un año. Puntual, creativo, proactivo. En los últimos meses su rendimiento bajó, llega tarde y en la última reunión estuvo callado y distraído. Hoy te enteraste que está buscando trabajo activamente. ¿Qué harías ahora y cómo lo manejarías hacia adelante?','category':'motivacion','difficulty':'basico','key_competencies':'Motivación, escucha activa, retención de talento'},
            {'title':'La decisión urgente','description':'Uno de tus colaboradores clave comete un error grave que afecta a un cliente importante. El cliente exige una solución en 30 minutos. Tienes información incompleta y tu equipo espera que decidas. ¿Qué haces primero?','category':'decision','difficulty':'intermedio','key_competencies':'Toma de decisiones bajo presión, gestión de crisis, comunicación'},
            {'title':'El cambio que nadie quiere','description':'La empresa acaba de anunciar una reestructuración que cambia los procesos de trabajo de tu equipo. Hay resistencia generalizada, rumores y baja moral. Tú estuviste en contra del cambio pero la decisión ya está tomada. ¿Cómo lo manejas con tu equipo?','category':'cambio','difficulty':'intermedio','key_competencies':'Gestión del cambio, liderazgo, comunicación en adversidad'},
        ]
        created = 0
        for c in cases:
            _, new = ManagementCase.objects.get_or_create(title=c['title'], defaults=c)
            if new: created += 1
        self.stdout.write(f'  → {created} casos nuevos ({ManagementCase.objects.count()} total)')

    def create_users(self):
        users = [
            {'username':'admin','password':'admin123','role':'admin','email':'admin@gerenteIA.com','first_name':'Admin','last_name':'Sistema','is_staff':True,'is_superuser':True},
            {'username':'coach1','password':'coach123','role':'coach','email':'coach@gerenteIA.com','first_name':'Laura','last_name':'Méndez','is_staff':False,'is_superuser':False},
            {'username':'gerente1','password':'gerente123','role':'gerente','email':'gerente@gerenteIA.com','first_name':'Carlos','last_name':'Ruiz','is_staff':False,'is_superuser':False},
        ]
        created = 0
        for d in users:
            if not User.objects.filter(username=d['username']).exists():
                User.objects.create_user(
                    username=d['username'], password=d['password'], role=d['role'],
                    email=d['email'], first_name=d['first_name'], last_name=d['last_name'],
                    is_staff=d['is_staff'], is_superuser=d['is_superuser'],
                )
                created += 1
        self.stdout.write(f'  → {created} usuarios nuevos')
        self.stdout.write('  admin/admin123 · coach1/coach123 · gerente1/gerente123')
