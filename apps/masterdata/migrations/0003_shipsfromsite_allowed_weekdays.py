import django.contrib.postgres.fields
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("masterdata", "0002_seed_reference_data")]

    operations = [
        migrations.AddField(
            model_name="shipsfromsite",
            name="allowed_weekdays",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.PositiveSmallIntegerField(
                    validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(6),
                    ]
                ),
                blank=True,
                default=list,
                size=None,
            ),
        ),
    ]
