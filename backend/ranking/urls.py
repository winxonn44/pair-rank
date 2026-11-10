"""API routes."""

from django.urls import path

from ranking import views

urlpatterns = [
    path("lists/", views.ListCollectionView.as_view()),
    path("lists/<int:list_id>/", views.ListDetailView.as_view()),
    path("lists/<int:list_id>/insertions/", views.InsertionCollectionView.as_view()),
    path("insertions/<int:insertion_id>/answers/", views.AnswerView.as_view()),
    path("insertions/<int:insertion_id>/abandon/", views.AbandonView.as_view()),
]
