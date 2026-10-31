from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from urllib.parse import quote

from rest_framework import serializers
from .models import Category, Dish, RankHistory, ToEatItem

class CategorySerializer(serializers.ModelSerializer):
    dish_count = serializers.SerializerMethodField()
    top_dish = serializers.SerializerMethodField()
    top_photo = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "position", "dish_count", "top_dish", "top_photo", "is_uncategorized"]

    def get_dish_count(self, obj):
        return obj.dishes.count()

    def get_top_dish(self, obj):
        dish = obj.dishes.first()
        return dish.restaurant if dish else None

    def get_top_photo(self, obj):
        dish = obj.dishes.exclude(photo="").exclude(photo__isnull=True).first()
        if dish:
            request = self.context.get("request")
            return request.build_absolute_uri(dish.photo.url) if request else dish.photo.url
        return None

    def validate_name(self, value):
        value = value.strip()
        if self.instance and self.instance.is_uncategorized:
            if value != self.instance.name:
                raise serializers.ValidationError("Uncategorized can't be renamed.")
            return value
        if value.lower() == "uncategorized":
            raise serializers.ValidationError("That name is reserved.")
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
    is_uncategorized = serializers.BooleanField(source="category.is_uncategorized", read_only=True)

    class Meta:
        model = Dish
        fields = ["id", "category", "name", "restaurant", "price", "note",
                  "date_tried", "map_link", "photo", "elo", "created_at",
                  "rank", "total", "history", "place_id", "is_uncategorized"]
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data.get("map_link") and instance.place_id:
            data["map_link"] = (
                "https://www.google.com/maps/search/?api=1"
                f"&query={quote(instance.restaurant)}&query_place_id={instance.place_id}"
            )
        return data
    

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

def make_snippet(text, query, radius=22):
    index = text.lower().find(query.lower()) if query else -1
    if index == -1:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


class SearchResultSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    note_snippet = serializers.SerializerMethodField()

    class Meta:
        model = Dish
        fields = ["id", "restaurant", "name", "photo", "category", "category_name", "note_snippet"]

    def get_note_snippet(self, obj):
        return make_snippet(obj.note, self.context.get("q", ""))

class ToEatSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    map_link = serializers.SerializerMethodField()

    class Meta:
        model = ToEatItem
        fields = ["id", "restaurant", "name", "note", "place_id", "category", "category_name",
                  "map_link", "position", "created_at"]
        read_only_fields = ["position", "created_at"]

    def get_category_name(self, obj):
        return obj.category.name if obj.category else ""

    def get_map_link(self, obj):
        if not obj.place_id:
            return ""
        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query={quote(obj.restaurant)}&query_place_id={obj.place_id}"
        )

    def validate_restaurant(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter the restaurant.")
        return value

    def validate_category(self, value):
        if value is None:
            return None
        if value.owner_id != self.context["request"].user.id:
            raise serializers.ValidationError("That category is not yours.")
        return None if value.is_uncategorized else value