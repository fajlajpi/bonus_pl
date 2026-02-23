from django.db import migrations

def create_sales_rep_group(apps, schema_editor):
    """
    Creates the 'Sales Reps' group if it doesn't already exist.
    """
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Sales Reps')

def reverse_func(apps, schema_editor):
    """
    Reverse function - removes the 'Sales Reps' group.
    """
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Sales Reps').delete()

class Migration(migrations.Migration):
    dependencies = [
        ('pa_bonus', '0013_invoice_invoicebrandturnover_and_more'), 
    ]

    operations = [
        migrations.RunPython(create_sales_rep_group, reverse_func),
    ]