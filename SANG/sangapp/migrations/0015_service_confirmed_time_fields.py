from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0014_service_inspection_confirmed_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='inspection_confirmed_time',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='service',
            name='treatment_confirmed_time',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
