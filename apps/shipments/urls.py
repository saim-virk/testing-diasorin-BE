from django.urls import path

from . import api, api_actions

urlpatterns = [
    path("requests", api.RequestListCreateView.as_view(), name="requests"),
    path("requests/export.csv", api.RequestExportView.as_view(), name="requests-export"),
    path("requests/<str:ref>", api.RequestDetailView.as_view(), name="request-detail"),
    path("requests/<str:ref>/steps/<int:n>", api.StepSaveView.as_view(), name="request-step"),
    path("requests/<str:ref>/draft", api.DraftSaveView.as_view(), name="request-draft"),
    path("requests/<str:ref>/discard", api.DiscardView.as_view(), name="request-discard"),
    path("requests/<str:ref>/submit", api.SubmitView.as_view(), name="request-submit"),
    path("requests/<str:ref>/approve", api_actions.ApproveView.as_view(), name="request-approve"),
    path("requests/<str:ref>/reject", api_actions.RejectView.as_view(), name="request-reject"),
    path("requests/<str:ref>/return", api_actions.ReturnView.as_view(), name="request-return"),
    path("requests/<str:ref>/cancel", api_actions.CancelView.as_view(), name="request-cancel"),
    path(
        "requests/<str:ref>/reassign-approver",
        api_actions.ReassignApproverView.as_view(),
        name="request-reassign-approver",
    ),
    path(
        "requests/<str:ref>/skip-approval",
        api_actions.SkipApprovalView.as_view(),
        name="request-skip-approval",
    ),
    path("requests/<str:ref>/comments", api_actions.CommentsView.as_view(), name="request-comments"),
    path("requests/<str:ref>/events", api_actions.EventsView.as_view(), name="request-events"),
    path("approvals", api_actions.ApprovalsView.as_view(), name="approvals"),
    path(
        "approvals/my-cost-centres", api_actions.MyCostCentresView.as_view(), name="approvals-my-cost-centres"
    ),
    path("me/counts", api_actions.MeCountsView.as_view(), name="me-counts"),
    path("requests/<str:ref>/duplicate", api.DuplicateView.as_view(), name="request-duplicate"),
    path("requests/<str:ref>/attachments", api.AttachmentListView.as_view(), name="request-attachments"),
    path(
        "requests/<str:ref>/attachments/<int:att_id>",
        api.AttachmentDetailView.as_view(),
        name="request-attachment",
    ),
]
