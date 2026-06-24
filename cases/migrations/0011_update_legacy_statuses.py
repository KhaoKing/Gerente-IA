from django.db import migrations

def update_legacy_statuses(apps, schema_editor):
    CaseSession = apps.get_model('cases', 'CaseSession')
    CaseSession.objects.filter(status='en_revision').update(status='en_validacion')
    CaseSession.objects.filter(status='evaluado').update(status='cerrado')

class Migration(migrations.Migration):
    dependencies = [
        ('cases', '0010_casesession_priority_casesession_sla_breached_and_more'),
    ]
    operations = [
        migrations.RunPython(update_legacy_statuses),
    ]
