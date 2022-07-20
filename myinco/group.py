from django import forms
from django.views.generic import ListView, CreateView

from django.http import JsonResponse, HttpResponseRedirect
from django.db.models import Q, Value
from django.urls import reverse_lazy
from django.template.loader import render_to_string

from isghome.models import User, AuthGroup, SystemLog
from isghome.views.myinco.util import make_system_log
from django.db.models import BooleanField

import json
import itertools
import operator
import copy


class AuthGroupCreateForm(forms.ModelForm):
    class Meta:
        model = AuthGroup
        fields = (
            "name",
            "description",
            "owner",
            "publish",
        )


class MyincoGroupListView(ListView, CreateView):
    template_name = "myinco_admin/group/list.html"
    model = AuthGroup
    form_class = AuthGroupCreateForm
    ordering = ("-ctime",)

    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return str(
            reverse_lazy("myinco_admin-group-list")
        )  # success_url may be lazy

    def get_queryset(self):
        queryset = super().get_queryset()
        keyword = self.request.GET.get("keyword")
        ordering = self.get_ordering()

        if keyword:
            queryset = queryset.filter(
                Q(name__icontains=keyword)
                | Q(members__profile__name=keyword)
                | Q(group_members__members__profile__name=keyword)
            ).distinct()

        if ordering:
            if isinstance(ordering, str):
                ordering = (ordering,)
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        users = User.objects.annotate(
            is_account=Value(True, output_field=BooleanField())
        )
        groups = AuthGroup.objects.annotate(
            is_account=Value(False, output_field=BooleanField())
        )

        search_list = []
        for user in users:
            search_list.append(user)
        for group in groups:
            search_list.append(group)

        context_data["form"] = AuthGroupCreateForm(
            initial={
                "name": "",
                "description": "",
                "owner": self.request.user,
                "publish": "publish",
            }
        )

        context_data["search_list"] = search_list

        return context_data

    def post(self, request, *args, **kwargs):
        self.object = None
        queryset = self.get_queryset()
        self.object_list = queryset

        if request.POST.get("form_type") == "delete":
            self.object = AuthGroup.objects.get(
                id=request.POST.get("object_id")
            )
            if request.user == self.object.owner:
                before_group = copy.deepcopy(self.object)
                default_log = SystemLog.objects.create(
                    page_name="그룹",
                    url=request.environ["PATH_INFO"],
                    user=request.user,
                    method="delete",
                    status_code="500",
                )
                try:
                    self.object.name = self.object.name + "(삭제예정)"
                    self.object.is_deleted = True
                    self.object.save()
                    extra_content = f"{request.user.profile.name}님에 의해 {before_group.name} 그룹 삭제"  # noqa
                    # self.object.delete()
                except Exception as e:
                    print(e)
                    context = self.get_context_data()
                    context["fail"] = "delete"
                    return self.render_to_response(context)

                make_system_log(
                    before_group,
                    "그룹",
                    request.environ["PATH_INFO"],
                    request.user,
                    "delete",
                    identifier=before_group.id,
                    default_log=default_log,
                    extra_content=extra_content,
                    extra_url=reverse_lazy("myinco_admin-group-list"),
                )

                context = self.get_context_data()
                context["success"] = "delete"
                return HttpResponseRedirect(
                    reverse_lazy("myinco_admin-group-list")
                )

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # before create object

        selected_members = self.request.POST.get("selected_member")
        selected_members = json.loads(selected_members)

        selected_members = sorted(selected_members, key=lambda x: x["type"])
        grouped_data = itertools.groupby(
            selected_members, key=operator.itemgetter("type")
        )

        users = []
        groups = []
        for key, data in grouped_data:
            data = list(data)
            if key == "member":
                users = User.objects.filter(id__in=[e["id"] for e in data])
            else:
                groups = AuthGroup.objects.filter(
                    id__in=[e["id"] for e in data]
                )
        if self.request.POST.get("form_type") == "create":
            default_log = SystemLog.objects.create(
                page_name="홈페이지 그룹",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="create",
                status_code="500",
            )

            self.object = form.save(commit=False)
            self.object = form.save()

            self.object.members.add(*users)
            self.object.group_members.add(*groups)

            extra_url = (
                reverse_lazy(
                    "myinco_admin-group-list",
                )
                + "?modal_id="
                + str(self.object.id)
            )
            make_system_log(
                self.object,
                "홈페이지 그룹",
                self.request.environ["PATH_INFO"],
                self.request.user,
                "create",
                identifier=self.object.id,
                default_log=default_log,
                extra_url=extra_url,
            )

            return super().form_valid(form)

        elif self.request.POST.get("form_type") == "update":
            default_log = SystemLog.objects.create(
                page_name="홈페이지 그룹",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )

            self.object = AuthGroup.objects.get(
                id=self.request.POST.get("object_id")
            )
            before_group = copy.deepcopy(self.object)

            if "name" in form.changed_data:
                self.object.name = self.request.POST.get("name")
            if "description" in form.changed_data:
                self.object.description = self.request.POST.get("description")
            self.object.save()

            object_users = set(self.object.members.all())
            object_groups = set(self.object.group_members.all())

            remove_users = object_users - set(users)
            add_users = set(users) - object_users
            remove_groups = object_groups - set(groups)
            add_groups = set(groups) - object_groups

            after_members = (
                set(self.object.members.all()) | add_users
            ) - remove_users

            after_groups = (
                set(self.object.group_members.all()) | add_groups
            ) - remove_groups

            after_members_qs = User.objects.filter(
                id__in=list(map(lambda x: x.id, after_members))
            )
            after_groups_qs = AuthGroup.objects.filter(
                id__in=list(map(lambda x: x.id, after_groups))
            )

            etc = [
                ["members", after_members_qs],
                ["group_members", after_groups_qs],
            ]
            extra_url = (
                reverse_lazy(
                    "myinco_admin-group-list",
                )
                + "?modal_id="
                + str(before_group.id)
            )
            system_log = make_system_log(
                before_group,
                "계정",
                self.request.environ["PATH_INFO"],
                self.request.user,
                "update",
                identifier=before_group.id,
                etc=etc,
                form=form,
                default_log=default_log,
                is_created=False,
                extra_url=extra_url,
            )

            self.object.members.remove(*list(remove_users))
            self.object.group_members.remove(*list(remove_groups))

            self.object.members.add(*list(add_users))
            for group in add_groups:
                if self.object not in group.get_child_group():
                    self.object.group_members.add(group)
                else:
                    print("추가할 수 없는 그룹이 있습니다.")

            if system_log:
                system_log.save_with_url(extra_url)

            return HttpResponseRedirect(self.get_success_url())

        # after create object

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context["errors"] = form.errors
        print(form.errors)
        return self.render_to_response(context)


