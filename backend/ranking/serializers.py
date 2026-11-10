"""Validate what comes in. Responses are plain dictionaries built in services.py."""

from rest_framework import serializers

from ranking.models import Answer, Tier


class CreateListSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=100)


class StartInsertionSerializer(serializers.Serializer):
    place_name = serializers.CharField(min_length=1, max_length=120)
    city = serializers.CharField(min_length=1, max_length=100, default="Los Angeles")
    tier = serializers.ChoiceField(choices=Tier.values, required=False)


class AnswerSerializer(serializers.Serializer):
    question_index = serializers.IntegerField(min_value=0)
    answer = serializers.ChoiceField(choices=Answer.values)
    response_ms = serializers.IntegerField(min_value=0, max_value=2**31 - 1, required=False)
