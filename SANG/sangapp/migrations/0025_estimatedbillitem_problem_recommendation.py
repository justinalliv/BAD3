from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0024_salesrepresentative_remove_property_country_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='estimatedbillitem',
            name='problem_text',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='estimatedbillitem',
            name='recommendation_text',
            field=models.TextField(blank=True),
        ),
    ]
