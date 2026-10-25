from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers
from .models import Category, Dish, RankHistory

class CategorySerializer(serializers.ModelSerializer):
    dish_count = serializers.SerializerMethodField()
    top_dish = serializers.SerializerMethodField()
    top_photo = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "position", "dish_count", "top_dish", "top_photo"]

    def get_dish_count(self, obj):
        return obj.dishes.count()

    def get_top_dish(self, obj):
        dish = obj.dishes.first()
        return dish.restaurant if dish else None

    def get_top_photo(self, obj):
        dish = obj.dishes.first()
        if dish and dish.photo:
            request = self.context.get("request")
            return request.build_absolute_uri(dish.photo.url) if request else dish.photo.url
        return None

    def validate_name(self, value):
        value = value.strip()
        clash = Category.objects.filter(owner=self.context["request"].user, name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("That category already exists.")
        return value

class RankHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RankHistory
        fields = ["rank", "recorded_at"]


class DishSerializer(serializers.ModelSerializer):
    history = RankHistorySerializer(many=True, read_only=True)
    rank = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Dish
        fields = ["id", "category", "name", "restaurant", "price", "note",
                  "date_tried", "map_link", "photo", "elo", "created_at",
                  "rank", "total", "history"]
        read_only_fields = ["elo", "created_at"]

    def get_rank(self, obj):
        ids = list(obj.category.dishes.values_list("id", flat=True))
        return ids.index(obj.id) + 1

    def get_total(self, obj):
        return obj.category.dishes.count()

    def validate_category(self, value):
        if value.owner_id != self.context["request"].user.id:
            raise serializers.ValidationError("That category is not yours.")
        return value

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    display_name = serializers.CharField(max_length=50)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_display_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter a display name.")
        return value

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(list(error.messages))
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class ProfileSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=50)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        try:
            password_validation.validate_password(value, self.context["request"].user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(list(error.messages))
        return value