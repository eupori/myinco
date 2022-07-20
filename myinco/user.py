from django import forms
from django.views.generic import ListView, DetailView, CreateView
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Case, When, Q
from django.template.loader import render_to_string
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from isghome.views import send_auto_email

from isghome.views.myinco.util import make_system_log
from isghome.models import (
    ServicePolicyPriceOption,
    User,
    UserProfile,
    Customer,
    UserBookmark,
    UserLog,
    Order,
    Organization,
    ResearchField,
    UserService,
    ServiceAttachment,
    SystemLog,
)

import datetime
import copy


# class CustomerCreateForm(forms.ModelForm):
#     class Meta:
#         model = Customer
#         exclude = ["grade", "synced_user", "is_synced"]


class UserProfileCreateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        exclude = ["user"]


class UserServiceUpdateForm(forms.ModelForm):
    attachment1 = forms.FileField(required=False)
    attachment2 = forms.FileField(required=False)
    attachment3 = forms.FileField(required=False)

    class Meta:
        model = UserService
        exclude = ["is_expired", "is_deleted"]

    def __init__(self, *args, **kwargs):
        super(UserServiceUpdateForm, self).__init__(*args, **kwargs)
        self.fields["license_date_from"] = forms.DateField(
            initial=self.instance.license_date_from,
            input_formats="%Y년 %m월 %d일 ",
            widget=forms.DateInput(format="%Y년 %m월 %d일"),
        )
        self.fields["license_date_to"] = forms.DateField(
            initial=self.instance.license_date_to,
            input_formats="%Y년 %m월 %d일 ",
            widget=forms.DateInput(format="%Y년 %m월 %d일"),
        )

        for ind, attachment in enumerate(
            self.instance.serviceattachment_set.all()
        ):
            self.fields[f"attachment{ind+1}"] = forms.FileField(
                initial=attachment.attachment
            )


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = (
            "auth_grade",
            "point_color",
            "organization",
            "research_field",
            "comment",
        )


class UserProfileUpdateForm(forms.ModelForm):
    address = forms.CharField(max_length=200, required=False)
    address_detail = forms.CharField(max_length=200, required=False)
    job_position = forms.CharField(max_length=50, required=False)
    phone_number = forms.CharField(max_length=50, required=False)

    class Meta:
        model = User
        fields = ("username", "password")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super(UserProfileUpdateForm, self).__init__(*args, **kwargs)
        name = UserProfileForm.__name__.lower()
        setattr(self, name, UserProfileForm(*args, **kwargs))
        form = getattr(self, name)
        self.fields.update(form.fields)
        self.initial.update(form.initial)
        # self.fields['password2'].help_text = _('')
        ordering = ["place_name"]
        self.fields["organization"] = forms.ModelChoiceField(
            initial=self.instance.organization if self.instance.id else None,
            queryset=Organization.objects.exclude(is_deleted=True).order_by(
                *ordering
            ),
        )
        self.fields["auth_grade"].choices = self.filter_auth_grade(
            self.user.profile.auth_grade,
        )

    def filter_auth_grade(self, grade):
        choices = []
        for each in UserProfile.USER_AUTH_GRADE_CHOICES:
            if each[0] > grade:
                pass
            else:
                choices.append(each)

        return choices


class OrderSearchForm(forms.Form):
    keyword = forms.CharField(max_length=50)


class SignupForm(forms.ModelForm):
    address = forms.CharField(max_length=200, required=False)
    address_detail = forms.CharField(max_length=200, required=False)
    job_position = forms.CharField(max_length=50, required=False)
    phone_number = forms.CharField(max_length=50, required=False)

    class Meta:
        model = User
        fields = ("username", "password")

    def __init__(self, *args, **kwargs):
        super(SignupForm, self).__init__(*args, **kwargs)
        name = UserProfileForm.__name__.lower()
        setattr(self, name, UserProfileForm(*args, **kwargs))
        form = getattr(self, name)
        self.fields.update(form.fields)
        self.initial.update(form.initial)
        # self.fields['password2'].help_text = _('')
        ordering = ["place_name"]
        self.fields["organization"] = forms.ModelChoiceField(
            # initial=self.instance.organization if self.instance.id else None,
            queryset=Organization.objects.exclude(is_deleted=True).order_by(
                *ordering
            ),
        )

    def is_valid(self):
        isValid = True
        name = UserProfileForm.__name__.lower()
        form = getattr(self, name)
        if not form.is_valid():
            isValid = False
        # is_valid will trigger clean method
        # so it should be called after all other forms is_valid are called
        # otherwise clean_data will be empty
        if not super(SignupForm, self).is_valid():
            isValid = False
        name = UserProfileForm.__name__.lower()
        form = getattr(self, name)
        self.errors.update(form.errors)
        return isValid

    def clean(self):
        cleaned_data = super(SignupForm, self).clean()
        name = UserProfileForm.__name__.lower()
        form = getattr(self, name)
        cleaned_data.update(form.cleaned_data)
        return cleaned_data


