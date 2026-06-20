from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from cases.models import CaseSession


class Command(BaseCommand):
    help = 'Detecta sesiones abandonadas (>30 min sin heartbeat) y las marca como abandoned'

    def handle(self, *args, **options):
        threshold = timezone.now() - timedelta(minutes=30)

        active_sessions = CaseSession.objects.filter(status='en_progreso')

        count = 0
        for session in active_sessions:
            last_activity = session.last_heartbeat or session.messages.last().created_at if session.messages.exists() else session.started_at

            if last_activity and last_activity < threshold:
                session.status = 'abandoned'
                session.save(update_fields=['status'])
                count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'Sesión {session.id} ({session.user.get_full_name()}) marcada como abandonada'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f'{count} sesiones marcadas como abandonadas.')
        )
