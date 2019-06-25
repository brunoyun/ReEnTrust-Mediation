# Generated by Django 2.2.1 on 2019-06-24 11:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hotelrecommendation', '0013_rating_rating_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='type',
            field=models.CharField(choices=[('L', 'Leisure'), ('B', 'Business')], default='L', max_length=1),
        ),
    ]