# contrib.User 를 모델에 넣으니 오류가 발생하여 UserProfile을 넣고 하위 user를 접근
class MyincoAdminUserListView(ListView, CreateView):
    template_name = "myinco_admin/user/list.html"
    model = UserProfile
    ordering = ("-ctime",)
    form_class = SignupForm

    def get_success_url(self):
        return str(
            reverse_lazy("myinco_admin-user-list")
        )  # success_url may be lazy

    def get(self, request, *args, **kwargs):
        self.object = None
        if request.user.profile:
            if int(request.user.profile.auth_grade) != 1:
                return super().get(request, *args, **kwargs)
        return HttpResponseRedirect(reverse_lazy("index"))

    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.user.id
        keyword = self.request.GET.get("keyword")
        ordering = self.get_ordering()

        if keyword:
            queryset = queryset.filter(
                Q(name__icontains=keyword)
                | Q(organization__place_name__icontains=keyword)
                | Q(phone_number__icontains=keyword)
                | Q(user__username__icontains=keyword)
                | Q(user__email__icontains=keyword)
                | Q(agree_receive_email__icontains=keyword)
                | Q(user__user_service__license_info__icontains=keyword)
            )

        queryset = queryset.filter(is_deleted=False)

        # queryset = queryset.annotate(
        #     is_bookmarked=Case(
        #         When(
        #             user__userbookmark__user__id=user_id,
        #             then=True,
        #         ),
        #         default=False,
        #     )
        # ).distinct()

        queryset = queryset.annotate(
            is_bookmarked=Case(
                When(
                    user__bookmark_target_user__user__id=user_id,
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

        if ordering:
            if isinstance(ordering, str):
                ordering = (ordering,)
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["bookmark_count"] = self.object_list.filter(
            is_bookmarked=True
        ).count()
        objects = context_data["object_list"]
        context_data["total_objects_count"] = objects.count()
        p = Paginator(objects, 10)

        customers = Customer.objects.filter(is_deleted=False)

        context_data["customers"] = customers
        context_data["total_object_list"] = context_data["object_list"]

        context_data["object_list"] = p.page(1)
        context_data["page"] = 1
        return context_data

    def post(self, request, *args, **kwargs):
        self.object = None
        queryset = self.get_queryset()
        self.object_list = queryset
        # 고객, 고객사 신규 추가
        # self에 넣어주기

        if request.POST.get("id_new_organization"):
            default_log = SystemLog.objects.create(
                page_name="고객사",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="create",
                status_code="500",
            )

            self.organization = Organization.objects.create(
                place_name=request.POST.get("id_new_organization"),
                address=request.POST.get("address"),
                address_detail=request.POST.get("address_detail"),
                post_number=request.POST.get("post_code"),
            )

            if self.organization:
                mutable = request.POST._mutable
                request.POST._mutable = True
                request.POST["organization"] = str(self.organization.id)
                request.POST._mutable = mutable
                self.organization.manager.add(request.user)
                self.organization.save()

                extra_url = reverse_lazy(
                    "myinco_admin-organization-detail",
                    kwargs={"id": self.organization.id, "tab": 0},
                )

                make_system_log(
                    self.organization,
                    "고객사",
                    request.environ["PATH_INFO"],
                    request.user,
                    "create",
                    identifier=self.organization.id,
                    default_log=default_log,
                    extra_url=extra_url,
                )
        else:
            self.organization = Organization.objects.get(
                id=request.POST.get("organization")
            )

        if request.POST.get("id_new_customer"):
            self.customer = None
            # default_log = SystemLog.objects.create(
            #     page_name="고객",
            #     url=self.request.environ["PATH_INFO"],
            #     user=self.request.user,
            #     method="create",
            #     status_code="500",
            # )

            # self.customer = Customer.objects.create(
            #     name=request.POST.get("id_new_customer"),
            #     job_position=request.POST.get("job_position"),
            #     phone_number=request.POST.get("phone_number"),
            #     email=request.POST.get("username"),
            #     organization=self.organization,
            # )

            # if self.customer:
            #     mutable = request.POST._mutable
            #     request.POST._mutable = True
            #     request.POST["customer"] = str(self.customer.id)
            #     request.POST._mutable = mutable
            #     self.customer.manager.add(request.user)
            #     self.customer.save()

            #     extra_url = reverse_lazy(
            #         "myinco_admin-customer-detail",
            #         kwargs={"id": self.customer.id, "tab": 0},
            #     )

            #     make_system_log(
            #         self.customer,
            #         "고객",
            #         request.environ["PATH_INFO"],
            #         request.user,
            #         "create",
            #         identifier=self.customer.id,
            #         default_log=default_log,
            #         extra_url=extra_url,
            #     )
        else:
            self.customer = Customer.objects.get(
                id=request.POST.get("customer")
            )

        research_fields = []
        for research_field in request.POST.getlist("research_field"):
            research_fields.append(
                ResearchField.objects.get(id=research_field)
            )
            # self.customer.research_field.add(
            #     ResearchField.objects.get(id=research_field)
            # )
            # self.customer.save()

        self.research_fields = research_fields

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # before create object
        self.object = form.save(commit=False)

        default_log = SystemLog.objects.create(
            page_name="계정",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="create",
            status_code="500",
        )

        # 회원가입 나머지 처리
        self.object = form.save()
        self.object.set_password(form.cleaned_data["password"])
        self.object.email = self.request.POST.get("username")
        # self.customer.synced_user = self.object
        self.object.save()

        user_profile = UserProfile.objects.get(user=self.object)
        if self.customer:
            user_profile.name = self.customer.name
            user_profile.phone_number = self.customer.phone_number
            user_profile.job_position = self.customer.job_position
        else:
            user_profile.name = self.request.POST.get("id_new_customer")
            user_profile.phone_number = self.request.POST.get("phone_number")
            user_profile.job_position = self.request.POST.get("job_position")
        user_profile.auth_grade = form.cleaned_data["auth_grade"]
        user_profile.organization = self.organization
        user_profile.address = self.organization.address
        user_profile.address_detail = self.organization.address_detail
        user_profile.manager = self.request.user

        for research_field in self.research_fields:
            user_profile.research_field.add(research_field)

        user_profile.save()

        # self.customer.organization = self.organization

        extra_url = reverse_lazy(
            "myinco_admin-user-detail",
            kwargs={"id": self.object.id, "tab": 0},
        )

        make_system_log(
            self.object,
            "계정",
            self.request.environ["PATH_INFO"],
            self.request.user,
            "create",
            identifier=self.object.id,
            default_log=default_log,
            extra_url=extra_url,
        )

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context["errors"] = form.errors
        print(form.errors)
        return self.render_to_response(context)


def user_page_ajax(request):
    user_id = request.POST.get("user_id")
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = UserProfile.objects.all()

    if keyword:
        queryset = queryset.filter(
            Q(name__icontains=keyword)
            | Q(organization__place_name__icontains=keyword)
            | Q(phone_number__icontains=keyword)
            | Q(user__username__icontains=keyword)
            | Q(user__email__icontains=keyword)
            | Q(agree_receive_email__icontains=keyword)
            | Q(user__user_service__license_info__icontains=keyword)
        )

    queryset = queryset.filter(is_deleted=False)

    queryset = queryset.annotate(
        is_bookmarked=Case(
            When(
                user__userbookmark__user__id=user_id,
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
                    "myinco_admin/user/list_ajax.html", context
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


def user_bookmark_ajax(request):
    user = request.POST.get("user")
    user_profile_id = request.POST.get("target_user")
    status = True if request.POST.get("status") == "true" else False

    target_user = UserProfile.objects.get(id=user_profile_id).user

    bookmarks = UserBookmark.objects.filter(target_user=target_user)
    if status:
        if bookmarks:
            return JsonResponse({"data": "bookmark already added"}, status=200)
        else:
            UserBookmark.objects.create(
                target_user=target_user,
                user=User.objects.get(id=user),
            )
            try:
                UserLog.objects.create(
                    diff="add bookmark",
                    target_user=target_user,
                    user=User.objects.get(id=user),
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
            UserBookmark.objects.get(
                target_user=target_user,
            ).delete()

            try:
                UserLog.objects.create(
                    target_user=target_user,
                    diff="remove bookmark",
                )
            except Exception as e:
                print(e)

            return JsonResponse({"data": "bookmark removed"}, status=200)


class MyincoAdminUserDetailView(DetailView):
    template_name = "myinco_admin/user/detail.html"
    model = UserProfile
    pk_url_kwarg = "id"
    slug_url_kwarg = "tab"

    def get_success_url(self):
        return str(
            reverse_lazy(
                "myinco_admin-user-detail",
                kwargs={"id": self.kwargs["id"], "tab": self.kwargs["tab"]},
            )
        )  # success_url may be lazy

    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        user_profile = data["object"]
        # data["orders"] = Order.objects.filter(
        #     purchaser_user=user.synced_user
        # )

        recommend_customers = Customer.objects.filter(
            Q(name=user_profile.name)
            & Q(is_deleted=False)
            & (
                Q(phone_number=user_profile.phone_number)
                | Q(email=user_profile.user.email)
            )
        ).order_by("-ctime")

        # recommend_customers = []
        # for each in customers:
        #     if each.name == user_profile.name:
        #         if each.phone_number == user_profile.phone_number:
        #             recommend_customers.append(each)
        #         elif each.email == user_profile.user.email:
        #             recommend_customers.append(each)
        data["recommends"] = recommend_customers

        # customers = Customer.objects.filter(~Q(name=None))
        customers = Customer.objects.filter(is_deleted=False).order_by(
            "-ctime"
        )

        p = Paginator(customers, 10)
        data["search_customer_list"] = p.page(1)
        data["page"] = 1

        # 서비스
        policys = ServicePolicyPriceOption.objects.filter(
            policy__is_active=True
        )
        # policy_dict = {}
        # for policy in policys:
        #     if policy.product_name in policy_dict.keys():
        #         policy_dict[policy.product_name].append(policy)
        #     else:
        #         policy_dict[policy.product_name] = [policy]
        # data["policys"] = policy_dict
        data["policys"] = policys

        data["my_cart"] = user_profile.user.mycart_set.filter(is_ordered=False)

        if user_profile.is_synced:
            synced_customer = user_profile.user.synced_user.first()
            if synced_customer:
                data["orders"] = Order.objects.filter(
                    Q(purchaser_user=user_profile.user)
                    | Q(purchaser_customer=synced_customer)
                ).distinct()
            else:
                data["orders"] = Order.objects.filter(
                    purchaser_user=user_profile.user
                )
        else:
            data["orders"] = Order.objects.filter(
                purchaser_user=user_profile.user
            )
        data["form"] = UserProfileUpdateForm(
            instance=user_profile, user=self.request.user
        )

        data["historys"] = SystemLog.objects.filter(
            model="UserProfile", model_identifier=user_profile.id
        ).order_by("-ctime")

        data["user_services"] = UserService.objects.filter(
            target_user=user_profile.user, is_deleted=False
        )

        return data

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.POST.get("form_type") == "create":
            default_log = SystemLog.objects.create(
                page_name="계정 - 서비스",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="create",
                status_code="500",
            )

            attachments = [
                request.FILES.get("attachment1"),
                request.FILES.get("attachment2"),
                request.FILES.get("attachment3"),
            ]
            # return super().post(request, *args, **kwargs)

            license_date_from_str = request.POST.get("license_date_from")
            license_date_to_str = request.POST.get("license_date_to")

            license_date_from = datetime.datetime.strptime(
                license_date_from_str, "%Y년 %m월 %d일"
            )
            license_date_to = datetime.datetime.strptime(
                license_date_to_str, "%Y년 %m월 %d일"
            )

            service_policy_price_option = ServicePolicyPriceOption.objects.get(
                id=request.POST.get("policy_id")
            )

            user_service = UserService.objects.create(
                service_policy_price_option=service_policy_price_option,
                license_info=request.POST.get("license_info"),
                target_user=self.object.user,
                license_date_from=license_date_from,
                license_date_to=license_date_to,
                download_center_url=request.POST.get("download_center_url"),
                password_setting_url=request.POST.get("password_setting_url"),
                login_guide_url=request.POST.get("login_guide_url"),
                faq_url=request.POST.get("faq_url"),
                request_reinstall_url=request.POST.get(
                    "request_reinstall_url"
                ),
            )

            for attachment in attachments:
                if attachment:
                    ServiceAttachment.objects.create(
                        user_service=user_service, attachment=attachment
                    )

            user_service.manager.add(request.user)

            make_system_log(
                user_service,
                "계정 - 서비스",
                request.environ["PATH_INFO"],
                request.user,
                "create",
                identifier=user_service.id,
                default_log=default_log,
            )

            content = "서비스 라이선스가 발급되었어요."
            name = user_service.target_user.profile.name

            send_auto_email(
                client_info=user_service,
                email_subject=f"[(주)인실리코젠] {name}님, 서비스 라이선스 발급 안내 드립니다.",
                email_template="myinco_admin/user/user_service_email.html",
                to_email=user_service.target_user.username,
                sub_title=content,
            )

            context = self.get_context_data()
            context["success"] = "connect"

            return HttpResponseRedirect(self.get_success_url())
        elif request.POST.get("form_type") == "connect":
            user_profile = self.object
            before_profile = copy.deepcopy(user_profile)
            customer = Customer.objects.get(
                id=request.POST.get("recommend_customer_id")
            )
            default_log = SystemLog.objects.create(
                page_name="계정",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )
            if request.POST.get("is_connected") == "true":
                customer.synced_user = None
                customer.is_synced = False
                user_profile.is_synced = False
                customer.save()
                user_profile.save()

                etc = [["is_synced", False]]
                extra_content = f"{request.user.profile.name}님에 의해 {user_profile.name}({user_profile.user.username}) 계정, 고객({customer.name}, {customer.email})연동취소"  # noqa
                make_system_log(
                    before_profile,
                    "계정",
                    request.environ["PATH_INFO"],
                    request.user,
                    "update",
                    identifier=before_profile.id,
                    etc=etc,
                    extra_content=extra_content,
                    default_log=default_log,
                )
            else:
                print("연동")
                if customer.synced_user:
                    customer.synced_user.profile.is_synced = False
                    customer.synced_user.profile.save()
                customer.synced_user = user_profile.user
                customer.is_synced = True
                user_profile.is_synced = True
                customer.save()
                user_profile.save()

                etc = [["is_synced", True]]
                if request.POST.get("method") == "recommend":
                    extra_content = f"{request.user.profile.name}님에 의해 {user_profile.name}({user_profile.user.username}) 계정, 추천 데이터({customer.name}, {customer.email})연동"  # noqa
                elif request.POST.get("method") == "search":
                    extra_content = f"{request.user.profile.name}님에 의해 {user_profile.name}({user_profile.user.username}) 계정, 검색 데이터({customer.name}, {customer.email})연동"  # noqa
                make_system_log(
                    before_profile,
                    "계정",
                    request.environ["PATH_INFO"],
                    request.user,
                    "update",
                    identifier=before_profile.id,
                    etc=etc,
                    extra_content=extra_content,
                    default_log=default_log,
                )

            context = self.get_context_data()
            context["success"] = "connect"
            return self.render_to_response(context)
        elif request.POST.get("form_type") == "update":
            default_log = SystemLog.objects.create(
                page_name="계정",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )

            user_profile = UserProfile.objects.get(id=kwargs["id"])
            before_profile = copy.deepcopy(user_profile)
            print("수정")
            password = request.POST.get("password")
            reset_password = request.POST.get("reset_password")

            if reset_password != "nochanged" or password:
                target_user = user_profile.user
                before_user = copy.deepcopy(target_user)
                if password:
                    etc = [["password", password]]
                else:
                    etc = [["password", reset_password]]
                make_system_log(
                    before_user,
                    "계정",
                    request.environ["PATH_INFO"],
                    request.user,
                    "update",
                    identifier=before_user.id,
                    etc=etc,
                    default_log=default_log,
                )

                if password and password != target_user.password:
                    target_user.set_password(password)
                elif reset_password != "nochanged":
                    target_user.set_password(
                        request.POST.get("reset_password")
                    )
                target_user.save()

            etc = []
            auth_grade = request.POST.get("auth_grade")
            research_field = request.POST.getlist("research_field")
            comment = request.POST.get("comment")
            job_position = request.POST.get("job_position")
            point_color = request.POST.get("point_color")
            phone_number = request.POST.get("phone_number")

            if auth_grade:
                etc.append(["auth_grade", auth_grade])
            if research_field:
                etc.append(["research_field", research_field])
            if job_position:
                etc.append(["job_position", job_position])
            if point_color:
                etc.append(["point_color", point_color])
            if phone_number:
                etc.append(["phone_number", phone_number])

            system_log = make_system_log(
                before_profile,
                "계정",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=before_profile.id,
                etc=etc,
                is_created=False,
                default_log=default_log,
            )

            user_profile.research_field.clear()
            for each in research_field:
                user_profile.research_field.add(
                    ResearchField.objects.get(id=each)
                )
            if auth_grade:
                user_profile.auth_grade = auth_grade

            if job_position:
                user_profile.job_position = job_position
            if point_color:
                user_profile.point_color = point_color
            if phone_number:
                user_profile.phone_number = phone_number
            if comment:
                user_profile.comment = comment

            try:
                user_profile.save()

                context = self.get_context_data()
                context["success"] = "connect"
            except Exception as e:
                print(e)
                context = self.get_context_data()
                context["success"] = "fail"
                return self.render_to_response(context)

            if system_log:
                system_log.save_with_url()
            return HttpResponseRedirect(self.get_success_url())

        elif request.POST.get("form_type") == "delete":
            before_profile = copy.deepcopy(self.object)
            default_log = SystemLog.objects.create(
                page_name="계정",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="delete",
                status_code="500",
            )
            try:
                if self.object.user.synced_user.all().count() > 0:
                    for sync_customer in self.object.user.synced_user.all():
                        sync_customer.is_synced = False

                self.object.is_deleted = True
                self.object.user.is_active = False
                self.object.user.save()
                self.object.is_synced = False
                user_services = UserService.objects.filter(
                    target_user=self.object.user
                )
                user_services.update(is_deleted=True)

                self.object.save()
            except Exception as e:
                print(e)
                context = self.get_context_data()
                context["fail"] = "delete"
                return self.render_to_response(context)

            extra_content = f"{request.user.profile.name}님에 의해 {before_profile.name}({before_profile.user.username}) 계정 삭제"  # noqa
            make_system_log(
                before_profile,
                "계정",
                self.request.environ["PATH_INFO"],
                self.request.user,
                "delete",
                identifier=before_profile.id,
                default_log=default_log,
                extra_content=extra_content,
                extra_url=reverse_lazy("myinco_admin-user-list"),
            )

            context = self.get_context_data()
            context["success"] = "delete"
            return HttpResponseRedirect(reverse_lazy("myinco_admin-user-list"))

        elif request.POST.get("form_type") == "service_update":
            default_log = SystemLog.objects.create(
                page_name="계정 - 서비스",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )
            user_service = UserService.objects.get(
                id=request.POST.get("service_id")
            )
            before_user_service = copy.deepcopy(user_service)

            deleted_attachment_ids = request.POST.get(
                "deleted_attachment"
            ).split(", ")
            deleted_attachment_ids = list(filter(None, deleted_attachment_ids))

            # 기타 첨부파일 삭제
            if deleted_attachment_ids:
                ServiceAttachment.objects.filter(
                    id__in=deleted_attachment_ids
                ).delete()

            attachments = [
                request.FILES.get("attachment1"),
                request.FILES.get("attachment2"),
                request.FILES.get("attachment3"),
            ]

            license_date_from_str = request.POST.get("license_date_from")
            license_date_to_str = request.POST.get("license_date_to")

            license_date_from = datetime.datetime.strptime(
                license_date_from_str, "%Y년 %m월 %d일"
            )
            license_date_to = datetime.datetime.strptime(
                license_date_to_str, "%Y년 %m월 %d일"
            )

            service_policy_price_option = ServicePolicyPriceOption.objects.get(
                id=request.POST.get("policy_id")
            )

            download_center_url = request.POST.get("download_center_url")
            password_setting_url = request.POST.get("password_setting_url")
            login_guide_url = request.POST.get("login_guide_url")
            faq_url = request.POST.get("faq_url")
            request_reinstall_url = request.POST.get("request_reinstall_url")

            user_service.download_center_url = download_center_url
            user_service.password_setting_url = password_setting_url
            user_service.login_guide_url = login_guide_url
            user_service.faq_url = faq_url
            user_service.request_reinstall_url = request_reinstall_url
            user_service.license_date_from = license_date_from.date()
            user_service.license_date_to = license_date_to.date()
            user_service.service_policy_price_option = (
                service_policy_price_option
            )
            user_service.license_info = request.POST.get("license_info")
            user_service.save()

            for attachment in attachments:
                if attachment:
                    ServiceAttachment.objects.create(
                        user_service=user_service, attachment=attachment
                    )

            etc = [
                ["license_date_from", license_date_from.date()],
                ["license_date_to", license_date_to.date()],
                ["service_policy_price_option", service_policy_price_option],
                ["license_info", request.POST.get("license_info")],
            ]
            make_system_log(
                before_user_service,
                "계정 - 서비스",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                etc=etc,
                identifier=user_service.id,
                default_log=default_log,
            )

            # context = self.get_context_data()
            # context["success"] = "connect"

            return HttpResponseRedirect(self.get_success_url())

        elif request.POST.get("form_type") == "service_delete":
            user_service_id = request.POST.get("service_id")
            user_service = UserService.objects.get(id=user_service_id)
            before_service = copy.deepcopy(user_service)
            default_log = SystemLog.objects.create(
                page_name="계정 - 서비스",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="delete",
                status_code="500",
            )

            try:
                user_service.delete()
            except Exception as e:
                print(e)
                context = self.get_context_data()
                context["fail"] = "delete"
                return self.render_to_response(context)
            extra_content = f"{request.user.profile.name}님에 의해 {before_service.service_policy_price_option.get_service_code()} 계정 서비스 삭제"  # noqa
            print(before_service.__dict__)
            make_system_log(
                before_service,
                "계정 - 서비스",
                self.request.environ["PATH_INFO"],
                self.request.user,
                "delete",
                identifier=before_service.id,
                default_log=default_log,
                extra_content=extra_content,
                extra_url=reverse_lazy(
                    "myinco_admin-user-detail",
                    kwargs={
                        "id": before_service.target_user.profile.id,
                        "tab": 0,
                    },
                ),
            )

            context = self.get_context_data()
            context["success"] = "delete"
            return HttpResponseRedirect(
                reverse_lazy(
                    "myinco_admin-user-detail",
                    kwargs={
                        "id": before_service.target_user.profile.id,
                        "tab": 0,
                    },
                )
            )
            #     if self.object.user.synced_user.all().count() > 0:
            #         for sync_customer in self.object.user.synced_user.all():
            #             sync_customer.is_synced = False

            #     self.object.is_deleted = True
            #     self.object.is_synced = False
            #     user_services = UserService.objects.filter(
            #         target_user=self.object.user
            #     )
            #     user_services.update(is_deleted=True)

            #     self.object.save()


def user_breakaway_ajax(request):
    default_log = SystemLog.objects.create(
        page_name="계정",
        url=request.environ["PATH_INFO"],
        user=request.user,
        method="update",
        status_code="500",
    )
    status = False if request.POST.get("status") == "false" else True
    target_user_id = request.POST.get("target_user_id")

    target_user = UserProfile.objects.get(id=target_user_id)
    before_target = copy.deepcopy(target_user)

    target_user.is_breaked = status
    target_user.grade = "1" if status else "0"
    target_user.save()

    etc = [["is_breaked", status], ["grade", "1" if status else "0"]]
    if status:
        extra_content = f"{request.user.profile.name} 님에 의해 {target_user.name}({target_user.user.username}) 계정 이탈 처리"  # noqa
    else:
        extra_content = f"{request.user.profile.name} 님에 의해 {target_user.name}({target_user.user.username}) 계정 복구 처리"  # noqa
    make_system_log(
        before_target,
        "계정",
        request.environ["PATH_INFO"],
        request.user,
        "update",
        identifier=before_target.id,
        etc=etc,
        extra_content=extra_content,
        default_log=default_log,
        extra_url=reverse_lazy(
            "myinco_admin-user-detail",
            kwargs={"id": target_user.id, "tab": "0"},
        ),
    )

    # 유저로그 추가해야 함

    return JsonResponse({"success": "success"}, status=200)


def open_userservice_update_modal(request, id, tab, pk):
    object_id = request.POST.get("service_id")
    user_service = UserService.objects.get(id=object_id)
    policys = ServicePolicyPriceOption.objects.all()
    selected_policy = user_service.service_policy_price_option

    try:
        context = {
            "object": user_service,
            "user": request.user,
            "policys": policys,
            "form": UserServiceUpdateForm(instance=user_service),
            "selected_policy": selected_policy,
        }

        return JsonResponse(
            {
                "data": render_to_string(
                    "myinco_admin/user/service_modal.html", context
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
