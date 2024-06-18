# Generated by Django 4.2.13 on 2024-06-18 11:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('track', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='total_estimated_hours',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='task',
            name='estimated_hours',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='timetrack',
            name='task_type',
            field=models.PositiveSmallIntegerField(choices=[(1000, 'Design'), (1100, 'Development'), (1200, 'DevOps'), (2000, 'Documentation'), (3000, 'Documentation'), (4000, 'Meeting'), (5000, 'QA')]),
        ),
    ]