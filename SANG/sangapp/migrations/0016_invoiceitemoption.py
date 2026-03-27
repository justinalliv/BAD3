from decimal import Decimal
from django.db import migrations, models


def seed_invoice_item_options(apps, schema_editor):
    InvoiceItemOption = apps.get_model('sangapp', 'InvoiceItemOption')
    default_options = [
        ('General Pest Control Treatment', Decimal('2500.00')),
        ('Termite Control', Decimal('3000.00')),
        ('Rodent Control', Decimal('2200.00')),
        ('Mosquito Control', Decimal('1800.00')),
        ('Bed Bug Treatment', Decimal('2800.00')),
        ('Cockroach Control', Decimal('2000.00')),
        ('Other', Decimal('1500.00')),
    ]

    for name, price in default_options:
        InvoiceItemOption.objects.get_or_create(
            name=name,
            defaults={
                'default_unit_price': price,
                'is_active': True,
            },
        )


def unseed_invoice_item_options(apps, schema_editor):
    InvoiceItemOption = apps.get_model('sangapp', 'InvoiceItemOption')
    InvoiceItemOption.objects.filter(
        name__in=[
            'General Pest Control Treatment',
            'Termite Control',
            'Rodent Control',
            'Mosquito Control',
            'Bed Bug Treatment',
            'Cockroach Control',
            'Other',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0015_service_confirmed_time_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvoiceItemOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('default_unit_price', models.DecimalField(decimal_places=2, default=1500, max_digits=12)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'invoice_item_options',
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(seed_invoice_item_options, unseed_invoice_item_options),
    ]
