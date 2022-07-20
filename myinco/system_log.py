from django.views.generic import ListView
from django.db.models import Q
from django.urls import reverse_lazy

from django.contrib.auth.models import User
from isghome.models import SystemLog
from django.core.paginator import Paginator

from django.http import JsonResponse
from django.template.loader import render_to_string


class MyincoSystemLogListView(ListView):
    template_name = "myinco_admin/system_log/list.html"
    model = SystemLog
    ordering = ("-ctime",)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return str(
            reverse_lazy("myinco_admin-systemlog-list")
        )  # success_url may be lazy

    def get_queryset(self):
        queryset = super().get_queryset()
        keyword = self.request.GET.get("keyword")
        ordering = self.get_ordering()

        if keyword:
            queryset = queryset.filter(
                Q(id__icontains=keyword)
                | Q(model__icontains=keyword)
                | Q(page_name__icontains=keyword)
                | Q(url__icontains=keyword)
                | Q(user__profile__name__icontains=keyword)
            )

        # auth_queryset_ids = []
        # for instance in queryset:
        #     if instance.model_name == "SalesActivity":
        #         model_object = apps.get_model("isghome", instance.model_name)
        #         members = model_object.auth_group.get_child_users()

        #         if self.request.user in members:
        #             auth_queryset_ids.append(instance.id)

        #         if (
        #             self.request.user.profile.auth_grade
        #             >= model_object.auth_grade
        #             and instance.id not in auth_queryset_ids
        #         ):
        #             auth_queryset_ids.append(instance.id)

        # queryset = queryset.filter(id__in=auth_queryset_ids)

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


def systemlog_page_ajax(request):
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = SystemLog.objects.all()

    if keyword:
        queryset = queryset.filter(
            Q(model__icontains=keyword)
            | Q(page_name__icontains=keyword)
            | Q(url__icontains=keyword)
            | Q(user__profile__name__icontains=keyword)
            | Q(message__icontains=keyword)
        )

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
                    "myinco_admin/system_log/list_ajax.html", context
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


def open_systemlog_detail_modal(request):
    object_id = request.POST.get("ststem_log_id")
    user_id = request.POST.get("user_id")

    system_log = SystemLog.objects.get(id=object_id)
    user = User.objects.get(id=user_id)

    try:
        context = {
            "object": system_log,
            "user": user,
        }

        return JsonResponse(
            {
                "data": render_to_string(
                    "myinco_admin/system_log/list_modal.html", context
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
