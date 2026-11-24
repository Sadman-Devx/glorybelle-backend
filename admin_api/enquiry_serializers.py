from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from apps.enquiries.models import Enquiry, EnquiryNote


User = get_user_model()
ASSIGNABLE_USERS = (
    User.objects.filter(is_active=True, is_staff=True)
    .filter(Q(is_superuser=True) | Q(groups__name="Manager"))
    .distinct()
)


class AdminEnquiryListSerializer(serializers.ModelSerializer):
    topic_label = serializers.CharField(source="get_topic_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model = Enquiry
        fields = (
            "id",
            "name",
            "email",
            "topic",
            "topic_label",
            "atelier_type",
            "status",
            "status_label",
            "assigned_to",
            "assigned_to_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_assigned_to_name(enquiry) -> str | None:
        if enquiry.assigned_to is None:
            return None
        return enquiry.assigned_to.get_full_name().strip() or enquiry.assigned_to.get_username()


class AdminEnquiryNoteSerializer(serializers.ModelSerializer):
    author_id = serializers.IntegerField(read_only=True, allow_null=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = EnquiryNote
        fields = ("id", "body", "author_id", "author_name", "created_at")
        read_only_fields = fields

    @staticmethod
    def get_author_name(note) -> str | None:
        if note.author is None:
            return None
        return note.author.get_full_name().strip() or note.author.get_username()


class AdminEnquiryDetailSerializer(AdminEnquiryListSerializer):
    message = serializers.CharField(read_only=True)
    internal_notes = AdminEnquiryNoteSerializer(many=True, read_only=True)

    class Meta(AdminEnquiryListSerializer.Meta):
        fields = AdminEnquiryListSerializer.Meta.fields + (
            "message",
            "internal_notes",
        )


class AdminEnquiryUpdateSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=ASSIGNABLE_USERS,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Enquiry
        fields = ("status", "assigned_to")


class AdminEnquiryAssigneeSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "name", "email")
        read_only_fields = fields

    @staticmethod
    def get_name(user) -> str:
        return user.get_full_name().strip() or user.get_username()


class AdminEnquiryNoteCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=True)
