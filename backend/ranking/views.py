"""The HTTP layer: authenticate, validate, call a service, return JSON."""

import uuid

from django.contrib.auth import get_user_model, login
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ranking import services
from ranking.models import RankList
from ranking.serializers import AnswerSerializer, CreateListSerializer, StartInsertionSerializer


def _ensure_guest(request: Request) -> None:
    """One browser = one guest, created on its first write.

    This runs after throttling and checks CSRF itself, because DRF only checks it
    for logged-in users. A rejected request therefore never creates a row.
    """
    if request.user.is_authenticated:
        return
    SessionAuthentication().enforce_csrf(request)
    guest = get_user_model().objects.create_user(username=f"guest-{uuid.uuid4().hex}")
    login(request._request, guest)
    request.user = guest


@method_decorator(ensure_csrf_cookie, name="dispatch")
class ListCollectionView(APIView):
    """GET also hands a new browser the CSRF cookie it needs for its first POST."""

    def get_permissions(self) -> list[BasePermission]:
        return [AllowAny()]

    def get(self, request: Request) -> Response:
        if not request.user.is_authenticated:
            return Response([])
        rows = RankList.objects.filter(owner=request.user).order_by("id")
        return Response([{"id": r.pk, "name": r.name, "version": r.version} for r in rows])

    def post(self, request: Request) -> Response:
        body = CreateListSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        _ensure_guest(request)
        ranked = RankList.objects.create(owner=request.user, name=body.validated_data["name"])
        return Response(services.list_payload(ranked), status=status.HTTP_201_CREATED)


class ListDetailView(APIView):
    def get(self, request: Request, list_id: int) -> Response:
        ranked = get_object_or_404(RankList, pk=list_id, owner=request.user)
        return Response(services.list_payload(ranked))


class InsertionCollectionView(APIView):
    def post(self, request: Request, list_id: int) -> Response:
        body = StartInsertionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = services.start_insertion(
            request.user, list_id, data["place_name"], data["city"], data.get("tier")
        )
        return Response(result, status=status.HTTP_201_CREATED)


class AnswerView(APIView):
    def post(self, request: Request, insertion_id: int) -> Response:
        body = AnswerSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = services.answer_question(
            request.user,
            insertion_id,
            data["question_index"],
            data["answer"],
            data.get("response_ms"),
        )
        return Response(result)


class AbandonView(APIView):
    def post(self, request: Request, insertion_id: int) -> Response:
        services.abandon_insertion(request.user, insertion_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
