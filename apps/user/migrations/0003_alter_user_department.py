# Generated by Django 4.2.13 on 2024-06-18 14:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0002_user_department'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='department',
            field=models.PositiveSmallIntegerField(choices=[(1000, 'Data Analyst'), (1100, 'Development'), (1200, 'Development'), (2000, 'Management'), (3000, 'Project Manager'), (5000, 'QA')], null=True),
        ),
    ]
