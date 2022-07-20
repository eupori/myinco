from django import forms
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
)

from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.db.models import Case, When, Q
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from isghome.views.myinco.util import make_system_log

from isghome.models import (
    User,
    UserProfile,
    Order,
    Customer,
    CustomerBookmark,
    CustomerLog,
    Organization,
    OrderCart,
    SystemLog,
)

import copy


class CustomerCreateForm(forms.ModelForm):
    class Meta:
        model = Customer
        exclude = ["grade", "synced_user", "is_synced"]

    def __init__(self, *args, **kwargs):
        super(CustomerCreateForm, self).__init__(*args, **kwargs)
        ordering = ["place_name"]

        self.fields["organization"] = forms.ModelChoiceField(
            initial=self.instance.organization if self.instance.id else None,
            queryset=Organization.objects.exclude(is_deleted=True).order_by(
                *ordering
            ),
        )


class MyincoAdminCustomerListView(ListView, CreateView):
    template_name = "myinco_admin/customer/list.html"
    model = Customer
    ordering = ("-ctime",)
    form_class = CustomerCreateForm
    # success_url = reverse_lazy("myinco_admin-customer-list")

    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return str(
            reverse_lazy("myinco_admin-customer-list")
        )  # success_url may be lazy

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
                | Q(email__icontains=keyword)
                | Q(synced_user__user_service__license_info__icontains=keyword)
            )

        queryset = queryset.filter(is_deleted=False)

        # queryset = queryset.annotate(
        #     is_bookmarked=Case(
        #         When(
        #             customerbookmark__user__id=user_id,
        #             then=True,
        #         ),
        #         default=False,
        #     )
        # ).distinct()

        queryset = queryset.annotate(
            is_bookmarked=Case(
                When(
                    customerbookmark__user__id=user_id,
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
        context_data["total_object_list"] = context_data["object_list"]
        p = Paginator(objects, 10)
        context_data["object_list"] = p.page(1)
        context_data["page"] = 1
        return context_data

    # def post(self, request, *args, **kwargs):
    #     print(request.POST)
    #     self.object = None
    #     queryset = self.get_queryset()
    #     self.object_list = queryset
    #     context = self.get_context_data()
    #     return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = None
        queryset = self.get_queryset()
        self.object_list = queryset
        # 신규 고객사 추가
        if request.POST.get("id_new_organization"):
            default_log = SystemLog.objects.create(
                page_name="고객사",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="create",
                status_code="500",
            )
            organization = Organization.objects.create(
                place_name=request.POST.get("id_new_organization"),
                address=request.POST.get("address"),
                address_detail=request.POST.get("address_detail"),
                post_number=request.POST.get("post_code"),
            )

            if organization:
                mutable = request.POST._mutable
                request.POST._mutable = True
                request.POST["organization"] = str(organization.id)
                request.POST._mutable = mutable
                organization.manager.add(request.user)
                organization.save()

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
                    extra_ur=extra_url,
                )
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # before create object
        default_log = SystemLog.objects.create(
            page_name="고객",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="create",
            status_code="500",
        )
        customer = form.save(commit=False)
        customer.grade = "0"
        customer.funnels = "sales"
        # customer = form.save()
        customer.save()
        customer.manager.add(self.request.user)
        customer.save()

        extra_url = reverse_lazy(
            "myinco_admin-customer-detail",
            kwargs={"id": customer.id, "tab": 0},
        )
        make_system_log(
            customer,
            "고객",
            self.request.environ["PATH_INFO"],
            self.request.user,
            "create",
            identifier=customer.id,
            default_log=default_log,
            extra_url=extra_url,
        )

        # after create object
        # return super().form_valid(form)
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context["errors"] = form.errors
        print(form.errors)
        return self.render_to_response(context)


def customer_page_ajax(request):
    user_id = request.POST.get("user_id")
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = Customer.objects.filter(is_deleted=False)

    if keyword:
        queryset = queryset.filter(
            Q(name__icontains=keyword)
            | Q(organization__place_name__icontains=keyword)
            | Q(phone_number__icontains=keyword)
            | Q(email__icontains=keyword)
            | Q(synced_user__user_service__license_info__icontains=keyword)
        )

    queryset = queryset.filter(is_deleted=False)

    queryset = queryset.annotate(
        is_bookmarked=Case(
            When(
                customerbookmark__user__id=user_id,
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
                    "myinco_admin/customer/list_ajax.html", context
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


def customer_bookmark_ajax(request):
    user = request.POST.get("user")
    customer = request.POST.get("customer")
    status = True if request.POST.get("status") == "true" else False

    bookmarks = CustomerBookmark.objects.filter(
        customer=Customer.objects.get(id=customer),
        user=User.objects.get(id=user),
    )

    if status:
        if bookmarks:
            return JsonResponse({"data": "bookmark already added"}, status=200)
        else:
            CustomerBookmark.objects.create(
                customer=Customer.objects.get(id=customer),
                user=User.objects.get(id=user),
            )
            try:
                CustomerLog.objects.create(
                    customer=Customer.objects.get(id=customer),
                    diff="add bookmark",
                )
                print("customer log create success!!")
            except Exception as e:
                print(e)

            return JsonResponse({"data": "bookmark added"}, status=200)
    else:
        if not bookmarks:
            return JsonResponse(
                {"data": "bookmark already removed"}, status=200
            )
        else:
            CustomerBookmark.objects.get(
                customer=Customer.objects.get(id=customer),
                user=User.objects.get(id=user),
            ).delete()

            bookmarks = CustomerBookmark.objects.filter(
                customer=Customer.objects.get(id=customer),
                user=User.objects.get(id=user),
            )

            try:
                CustomerLog.objects.create(
                    customer=customer, diff="remove bookmark"
                )
            except Exception as e:
                print(e)

            return JsonResponse({"data": "bookmark removed"}, status=200)


def open_customer_history_modal(request):
    object_id = request.POST.get("customer_id")
    customer = Customer.objects.get(id=object_id)
    historys = SystemLog.objects.filter(
        model="Customer", model_identifier=customer.id
    ).order_by("-ctime")

    context = {
        "object": customer,
        "user": request.user,
        "historys": historys,
    }

    return JsonResponse(
        {
            "data": render_to_string(
                "myinco_admin/customer/history_modal.html", context
            ),
            "status": True,
        }
    )


class MyincoAdminCustomerDetailView(DetailView, UpdateView):
    template_name = "myinco_admin/customer/detail.html"
    model = Customer
    pk_url_kwarg = "id"
    slug_url_kwarg = "tab"
    form_class = CustomerCreateForm

    def get_success_url(self):
        return str(
            reverse_lazy(
                "myinco_admin-customer-detail",
                kwargs={"id": self.kwargs["id"], "tab": self.kwargs["tab"]},
            )
        )  # success_url may be lazy

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        customer = data["object"]
        customer_form = CustomerCreateForm(instance=customer)
        data["customer_form"] = customer_form
        data["tab"] = self.kwargs["tab"]

        if customer.synced_user:
            synced_user = customer.synced_user
            if synced_user:
                data["orders"] = Order.objects.filter(
                    Q(purchaser_user=synced_user)
                    | Q(purchaser_customer=customer)
                ).distinct()
            else:
                data["orders"] = Order.objects.filter(
                    purchaser_customer=customer
                )
        else:
            data["orders"] = Order.objects.filter(purchaser_customer=customer)

        users = UserProfile.objects.filter(is_deleted=False).order_by("-ctime")

        recommend_users = []
        for each in users:
            if each.name == customer.name:
                if each.phone_number == customer.phone_number:
                    recommend_users.append(each)
                elif each.user.email == customer.email:
                    recommend_users.append(each)
        data["recommends"] = recommend_users

        # profiles = users.filter(~Q(name=None))
        profiles = users.filter()
        p = Paginator(profiles, 10)
        data["search_user_list"] = p.page(1)

        data["order_carts"] = OrderCart.objects.filter(
            order__purchaser_customer=customer
        )

        data["historys"] = SystemLog.objects.filter(
            model="Customer", model_identifier=customer.id
        ).order_by("-ctime")

        data["page"] = 1

        # MyModel.objects.none()
        salesactivity_list = []
        for sa in self.object.salesactivity_set.all():
            if sa.check_permission(self.request.user):
                salesactivity_list.append(sa)
        data["salesactivity_list"] = salesactivity_list

        return data

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.POST.get("form_type") == "update":

            # 신규 고객사 추가
            if request.POST.get("id_new_organization"):
                default_log = SystemLog.objects.create(
                    page_name="고객사",
                    url=self.request.environ["PATH_INFO"],
                    user=self.request.user,
                    method="create",
                    status_code="500",
                )

                organization = Organization.objects.create(
                    place_name=request.POST.get("id_new_organization"),
                    address=request.POST.get("address"),
                    address_detail=request.POST.get("address_detail"),
                    post_number=request.POST.get("post_code"),
                )

                if organization:
                    make_system_log(
                        organization,
                        "고객사",
                        self.request.environ["PATH_INFO"],
                        self.request.user,
                        "create",
                        identifier=organization.id,
                        default_log=default_log,
                    )

                    mutable = request.POST._mutable
                    request.POST._mutable = True
                    request.POST["organization"] = str(organization.id)
                    request.POST._mutable = mutable

            return super().post(request, *args, **kwargs)
        elif request.POST.get("form_type") == "connect":
            customer = self.object
            before_customer = copy.deepcopy(self.object)
            user = UserProfile.objects.get(
                id=request.POST.get("recommend_user_id")
            ).user

            if request.POST.get("is_connected") == "true":
                print("연동 취소")
                default_log = SystemLog.objects.create(
                    page_name="고객",
                    url=self.request.environ["PATH_INFO"],
                    user=self.request.user,
                    method="update",
                    status_code="500",
                )
                synced_user = customer.synced_user
                synced_user.profile.is_synced = False
                synced_user.profile.save()
                customer.synced_user = None
                customer.is_synced = False
                customer.save()

                etc = [["is_synced", False]]
                extra_content = f"{request.user.profile.name}님에 의해 {customer.name}({customer.email}) 고객, 계정({user.profile.name}, {user.username})연동취소"  # noqa
                make_system_log(
                    before_customer,
                    "고객",
                    request.environ["PATH_INFO"],
                    request.user,
                    "update",
                    identifier=before_customer.id,
                    etc=etc,
                    extra_content=extra_content,
                    default_log=default_log,
                )
            else:
                print("연동")
                default_log = SystemLog.objects.create(
                    page_name="고객",
                    url=self.request.environ["PATH_INFO"],
                    user=self.request.user,
                    method="update",
                    status_code="500",
                )

                if user.synced_user.last():
                    before_customer = user.synced_user.last()
                    before_customer.is_synced = False
                    before_customer.synced_user = None
                    before_customer.save()

                customer.synced_user = user
                customer.is_synced = True
                user.profile.is_synced = True
                user.profile.save()
                customer.save()

                etc = [["is_synced", True]]
                if request.POST.get("method") == "recommend":
                    extra_content = f"{request.user.profile.name}님에 의해 {customer.name}({customer.email}) 고객, 추천 데이터({user.profile.name}, {user.username})연동"  # noqa
                if request.POST.get("method") == "search":
                    extra_content = f"{request.user.profile.name}님에 의해 {customer.name}({customer.email}) 고객, 검색 데이터({user.profile.name}, {user.username})연동"  # noqa
                make_system_log(
                    before_customer,
                    "고객",
                    request.environ["PATH_INFO"],
                    request.user,
                    "update",
                    identifier=before_customer.id,
                    etc=etc,
                    extra_content=extra_content,
                    default_log=default_log,
                )

            context = self.get_context_data()
            context["success"] = "connect"
            return self.render_to_response(context)

        elif request.POST.get("form_type") == "delete":

            before_customer = copy.deepcopy(self.object)
            default_log = SystemLog.objects.create(
                page_name="고객",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="delete",
                status_code="500",
            )
            try:
                if self.object.synced_user:
                    self.object.synced_user.profile.is_synced = False
                    self.object.synced_user.profile.save()

                self.object.is_deleted = True
                self.object.save()
            except Exception as e:
                print(e)
                context = self.get_context_data()
                context["fail"] = "delete"
                return self.render_to_response(context)

            extra_content = f"{request.user.profile.name}님에 의해 {before_customer.name}({before_customer.email}) 고객 삭제"  # noqa
            make_system_log(
                before_customer,
                "고객",
                self.request.environ["PATH_INFO"],
                self.request.user,
                "delete",
                identifier=before_customer.id,
                default_log=default_log,
                extra_content=extra_content,
                extra_url=reverse_lazy("myinco_admin-customer-list"),
            )

            context = self.get_context_data()
            context["success"] = "delete"
            return HttpResponseRedirect(
                reverse_lazy("myinco_admin-customer-list")
            )

    def form_valid(self, form):
        # before create object
        before_customer = Customer.objects.get(pk=self.kwargs["id"])
        default_log = SystemLog.objects.create(
            page_name="고객",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="update",
            status_code="500",
        )

        system_log = make_system_log(
            before_customer,
            "고객",
            self.request.environ["PATH_INFO"],
            self.request.user,
            "update",
            identifier=before_customer.id,
            form=form,
            is_created=False,
            default_log=default_log,
        )
        self.object = form.save(commit=False)
        self.object = form.save()
        if system_log:
            system_log.save_with_url()

        # after create object
        return super().form_valid(form)

    def form_invalid(self, form):
        SystemLog.objects.create(
            page_name="고객",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="update",
            status_code="500",
        )

        context = self.get_context_data(form=form)
        context["errors"] = form.errors
        print(form.errors)
        return self.render_to_response(context)


def search_user_page_ajax(request):
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = UserProfile.objects.filter(is_deleted=False)

    if keyword:
        queryset = queryset.filter(
            ~Q(name=None) & Q(name__icontains=keyword)
            | Q(organization__place_name__icontains=keyword)
            | Q(job_position__icontains=keyword)
            | Q(phone_number__icontains=keyword)
            | Q(organization__address_name__icontains=keyword)  # noqa
        )
    queryset = queryset.order_by("-ctime")

    try:
        p = Paginator(queryset, 10)
        queryset = p.page(int(page))

        context = {"search_user_list": queryset, "page": int(page)}

        return JsonResponse(
            {
                "data": render_to_string(
                    "myinco_admin/customer/search_user_ajax.html", context
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


def customer_breakaway_ajax(request):
    status = False if request.POST.get("status") == "false" else True
    customer_id = request.POST.get("customer_id")
    user_id = request.POST.get("user_id")

    customer = Customer.objects.get(id=customer_id)
    user = User.objects.get(id=user_id)
    before_target = copy.deepcopy(customer)

    default_log = SystemLog.objects.create(
        page_name="고객",
        url=request.environ["PATH_INFO"],
        user=request.user,
        method="update",
        status_code="500",
    )

    customer.is_breaked = status
    customer.grade = "2" if status else "0"
    customer.save()

    CustomerLog.objects.create(
        customer=customer, diff="status change to " + str(status), user=user
    )

    etc = [["is_breaked", status], ["grade", "1" if status else "0"]]
    if status:
        extra_content = f"{request.user.profile.name} 님에 의해 {before_target.name}({before_target.email}) 계정 이탈 처리"  # noqa
    else:
        extra_content = f"{request.user.profile.name} 님에 의해 {before_target.name}({before_target.email}) 계정 복구 처리"  # noqa
    make_system_log(
        before_target,
        "고객",
        request.environ["PATH_INFO"],
        request.user,
        "update",
        identifier=before_target.id,
        etc=etc,
        extra_content=extra_content,
        default_log=default_log,
        extra_url=reverse_lazy(
            "myinco_admin-customer-detail",
            kwargs={"id": customer.id, "tab": "0"},
        ),
    )

    return JsonResponse({"success": "success"}, status=200)


def search_customer_page_ajax(request):
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = Customer.objects.filter(is_deleted=False)

    if keyword:
        queryset = queryset.filter(
            # ~Q(name=None) & Q(name__icontains=keyword)
            Q(name__icontains=keyword)
            | Q(organization__place_name__icontains=keyword)
            | Q(job_position__icontains=keyword)
            | Q(phone_number__icontains=keyword)
            | Q(organization__address_name__icontains=keyword)  # noqa
        )
    queryset = queryset.order_by("-ctime")

    try:
        p = Paginator(queryset, 10)
        queryset = p.page(int(page))

        context = {"search_customer_list": queryset, "page": int(page)}

        return JsonResponse(
            {
                "data": render_to_string(
                    "myinco_admin/user/search_customer_ajax.html", context
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


class CustomerListView(ListView):
    model = Customer
    template_name = ""

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        org_id = request.GET.get("org_id")
        if org_id and org_id.isdigit():
            queryset = queryset.filter(
                organization__id=org_id, is_deleted=False
            )
            queryset = queryset.order_by("name")
            customer_list = [
                {"id": customer.id, "name": customer.name}
                for customer in queryset
            ]
        else:
            customer_list = []
        return JsonResponse({"customer_list": customer_list})


class CustomerInfoView(DetailView):
    model = Customer
    template_name = ""

    def get(self, request, *args, **kwargs):
        customer = self.get_object()
        data = {
            "phone_number": customer.phone_number.as_national,
            "email": customer.email,
            "job_position": customer.job_position,
        }
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
            }
        )
