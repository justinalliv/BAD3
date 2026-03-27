from decimal import Decimal
from django.db import migrations, models


TREATMENT_METADATA = {
    'Termite Control': ('Targeted treatment for active termite activity.', Decimal('3000.00')),
    'Cockroach Control': ('Focused control for cockroach infestations.', Decimal('2000.00')),
    'General Pest Control Treatment': ('General-purpose treatment for common pests.', Decimal('2500.00')),
    'Mosquito Control': ('Mosquito population reduction treatment.', Decimal('1800.00')),
    'Rodent Control': ('Rodent monitoring and control treatment.', Decimal('2200.00')),
    'Bed Bug Treatment': ('Specialized treatment for bed bug infestations.', Decimal('2800.00')),
}


def populate_treatment_metadata(apps, schema_editor):
    ServiceFormOption = apps.get_model('sangapp', 'ServiceFormOption')

    treatment_qs = ServiceFormOption.objects.filter(
        form_section='Treatment',
        field_name='Treatment Service',
    )

    for option in treatment_qs:
        metadata = TREATMENT_METADATA.get(option.option_value)
        if not metadata:
            continue

        description, rate = metadata
        update_fields = []
        if not option.option_description:
            option.option_description = description
            update_fields.append('option_description')
        if option.option_rate is None:
            option.option_rate = rate
            update_fields.append('option_rate')

        if update_fields:
            option.save(update_fields=update_fields)


def clear_treatment_metadata(apps, schema_editor):
    ServiceFormOption = apps.get_model('sangapp', 'ServiceFormOption')
    ServiceFormOption.objects.filter(
        form_section='Treatment',
        field_name='Treatment Service',
    ).update(option_description='', option_rate=None)


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0021_remove_unreferenced_baygon_records'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceformoption',
            name='option_description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='serviceformoption',
            name='option_rate',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.RunPython(populate_treatment_metadata, reverse_code=clear_treatment_metadata),
    ]
