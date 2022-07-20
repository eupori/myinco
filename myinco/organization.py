from django import forms
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from django.http import JsonResponse, HttpResponseRedirect
from django.db.models import Case, When, Q
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from isghome.views.myinco.util import make_system_log

from isghome.models import (
    User,
    UserProfile,
    Customer,
    Organization,
    OrganizationBookmark,
    OrganizationLog,
    SalesActivity,
    SystemLog,
)

import copy


class OrganizationCreateForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = (
            "address",
            "address_detail",
            "post_number",
            "fax_number",
            "classification",
            "comment",
            "place_name",
            "phone",
            "place_url",
            "address_en",
            "address_detail_en",
            "alias",
        )


class MyincoOrganizationListView(ListView, CreateView):
    template_name = "myinco_admin/organization/list.html"
    model = Organization
    form_class = OrganizationCreateForm
    ordering = ("-ctime",)

    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return str(
            reverse_lazy("myinco_admin-organization-list")
        )  # success_url may be lazy

    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.user.id
        keyword = self.request.GET.get("keyword")
        ordering = self.get_ordering()

        if keyword:
            queryset = queryset.filter(Q(place_name__icontains=keyword))

        queryset = queryset.filter(is_deleted=False)

        # queryset = queryset.annotate(
        #     is_bookmarked=Case(
        #         When(
        #             organizationbookmark__in=OrganizationBookmark.objects.filter(
        #                 user__id=user_id
        #             ),
        #             then=True,
        #         ),
        #         default=False,
        #     )
        # ).distinct()
        queryset = queryset.annotate(
            is_bookmarked=Case(
                When(
                    organizationbookmark__user__id=user_id,
                    then=True,
                ),
                default=False,
            )
        )

        true_set = queryset.filter(is_bookmarked=True).distinct()
        ids = true_set.values_list("id", flat=True)
        false_set = (
            queryset.filter(is_bookmarked=False).distinct().exclude(id__in=ids)
        )
        queryset = true_set | false_set

        # .filter(Q(is_bookmarked_user=user_id) | Q(is_bookmarked_user=None))
        # .annotate(
        #     is_bookmarked=Case(
        #         When(
        #             is_bookmarked_user=user_id,
        #             then=True,
        #         ),
        #         default=False,
        #     )
        # )
        # queryset = queryset.annotate(bookmark_list=F("organizationbookmark"))
        # print("@#$@#$#@$#@$")
        # print(queryset)
        # for q in queryset:
        #     print(q.id)
        #     print(q.bookmark_list)

        if ordering:
            if isinstance(ordering, str):
                ordering = (ordering,)
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["total_object_list"] = context_data["object_list"]
        p = Paginator(context_data["object_list"], 10)
        context_data["object_list"] = p.page(1)
        context_data["bookmark_count"] = self.object_list.filter(
            is_bookmarked=True
        ).count()
        context_data[
            "total_objects_count"
        ] = Organization.objects.all().count()
        return context_data

    def post(self, request, *args, **kwargs):
        self.object = None
        queryset = self.get_queryset()
        self.object_list = queryset
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # before create object
        # after create object
        object_data = form.save(commit=False)
        default_log = SystemLog.objects.create(
            page_name="고객사",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="create",
            status_code="500",
        )

        object_data.save()
        object_data.manager.add(self.request.user)
        object_data.save()

        extra_url = reverse_lazy(
            "myinco_admin-organization-detail",
            kwargs={"id": object_data.id, "tab": 0},
        )

        make_system_log(
            object_data,
            "고객사",
            self.request.environ["PATH_INFO"],
            self.request.user,
            "create",
            identifier=object_data.id,
            default_log=default_log,
            extra_url=extra_url,
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context["errors"] = form.errors
        print(form.errors)
        return self.render_to_response(context)


def organization_page_ajax(request):
    user_id = request.POST.get("user_id")
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = Organization.objects.all()

    if keyword:
        queryset = queryset.filter(
            # Q(name__icontains=keyword)
            # | Q(organization__place_name__icontains=keyword)
            # | Q(place_name__icontains=keyword)
            Q(place_name__icontains=keyword)
            # | Q(email__icontains=keyword)
            # | Q(organization__address_name__icontains=keyword)  # noqa
        )

    queryset = queryset.filter(is_deleted=False)

    queryset = queryset.annotate(
        is_bookmarked=Case(
            When(
                organizationbookmark__user__id=user_id,
                then=True,
            ),
            default=False,
        )
    )

    true_set = queryset.filter(is_bookmarked=True).distinct()
    ids = true_set.values_list("id", flat=True)
    false_set = (
        queryset.filter(is_bookmarked=False).distinct().exclude(id__in=ids)
    )
    queryset = true_set | false_set

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
                    "myinco_admin/organization/list_ajax.html", context
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


def organization_bookmark_ajax(request):
    user = request.POST.get("user")
    organization_id = request.POST.get("organization")
    status = True if request.POST.get("status") == "true" else False

    bookmarks = OrganizationBookmark.objects.filter(
        organization=Organization.objects.get(id=organization_id),
        user=User.objects.get(id=user),
    )

    if status:
        if bookmarks:
            return JsonResponse({"data": "bookmark already added"}, status=200)
        else:
            OrganizationBookmark.objects.create(
                organization=Organization.objects.get(id=organization_id),
                user=User.objects.get(id=user),
            )
            try:
                OrganizationLog.objects.create(
                    organization=Organization.objects.get(id=organization_id),
                    diff="add bookmark",
                )
            except Exception as e:
                print(e)

            return JsonResponse({"data": "bookmark added"}, status=200)

    else:
        if not bookmarks:
            return JsonResponse(
                {"data": "bookmark already removed"}, status=200
            )
        else:
            OrganizationBookmark.objects.get(
                organization=Organization.objects.get(id=organization_id),
                user=User.objects.get(id=user),
            ).delete()

            try:
                OrganizationLog.objects.create(
                    organization=Organization.objects.get(id=organization_id),
                    diff="remove bookmark",
                )
            except Exception as e:
                print(e)

            return JsonResponse({"data": "bookmark removed"}, status=200)


class MyincoOrganizationDetailView(DetailView, UpdateView):
    template_name = "myinco_admin/organization/detail.html"
    model = Organization
    pk_url_kwarg = "id"
    form_class = OrganizationCreateForm

    def get_success_url(self):
        return str(
            reverse_lazy(
                "myinco_admin-organization-detail",
                kwargs={"id": self.kwargs["id"], "tab": self.kwargs["tab"]},
            )
        )  # success_url may be lazy

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        related_activities = SalesActivity.objects.filter(
            customer__organization=self.object
        )
        salesactivity_list = []
        for sa in related_activities:
            if sa.check_permission(self.request.user):
                salesactivity_list.append(sa)
        context["salesactivity_list"] = salesactivity_list
        context["historys"] = SystemLog.objects.filter(
            model="Organization", model_identifier=self.object.id
        ).order_by("-ctime")
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if request.POST.get("form_type") == "delete":
            before_organization = copy.deepcopy(self.object)
            default_log = SystemLog.objects.create(
                page_name="고객",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="delete",
                status_code="500",
            )
            try:
                users = UserProfile.objects.filter(organization=self.object)
                customers = Customer.objects.filter(organization=self.object)
                new_organization = Organization.objects.get(place_name="무소속")

                users.update(organization=new_organization)
                customers.update(organization=new_organization)

                self.object.is_deleted = True
                self.object.save()
            except Exception as e:
                print(e)
                context = self.get_context_data()
                context["fail"] = "delete"
                return self.render_to_response(context)

            extra_content = f"{request.user.profile.name}님에 의해 {before_organization.place_name} 고객사"  # noqa
            make_system_log(
                before_organization,
                "고객사",
                self.request.environ["PATH_INFO"],
                self.request.user,
                "delete",
                identifier=before_organization.id,
                default_log=default_log,
                extra_content=extra_content,
                extra_url=reverse_lazy("myinco_admin-organization-list"),
            )

            context = self.get_context_data()
            context["success"] = "delete"
            return HttpResponseRedirect(
                reverse_lazy("myinco_admin-organization-list")
            )

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        default_log = SystemLog.objects.create(
            page_name="계정",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="update",
            status_code="500",
        )
        before_organizaion = Organization.objects.get(pk=self.kwargs["id"])
        self.object = form.save()
        make_system_log(
            before_organizaion,
            "계정",
            self.request.environ["PATH_INFO"],
            self.request.user,
            "update",
            identifier=before_organizaion.id,
            form=form,
            default_log=default_log,
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context["errors"] = form.errors
        print(form.errors)
        return self.render_to_response(context)


def organization_active_ajax(request):
    status = False if request.POST.get("status") == "false" else True
    organization_id = request.POST.get("organization_id")
    user_id = request.POST.get("user_id")

    organization = Organization.objects.get(id=organization_id)
    before_target = copy.deepcopy(organization)
    user = User.objects.get(id=user_id)

    default_log = SystemLog.objects.create(
        page_name="고객사",
        url=request.environ["PATH_INFO"],
        user=request.user,
        method="update",
        status_code="500",
    )

    organization.is_active = status
    organization.save()

    OrganizationLog.objects.create(
        organization=organization,
        diff="status change to " + str(status),
        user=user,
    )

    etc = [["is_active", status]]
    if status:
        extra_content = f"{request.user.profile.name} 님에 의해 {organization.place_name} 고객사 활성화"  # noqa
    else:
        extra_content = f"{request.user.profile.name} 님에 의해 {organization.place_name} 고객사 비활성화"  # noqa

    make_system_log(
        before_target,
        "고객사",
        request.environ["PATH_INFO"],
        request.user,
        "update",
        identifier=before_target.id,
        etc=etc,
        extra_content=extra_content,
        default_log=default_log,
        extra_url=reverse_lazy(
            "myinco_admin-organization-detail",
            kwargs={"id": before_target.id, "tab": "0"},
        ),
    )

    return JsonResponse({"success": "success"}, status=200)


class OrganizationInfoView(DetailView):
    model = Organization
    template_name = ""

    def get(self, request, *args, **kwargs):
        organization = self.get_object()
        data = {
            "place_name": organization.get_str(),
            "address": organization.address,
            "address_detail": organization.address_detail,
            "post_number": organization.post_number,
        }
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
            }
        )
