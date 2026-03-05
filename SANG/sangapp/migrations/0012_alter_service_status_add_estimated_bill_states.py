from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0011_invoice_invoiceitem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='service',
            name='status',
            field=models.CharField(
                choices=[
                    ('For Inspection', 'For Inspection'),
                    ('Ongoing Inspection', 'Ongoing Inspection'),
                    ('Estimated Bill Created', 'Estimated Bill Created'),
                    ('Estimated Bill Confirmed', 'Estimated Bill Confirmed'),
                    ('For Treatment', 'For Treatment'),
                    ('Ongoing Treatment', 'Ongoing Treatment'),
                    ('Pending Payment', 'Pending Payment'),
                    ('Payment Confirmed', 'Payment Confirmed'),
                    ('Completed', 'Completed'),
                    ('Cancelled', 'Cancelled'),
                ],
                default='For Inspection',
                max_length=50,
            ),
        ),
    ]
