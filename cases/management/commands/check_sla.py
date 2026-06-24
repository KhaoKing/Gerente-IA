from django.core.management.base import BaseCommand
from django.utils import timezone
from cases.models import CaseSession, CaseAudit


class Command(BaseCommand):
    help = 'Marca como vencidas las sesiones cuyo SLA ha expirado'

    def handle(self, *args, **options):
        now = timezone.now()
        overdue = CaseSession.objects.filter(
            sla_deadline__isnull=False,
            sla_breached=False,
            sla_deadline__lt=now,
        )

        count = 0
        for session in overdue:
            session.sla_breached = True
            session.save(update_fields=['sla_breached'])
            CaseAudit.objects.create(
                session=session, action='status_change',
                previous_status=session.status, new_status=session.status,
                observation='SLA vencido automáticamente',
            )
            count += 1
            self.stdout.write(
                self.style.WARNING(
                    f'SLA vencido — Sesión {session.id} ({session.user.get_full_name()})'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f'{count} sesiones marcadas con SLA vencido.')
        )
