from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CardViewSet, ColumnViewSet, SubtaskViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("columns", ColumnViewSet, basename="column")
router.register("cards", CardViewSet, basename="card")
router.register("subtasks", SubtaskViewSet, basename="subtask")

urlpatterns = router.urls
