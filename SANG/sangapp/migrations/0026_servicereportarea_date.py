from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sangapp', '0025_estimatedbillitem_problem_recommendation'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicereportarea',
            name='date',
            field=models.DateField(blank=True, null=True),
        ),
    ]