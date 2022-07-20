# coding: utf-8

from django import forms
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.http import JsonResponse
from django.http import Http404
from django.urls import reverse_lazy
from django.db.models import Q
from django.db import transaction
from django.utils.safestring import mark_safe
from isghome.models import (
    User,
    Customer,
    Organization,
    SalesActivity,
    SystemLog,
    AuthGroup,
)
from isghome.utils import get_weekday_ko_name
from isghome.views import CustomModelChoiceField
from isghome.views.myinco.util import make_system_log

import json


class BaseSalesActivityListView(ListView):
    model = SalesActivity
    template_name = "myinco_admin/sales/list.html"

    def get_queryset(self):
        keyword = self.request.GET.get("keyword")
        manager = self.request.GET.get("manager")
        print("keyword:", keyword)
        print("manager:", manager)
        queryset = super().get_queryset()
        if keyword:
            queryset = queryset.filter(
                Q(activity_manager__profile__name__icontains=keyword)
                | Q(customer__name__icontains=keyword)
                | Q(customer__phone_number__icontains=keyword)
                | Q(customer__email__icontains=keyword)
                | Q(customer__organization__place_name__icontains=keyword)
            )
        if manager:
            queryset = queryset.filter(activity_manager__id=manager)
        return queryset

    def get_calender_data(self):
        calender_data = []
        for obj in self.object_list:
            title = obj.customer.rep_name
            manager = obj.activity_manager.profile.name
            classification = obj.get_activity_type_display()
            desc = obj.activity_content
            regdate = obj.ctime.strftime("%Y-%m-%d %H:%M:%S")
            activity_date = obj.activity_date.strftime("%Y-%m-%d")
            start = f"{activity_date} {obj.start_time.strftime('%H:%M:%S')}"
            end = f"{activity_date} {obj.end_time.strftime('%H:%M:%S')}"
            className = ["plan"] if obj.activity_status == "plan" else ""
            data = {
                "id": obj.id,
                "pk": obj.id,
                "title": title,
                "manager": manager,
                "classification": classification,
                "desc": desc,
                "regdate": regdate,
                "start": start,
                "end": end,
                "className": className,
            }
            calender_data.append(data)
        return calender_data

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        calender_data = self.get_calender_data()
        context["calender_data"] = json.dumps(calender_data)
        context["organizations"] = Organization.objects.filter(
            is_active=True
        ).order_by("place_name")
        managers = User.objects.filter(profile__auth_grade__gt=1)
        managers = managers.filter(
            profile__auth_grade__lte=self.request.user.profile.auth_grade
        )
        context["managers"] = managers
        context["query_type"] = self.query_type
        context["auth_groups"] = AuthGroup.objects.all()
        keyword = self.request.GET.get("keyword")
        manager = self.request.GET.get("manager")
        context["form_kwargs"] = {"keyword": keyword, "manager": manager}
        return context


class SalesActivityListView(BaseSalesActivityListView):
    query_type = "personal"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(activity_manager=self.request.user)
        return queryset


class SalesActivityTeamListView(BaseSalesActivityListView):
    query_type = "team"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(is_open=True)
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        new_object_list = []
        for obj in self.object_list:
            if obj.check_permission(self.request.user):
                new_object_list.append(obj)
        context["object_list"] = new_object_list
        self.object_list = new_object_list
        calender_data = self.get_calender_data()
        context["calender_data"] = json.dumps(calender_data)
        return context


