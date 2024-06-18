# Generated by Django 4.2.13 on 2024-06-14 17:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Milestone',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=225)),
                ('is_archived', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ['-id'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=225)),
                ('is_archived', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ['-id'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='TimeTrack',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('task_type', models.PositiveSmallIntegerField(choices=[(1, 'Development'), (2, 'Quality Assurance'), (3, 'Designing'), (4, 'Meeting'), (5, 'Meeting (Internal)')])),
                ('description', models.TextField(blank=True)),
                ('is_done', models.BooleanField(default=False)),
                ('duration', models.DurationField(blank=True, null=True)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='track.task')),
            ],
        ),
    ]