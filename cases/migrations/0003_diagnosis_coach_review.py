from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cases', '0002_remove_casesession_feedback_casesession_coach_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='diagnosissession',
            name='coach',
            field=models.ForeignKey(
                blank=True, null=True,
                limit_choices_to={'role': 'coach'},
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reviewed_diagnoses',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='diagnosissession',
            name='coach_approved',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='diagnosissession',
            name='coach_verdict',
            field=models.TextField(blank=True, verbose_name='Dictamen del Coach sobre el diagnóstico'),
        ),
        migrations.AddField(
            model_name='diagnosissession',
            name='coach_reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='diagnosissession',
            name='status',
            field=models.CharField(
                max_length=20,
                default='en_progreso',
                choices=[
                    ('en_progreso', 'En Progreso'),
                    ('completado', 'Completado — esperando revisión coach'),
                    ('aprobado', 'Aprobado por Coach'),
                    ('rechazado', 'Rechazado por Coach'),
                    ('nivel_asignado', 'Nivel Asignado'),
                ],
            ),
        ),
    ]
