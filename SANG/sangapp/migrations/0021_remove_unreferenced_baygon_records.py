from django.db import migrations


def remove_unreferenced_baygon_records(apps, schema_editor):
    Chemical = apps.get_model('sangapp', 'Chemical')
    ServiceReportChemical = apps.get_model('sangapp', 'ServiceReportChemical')
    ServiceFormOption = apps.get_model('sangapp', 'ServiceFormOption')

    baygon_ids = list(Chemical.objects.filter(name__iexact='Baygon').values_list('id', flat=True))
    referenced_ids = set(
        ServiceReportChemical.objects.filter(chemical_id__in=baygon_ids).values_list('chemical_id', flat=True)
    )

    deletable_ids = [chemical_id for chemical_id in baygon_ids if chemical_id not in referenced_ids]
    if deletable_ids:
        Chemical.objects.filter(id__in=deletable_ids).delete()

    ServiceFormOption.objects.filter(
        form_section='Service Report Submission',
        field_name='Chemicals Used',
        option_value__iexact='Baygon',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0020_deactivate_baygon_current_chemical'),
    ]

    operations = [
        migrations.RunPython(remove_unreferenced_baygon_records, migrations.RunPython.noop),
    ]
