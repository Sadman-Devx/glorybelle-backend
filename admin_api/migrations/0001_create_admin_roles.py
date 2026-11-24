from django.db import migrations


def create_admin_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    database = schema_editor.connection.alias
    Group.objects.using(database).get_or_create(name="Manager")
    Group.objects.using(database).get_or_create(name="Viewer")


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_admin_roles, migrations.RunPython.noop),
    ]