class SalesActivitySearchListView(BaseSalesActivityListView):
    template_name = "myinco_admin/sales/search.html"
    query_type = ""

    def get_queryset(self):
        keyword = self.request.GET.get("keyword")
        query_type = self.request.GET.get("query_type")
        print("keyword:", keyword)
        print("query_type:", query_type)
        queryset = super().get_queryset()
        if keyword:
            queryset = queryset.filter(
                Q(activity_manager__profile__name__icontains=keyword)
                | Q(customer__name__icontains=keyword)
                | Q(customer__phone_number__icontains=keyword)
                | Q(customer__email__icontains=keyword)
                | Q(customer__organization__place_name__icontains=keyword)
                | Q(activity_content__icontains=keyword)
            )
        if query_type == "personal":
            queryset = queryset.filter(activity_manager=self.request.user)
        elif query_type == "team":
            queryset = queryset.filter(is_open=True)
        else:
            queryset = SalesActivity.objects.none()
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        keyword = self.request.GET.get("keyword")
        query_type = self.request.GET.get("query_type")
        context["query_type"] = query_type
        context["form_kwargs"] = {"keyword": keyword, "query_type": query_type}
        search_result = {}
        for obj in self.object_list.order_by("-activity_date", "start_time"):
            ctime = obj.activity_date.strftime("%Y년 %m월 %d일")
            weekday_name = get_weekday_ko_name(
                obj.activity_date.strftime("%A")
            )
            if ctime not in search_result:
                search_result[ctime] = {
                    "weekday_name": weekday_name,
                    "sales_list": [],
                }
            search_result[ctime]["sales_list"].append(
                {
                    "title": obj.customer.rep_name,
                    "manager": obj.activity_manager.profile.name,
                    "desc": obj.activity_content,
                    "classification": obj.get_activity_type_display(),
                    "className": "plan"
                    if obj.activity_status == "plan"
                    else "",
                    "start_time": f"{obj.start_time.strftime('%p %H:%M')}",
                    "end_time": f"{obj.end_time.strftime('%p %H:%M')}",
                }
            )
        context["search_result"] = search_result
        context["search_result_count"] = self.object_list.count()
        return context


class SalesActivityDetailView(DetailView):
    model = SalesActivity
    template_name = "myinco_admin/sales/detail.html"

    def dispatch(self, request, *args, **kwargs):
        is_active = self.has_permission()
        if not is_active:
            raise Http404("접근 권한이 없습니다.")
        if request.method.lower() in self.http_method_names:
            handler = getattr(
                self, request.method.lower(), self.http_method_not_allowed
            )
        else:
            handler = self.http_method_not_allowed
        return handler(request, *args, **kwargs)

    def has_permission(self):
        if not self.request.user.is_authenticated:
            print("ㅂㅣ 로그인 유저 접근")
            raise Http404("해당 페이지에 대해 접근 권한이 없습니다.")
        obj = self.get_object()
        user = self.request.user
        if user.is_superuser is True:
            return True
        if obj.permission_group:
            if (
                user in obj.permission_group.get_child_users()
                or user == obj.permission_group.owner
            ):
                return True
            else:
                print("obj.permission_group")
                raise Http404("해당 페이지에 대해 접근 권한이 없습니다.")
        if obj.activity_manager == user:
            return True
        elif obj.is_open is True and user.profile.auth_grade > 2:
            return True
        return False

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        related_activities = self.object.customer.salesactivity_set.exclude(
            id=self.object.id
        )
        context["related_activities"] = related_activities
        organization_list = Organization.objects.filter(
            is_active=True
        ).order_by("place_name")
        customer_list = self.object.customer.organization.customer_set.all()
        manager_list = User.objects.exclude(profile__auth_grade=1)
        context["organization_list"] = organization_list
        context["customer_list"] = customer_list
        context["manager_list"] = manager_list
        referer_url = self.request.META.get("HTTP_REFERER")
        if referer_url and "team" in referer_url:
            list_url = reverse_lazy("myinco_admin-sales-activity-team-list")
        else:
            list_url = reverse_lazy("myinco_admin-sales-activity-list")
        context["list_url"] = list_url
        context["start_time"] = self.object.start_time.strftime("%p %I:%M")
        context["end_time"] = self.object.end_time.strftime("%p %I:%M")
        context["auth_groups"] = AuthGroup.objects.all()
        context["historys"] = SystemLog.objects.filter(
            model="SalesActivity", model_identifier=context["object"].id
        ).order_by("-ctime")
        return context


