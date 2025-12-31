from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biopsy_result', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='biopsyresult',
            name='verified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name='biopsy_results', to='user.user'),
        ),
    ]
