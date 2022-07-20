from django.views.generic import ListView
from django.db.models import Q
from django.urls import reverse_lazy

from django.contrib.auth.models import User
from isghome.models import Notification
from django.core.paginator import Paginator

from django.http import JsonResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy


class MyincoNotificationListView(ListView):
    template_name = "myinco_admin/notification/list.html"
    model = Notification
    ordering = ("-ctime",)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return str(
            reverse_lazy("myinco_admin-notification-list")
        )  # success_url may be lazy

    def get_queryset(self):
        queryset = super().get_queryset()
        keyword = self.request.GET.get("keyword")
        ordering = self.get_ordering()

        if keyword:
            queryset = queryset.filter(
                Q(id__icontains=keyword)
                | Q(target_user__profile__name__icontains=keyword)
                | Q(log__user__profile__name__icontains=keyword)
                | Q(log__page_name__icontains=keyword)
            )

        queryset = queryset.filter(target_user=self.request.user)

        if ordering:
            if isinstance(ordering, str):
                ordering = (ordering,)
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        objects = context_data["object_list"]
        context_data["total_objects_count"] = objects.count()
        context_data["total_object_list"] = context_data["object_list"]
        p = Paginator(objects, 10)
        context_data["object_list"] = p.page(1)
        context_data["page"] = 1
        return context_data


def notification_page_ajax(request):
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = Notification.objects.all()

    if keyword:
        queryset = queryset.filter(
            Q(target_user__profile__name__icontains=keyword)
            | Q(log__user__profile__name__icontains=keyword)
        )

    queryset = queryset.filter(target_user=request.user)

    ordering = ("-ctime",)
    if ordering:
        if isinstance(ordering, str):
            ordering = (ordering,)
        queryset = queryset.order_by(*ordering)

    try:
        p = Paginator(queryset, 10)
        queryset = p.page(int(page))
        context = {"object_list": queryset, "page": int(page)}

        return JsonResponse(
            {
                "data": render_to_string(
                    "myinco_admin/notification/list_ajax.html", context
                ),
                "status": True,
            }
        )
    except Exception as e:
        print(e)
        return JsonResponse(
            {
                "status": False,
            }
        )


def open_notification_detail_modal(request):
    object_id = request.POST.get("notification_id")
    user_id = request.POST.get("user_id")

    notification = Notification.objects.get(id=object_id)
    user = User.objects.get(id=user_id)

    try:
        context = {
            "object": notification,
            "user": user,
        }

        return JsonResponse(
            {
                "data": render_to_string(
                    "myinco_admin/notification/list_modal.html", context
                ),
                "status": True,
            }
        )
    except Exception as e:
        print(e)
        return JsonResponse(
            {
                "status": False,
            }
        )


def notification_read_check_ajax(request):
    object_id = request.POST.get("notification_id")

    notification = Notification.objects.get(id=object_id)
    notification.is_check = True
    notification.save()

    return JsonResponse(
        {
            "data": {"is_check": True},
            "status": True,
        }
    )


def notification_all_read_ajax(request):
    print(request.__dict__)
    notifications = Notification.objects.filter(target_user=request.user)
    notifications.update(is_check=True)
    return HttpResponseRedirect(request.environ["HTTP_REFERER"])
