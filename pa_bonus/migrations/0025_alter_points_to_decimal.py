from django.db import migrations, models
import decimal


class Migration(migrations.Migration):

    dependencies = [
        ('pa_bonus', '0024_remove_usercontractgoal_brands_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pointstransaction',
            name='value',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
        migrations.AlterField(
            model_name='pointsbalance',
            name='points',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
        migrations.AlterField(
            model_name='reward',
            name='point_cost',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
        migrations.AlterField(
            model_name='rewardrequest',
            name='total_points',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=10),
        ),
        migrations.AlterField(
            model_name='rewardrequestitem',
            name='point_cost',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
    ]
