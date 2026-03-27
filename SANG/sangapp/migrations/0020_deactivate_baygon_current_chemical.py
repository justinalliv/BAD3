from django.db import migrations


def deactivate_baygon_current_chemical(apps, schema_editor):
    Chemical = apps.get_model('sangapp', 'Chemical')
    ServiceFormOption = apps.get_model('sangapp', 'ServiceFormOption')

    Chemical.objects.filter(name__iexact='Baygon', is_active=True).update(is_active=False)
    ServiceFormOption.objects.filter(
        form_section='Service Report Submission',
        field_name='Chemicals Used',
        option_value__iexact='Baygon',
        is_active=True,
    ).update(is_active=False)


def reactivate_baygon_current_chemical(apps, schema_editor):
    Chemical = apps.get_model('sangapp', 'Chemical')
    ServiceFormOption = apps.get_model('sangapp', 'ServiceFormOption')

    Chemical.objects.filter(name__iexact='Baygon', is_active=False).update(is_active=True)
    ServiceFormOption.objects.filter(
        form_section='Service Report Submission',
        field_name='Chemicals Used',
        option_value__iexact='Baygon',
        is_active=False,
    ).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0019_chemical_invoiceitem_service_item_and_more'),
    ]

    operations = [
        migrations.RunPython(
            deactivate_baygon_current_chemical,
            reverse_code=reactivate_baygon_current_chemical,
        ),
    ]
