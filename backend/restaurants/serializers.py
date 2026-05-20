from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    UserProfile,
    Shop,
    Favorite,
    VisitRecord,
    Rating,
    Comment,
    SearchHistory,
)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["display_name", "favorite_genre", "theme"]


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff", "profile"]
        read_only_fields = ["is_staff"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=4, write_only=True)
    display_name = serializers.CharField(max_length=100, required=False, default="")


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = "__all__"


class FavoriteSerializer(serializers.ModelSerializer):
    shop = ShopSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ["id", "shop", "created_at"]


class VisitRecordSerializer(serializers.ModelSerializer):
    shop = ShopSerializer(read_only=True)

    class Meta:
        model = VisitRecord
        fields = ["id", "shop", "visit_count", "updated_at"]


class RatingSerializer(serializers.ModelSerializer):
    shop = ShopSerializer(read_only=True)

    class Meta:
        model = Rating
        fields = ["id", "shop", "score", "updated_at"]


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "shop", "author_name", "text", "created_at", "updated_at"]
        read_only_fields = ["author_name", "created_at", "updated_at"]


class CommentReadSerializer(serializers.ModelSerializer):
    author_email = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "author_name",
            "author_email",
            "text",
            "created_at",
            "updated_at",
        ]

    def get_author_email(self, obj):
        return obj.user.email if obj.user else None


class SearchHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchHistory
        fields = ["id", "query_params", "result_count", "created_at"]