class SalesActivityCreateForm(forms.ModelForm):
    start_time = forms.TimeField(input_formats=["%p %I:%M"])
    end_time = forms.TimeField(input_formats=["%p %I:%M"])
    post_number = forms.CharField()
    address = forms.CharField()
    address_detail = forms.CharField(required=False)
    phone_number = forms.CharField()
    email = forms.EmailField()
    organization = CustomModelChoiceField(
        queryset=Organization.objects.all(),
        required=False,
    )
    customer = CustomModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
    )
    new_organization = forms.CharField(required=False)
    new_customer = forms.CharField(required=False)
    new_organization_fields = [
        "address",
        "address_detail",
        "post_number",
    ]
    new_customer_fields = [
        "phone_number",
        "email",
    ]

    class Meta:
        model = SalesActivity
        fields = [
            # "customer",
            "activity_date",
            "start_time",
            "end_time",
            "activity_type",
            "activity_status",
            "activity_content",
            "activity_manager",
            "is_open",
            "permission_group",
        ]

    def clean(self):
        print(">>>>>>> clean...")
        cleaned_data = super().clean()
        organization = cleaned_data.get("organization")
        if not organization:
            new_organization = cleaned_data.get("new_organization")
            if new_organization:
                for field_name in self.new_organization_fields:
                    if not cleaned_data.get(field_name):
                        raise forms.ValidationError(
                            f"고객사 추가 에러: {field_name} 값이 없습니다."
                        )
            else:
                raise forms.ValidationError("고객사 선택이 잘못되었습니다.")
        customer = cleaned_data.get("customer")
        if not customer:
            new_customer = cleaned_data.get("new_customer")
            if new_customer:
                for field_name in self.new_customer_fields:
                    if not cleaned_data.get(field_name):
                        raise forms.ValidationError(
                            f"고객 추가 에러: {field_name} 값이 없습니다."
                        )
            else:
                raise forms.ValidationError("고객 선택이 잘못되었습니다.")
        return cleaned_data


class SalesActivityCreateView(CreateView):
    model = SalesActivity
    template_name = ""
    form_class = SalesActivityCreateForm

    @transaction.atomic
    def form_valid(self, form):
        default_log = SystemLog.objects.create(
            page_name="영업활동",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="create",
            status_code="500",
        )
        data = form.cleaned_data
        organization = data.get("organization")
        customer = data.get("customer")
        if data.get("new_organization"):
            # create new organization
            place_name = data.get("new_organization")
            address = data.get("address")
            address_detail = data.get("address_detail")
            post_number = data.get("post_number")
            try:
                organization = Organization.objects.get(
                    place_name=place_name,
                    address=address,
                    post_number=post_number,
                )
            except Organization.DoesNotExist:
                exist_organization = Organization.objects.filter(
                    place_name=data.get("organization")
                )
                alias = str(exist_organization.count() + 1) + "번"
                organization = Organization.objects.create(
                    place_name=place_name,
                    address=address,
                    address_detail=address_detail,
                    post_number=post_number,
                    alias=alias,
                )
        if data.get("new_customer"):
            # create new customer
            customer = Customer.objects.create(
                name=data.get("new_customer"),
                organization=organization,
                phone_number=data.get("phone_number"),
                email=data.get("email"),
            )
        self.object = form.save(commit=False)
        self.object.customer = customer
        self.object.save()

        extra_url = self.object.get_absolute_url()

        make_system_log(
            self.object,
            "영업활동",
            self.request.environ["PATH_INFO"],
            self.request.user,
            "create",
            identifier=self.object.id,
            default_log=default_log,
            extra_url=extra_url,
        )
        return JsonResponse(
            {
                "is_success": True,
                "detail_url": self.object.get_absolute_url(),
            }
        )

    def form_invalid(self, form):
        errors = []
        for error_key in form.errors:
            for error in form.errors[error_key]:
                errors.append(f'"{error_key}: {error}"')
        err_messages = "<br>".join(errors)
        print("errors:", errors)
        return JsonResponse(
            {
                "is_success": False,
                "err_messages": mark_safe(err_messages),
            }
        )


class SalesActivityUpdateForm(forms.ModelForm):
    start_time = forms.TimeField(input_formats=["%p %I:%M"])
    end_time = forms.TimeField(input_formats=["%p %I:%M"])
    # post_number = forms.CharField()
    # address = forms.CharField()
    # address_detail = forms.CharField(required=False)

    class Meta:
        model = SalesActivity
        fields = [
            "activity_date",
            "start_time",
            "end_time",
            "activity_type",
            "activity_status",
            "activity_content",
            "activity_manager",
            # "activity_companions",
            "is_open",
            "permission_group",
        ]


