# Generated by Django 2.2.1 on 2019-05-28 10:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hotelrecommendation', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='gender',
            field=models.CharField(choices=[('M', 'Male'), ('F', 'Female')], default='M', max_length=1),
        ),
    ]
