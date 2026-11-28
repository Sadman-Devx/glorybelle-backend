"""Data migration: active newsletter subscribers retain consent."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def test_existing_active_subscribers_are_grandfathered_as_confirmed():
    executor = MigrationExecutor(connection)
    latest_migrations = executor.loader.graph.leaf_nodes()
    migration_1 = ("newsletter", "0001_initial")
    migration_2 = (
        "newsletter",
        "0002_newslettersubscriber_confirmation_nonce_and_more",
    )

    try:
        executor.migrate([migration_1])
        old_apps = executor.loader.project_state([migration_1]).apps
        OldSubscriber = old_apps.get_model("newsletter", "NewsletterSubscriber")
        active = OldSubscriber.objects.create(
            email="legacy-active@example.com",
            is_active=True,
        )
        inactive = OldSubscriber.objects.create(
            email="legacy-unsubscribed@example.com",
            is_active=False,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([migration_2])
        migrated_apps = executor.loader.project_state([migration_2]).apps
        Subscriber = migrated_apps.get_model(
            "newsletter", "NewsletterSubscriber"
        )

        assert Subscriber.objects.get(pk=active.pk).is_confirmed
        assert not Subscriber.objects.get(pk=inactive.pk).is_confirmed
    finally:
        MigrationExecutor(connection).migrate(latest_migrations)