class SalesActivityUpdateView(UpdateView):
    model = SalesActivity
    template_name = ""
    form_class = SalesActivityUpdateForm

    @transaction.atomic
    def form_valid(self, form):
        default_log = SystemLog.objects.create(
            page_name="영업활동",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="update",
            status_code="500",
        )
        before_object = self.get_object()

        self.object = form.save()

        make_system_log(
            before_object,
            "영업활동",
            self.request.environ["PATH_INFO"],
            self.request.user,
            "update",
            identifier=self.object.id,
            form=form,
            default_log=default_log,
        )

        return JsonResponse(
            {
                "is_success": True,
                "detail_url": self.object.get_absolute_url(),
            }
        )

    def form_invalid(self, form):
        return JsonResponse(
            {
                "is_success": False,
                "error": str(form.errors),
            }
        )


class SalesActivityDeleteView(DeleteView):
    model = SalesActivity
    template_name = "myinco_admin/sales/delete.html"

    def post(self, request, *args, **kwargs):
        password = request.POST.get("password")
        is_delete = request.POST.get("delete")
        data = {}
        is_success = False
        referer_url = self.request.META.get("HTTP_REFERER")
        if referer_url and "team" in referer_url:
            list_url = reverse_lazy("myinco_admin-sales-activity-team-list")
        else:
            list_url = reverse_lazy("myinco_admin-sales-activity-list")
        data["list_url"] = list_url
        if is_delete == "Yes":
            if request.user.check_password(password):
                self.object = self.get_object()
                self.object.delete()
                is_success = True
            else:
                data["error"] = "Password Not Match..."
        else:
            data["error"] = "Invalid request."
        data["is_success"] = is_success
        return JsonResponse(data)


class SalesActivityInfoView(DetailView):
    model = SalesActivity
    template_name = ""

    def get(self, request, *args, **kwargs):
        activity = self.get_object()
        c_date = activity.ctime.strftime("%Y년 %m월 %d일·생성됨")
        # regdate = activity.ctime.strftime("%Y-%m-%d %H:%M:%S")
        activity_date = activity.activity_date.strftime("%Y-%m-%d")
        start = activity.start_time.strftime("%p %I:%M")
        end = activity.end_time.strftime("%p %I:%M")
        org_queryset = Organization.objects.filter(is_active=True).order_by(
            "place_name"
        )
        organization_list = [
            {"id": org.id, "value": org.place_name} for org in org_queryset
        ]  # noqa
        customer_list = [
            {"id": cus.id, "value": cus.name}
            for cus in activity.customer.organization.customer_set.all()
        ]  # noqa
        # managers = User.objects.filter(profile__auth_grade__gt=1)
        managers = User.objects.exclude(profile__auth_grade=1)
        print("ag:", self.request.user.profile.auth_grade)
        print(11, managers)
        # managers = managers.filter(
        #     profile__auth_grade__lte=self.request.user.profile.auth_grade
        # )
        print(22, managers)
        manager_list = [
            {"id": user.id, "value": user.profile.name} for user in managers
        ]  # noqa
        permission_group = ""
        if activity.permission_group:
            permission_group = activity.permission_group.id
        data = {
            "id": activity.id,
            "regdate": activity_date,
            "start": start,
            "end": end,
            "c_date": c_date,
            "organization_list": organization_list,
            "customer_list": customer_list,
            "manager_list": manager_list,
            "organization": activity.customer.organization.id,
            "customer": activity.customer.id,
            "address": activity.customer.organization.address,
            "address_detail": activity.customer.organization.address_detail,
            "phone_number": activity.customer.phone_number.as_national,
            "email": activity.customer.email,
            "activity_content": activity.activity_content,
            "activity_type": activity.activity_type,
            "activity_status": activity.activity_status,
            "activity_manager": activity.activity_manager.id,
            "permission_group": permission_group,
            "is_open": activity.is_open,
        }
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
            }
        )