def open_group_update_modal(request):
    object_id = request.POST.get("auth_group_id")
    user_id = request.POST.get("user_id")

    auth_group = AuthGroup.objects.get(id=object_id)
    user = User.objects.get(id=user_id)

    users = User.objects.annotate(
        is_account=Value(True, output_field=BooleanField())
    )
    groups = AuthGroup.objects.annotate(
        is_account=Value(False, output_field=BooleanField())
    )

    search_list = []
    for user in users:
        search_list.append(user)
    for group in groups:
        search_list.append(group)

    members = (
        auth_group.membership_set.all()
        .annotate(is_account=Value(True, output_field=BooleanField()))
        .order_by("-joined_at")
    )
    group_members = (
        auth_group.target_group.all()
        .annotate(is_account=Value(False, output_field=BooleanField()))
        .order_by("-joined_at")
    )

    joined_list = []
    for member in members:
        joined_list.append(member)
    for group_member in group_members:
        joined_list.append(group_member)

    try:
        context = {
            "object": auth_group,
            "search_list": search_list,
            "manager": auth_group.owner,
            "user": request.user,
            "joined_list": joined_list,
            "form": AuthGroupCreateForm(
                initial={
                    "name": auth_group.name,
                    "description": auth_group.description,
                    "owner": auth_group.owner,
                    "publish": auth_group.publish,
                }
            ),
        }

        return JsonResponse(
            {
                "data": render_to_string(
                    "myinco_admin/group/list_modal.html", context
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
