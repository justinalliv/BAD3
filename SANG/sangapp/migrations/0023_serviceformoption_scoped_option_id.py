from django.db import migrations, models


def populate_scoped_ids(apps, schema_editor):
    ServiceFormOption = apps.get_model('sangapp', 'ServiceFormOption')

    groups = {}
    for option in ServiceFormOption.objects.all().order_by('form_section', 'field_name', 'option_value', 'id'):
        key = (option.form_section, option.field_name)
        groups.setdefault(key, 0)
        groups[key] += 1
        option.scoped_option_id = groups[key]
        option.save(update_fields=['scoped_option_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0022_serviceformoption_treatment_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceformoption',
            name='scoped_option_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(populate_scoped_ids, migrations.RunPython.noop),
    ]
