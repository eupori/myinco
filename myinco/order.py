import json
import datetime
import copy

from django import forms
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
)

from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe
from django.db.models import Case, When, Q
from django.db import transaction
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from isghome.views import send_auto_email

from isghome.models import (
    User,
    Order,
    Quotation,
    OrderBookmark,
    Payment,
    PurchaseOrder,
    OrderLog,
    OrderCart,
    ServicePolicyPriceOption,
    Organization,
    Customer,
    SystemLog,
    AuthGroup,
)
from isghome.views import generate_order_identifier
from isghome.utils import PDFError, QuotationError
from isghome.views.myinco.util import make_system_log
from isghome.utils import myinco_token_generator
from isghome.tasks import update_quotation

import time


class OrderDetailForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ("status", "manager")


class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ("order_type", "purchaser_user", "purchaser_customer")


class MyModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.profile.name


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        exclude = ("order",)

    def __init__(self, *args, **kwargs):
        super(QuotationForm, self).__init__(*args, **kwargs)
        ordering = ["-profile__auth_grade", "profile__name"]
        if self.instance:
            self.fields["is_published"] = forms.ChoiceField(
                widget=forms.Select(
                    attrs={"id": "is_published" + str(self.instance.id)}
                ),
                choices=Quotation.PUBLISH_CHOICES,
                initial=self.instance.is_published,
            )
            self.fields["pub_date_to"] = forms.DateField(
                widget=forms.DateInput(
                    format="%Y년 %m월 %d일",
                    attrs={"id": "pub_date_to_" + str(self.instance.id)},
                ),
                initial=self.instance.pub_date_to,
            )
            self.fields["pub_date_from"] = forms.DateField(
                widget=forms.DateInput(
                    format="%Y년 %m월 %d일",
                    attrs={"id": "pub_date_from_" + str(self.instance.id)},
                ),
                initial=self.instance.pub_date_from,
            )
            self.fields["manager"] = MyModelChoiceField(
                widget=forms.Select(
                    attrs={"id": "manager" + str(self.instance.id)}
                ),
                initial=self.instance.manager,
                queryset=AuthGroup.objects.get(name="영업담당자")
                .get_child_users()
                .order_by(*ordering),
            )
            self.fields[
                "special_offer_price"
            ].initial = self.instance.special_offer_price


class MyincoAdminOrderListView(ListView, CreateView):
    template_name = "myinco_admin/order/list.html"
    model = Order
    form_class = OrderCreateForm
    ordering = ("-ctime",)

    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.user.id
        keyword = self.request.GET.get("keyword")

        if keyword:
            # code_ids = []
            # for order in queryset:
            #     service_code_check = [
            #         keyword in item.policy.get_service_code()
            #         for item in order.ordercart_set.all()
            #     ]
            #     print(
            #         [
            #             item.policy.get_service_code()
            #             for item in order.ordercart_set.all()
            #         ]
            #     )
            #     if any(service_code_check):
            #         code_ids.append(order.id)

            queryset = queryset.filter(
                Q(identifier__icontains=keyword)
                | Q(manager__profile__name__icontains=keyword)
                | Q(purchaser_customer__email__icontains=keyword)
                | Q(purchaser_customer__name__icontains=keyword)
                | Q(purchaser_customer__phone_number__icontains=keyword)
                | Q(
                    purchaser_customer__organization__place_name__icontains=keyword  # noqa
                )
                | Q(purchaser_user__username__icontains=keyword)
                | Q(purchaser_user__profile__name__icontains=keyword)
                | Q(purchaser_user__profile__phone_number__icontains=keyword)
                | Q(
                    purchaser_user__profile__organization__place_name__icontains=keyword  # noqa
                )
                | Q(ordercart__policy__product_name__icontains=keyword)
                # | Q(ordercart__policy__get_service_code=keyword)  # noqa
                | Q(ordercart__policy__service_code__icontains=keyword)
            )

        # 관련주문 제외
        # queryset = queryset.exclude(order_type="division")

        # queryset = queryset.annotate(
        #     is_bookmarked=Case(
        #         When(
        #             orderbookmark__user__id=user_id,
        #             then=True,
        #         ),
        #         default=False,
        #     ),
        #     final_price=F("payment__final_price"),
        # ).distinct()

        queryset = queryset.annotate(
            is_bookmarked=Case(
                When(
                    orderbookmark__user__id=user_id,
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

        ordering = self.get_ordering()
        if ordering:
            if isinstance(ordering, str):
                ordering = (ordering,)
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["bookmark_count"] = self.object_list.filter(
            is_bookmarked=True
        ).count()
        data["total_order_count"] = Order.objects.filter(
            is_deleted=False
        ).count()

        # 서비스
        policys = ServicePolicyPriceOption.objects.all()
        policy_dict = {
            policy.product_name: list(
                filter(
                    lambda x: x.product_name == policy.product_name, policys
                )
            )
            for policy in policys
        }

        # policy_dict = {}
        # for policy in policys:
        #     if policy.product_name in policy_dict:
        #         policy_dict[policy.product_name].append(policy)
        #     else:
        #         policy_dict[policy.product_name] = [policy]

        data["policys"] = policy_dict
        data["organizations"] = Organization.objects.filter(is_deleted=False)

        objects = data["object_list"]
        data["total_object_list"] = data["object_list"]
        p = Paginator(objects, 10)
        data["object_list"] = p.page(1)
        data["page"] = 1

        return data

    # 해당 post 는 추후 주문번호 정책 반영 시 form_save 로 전체 코드 변경 예정
    def post(self, request, *args, **kwargs):
        input_service = request.POST.get("input_service")
        input_order_type = request.POST.get("input_order_type")
        purchaser_user = request.POST.get("purchaser_user")

        default_log = SystemLog.objects.create(
            page_name="솔루션 주문",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="create",
            status_code="500",
        )

        if input_service:
            services = json.loads(input_service)

        # purchaser_organization = request.POST.get('purchaser_organization')
        # organization = Organization.objects.get(id=purchaser_organization)
        if request.POST.get("input_order_type") == "0":
            target_user = User.objects.get(id=purchaser_user)
        elif request.POST.get("input_order_type") == "1":
            customer = Customer.objects.get(id=purchaser_user)

        order_type = ""
        if input_order_type == "0":  # 온라인 주문
            order_type = "online"
            user = target_user
            customer = None
        elif input_order_type == "1":  # 오프라인 주문
            order_type = "sales"
            user = None
            customer = customer
        elif input_order_type == "2":  # 관련 주문
            order_type = "division"

        if order_type == "division":
            parent_order = Order.objects.get(
                id=request.POST.get("input_order")
            )
            order = Order.objects.create(
                order_type=order_type,
                identifier=parent_order.get_expected_number(),
                purchaser_user=parent_order.purchaser_user,
                purchaser_customer=parent_order.purchaser_customer,
                payment_method=parent_order.payment_method,
                parent=parent_order,
            )
            if order:
                order.manager.add(self.request.user)
                OrderLog.objects.create(
                    order=order,
                    to_status="estimate-request",
                    mtime=datetime.datetime.now(),
                    user=self.request.user,
                )

                make_system_log(
                    order,
                    "솔루션 주문",
                    request.environ["PATH_INFO"],
                    request.user,
                    "create",
                    identifier=order.id,
                    default_log=default_log,
                )

                if order.purchaser_user:
                    target = order.purchaser_user.username
                    name = order.purchaser_user.profile.name
                elif order.purchaser_customer:
                    target = order.purchaser_customer.email
                    name = order.purchaser_customer.name

                content = "서비스 견적을 요청했어요."
                send_auto_email(
                    client_info=order,
                    email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
                    email_template="myinco_admin/order/order_email.html",
                    to_email=target,
                    sub_title=content,
                )

                return HttpResponseRedirect(
                    reverse_lazy("myinco_admin-order-list")
                )
        else:
            identifier = generate_order_identifier(
                    service_type='solution', order_type=order_type)

            order = Order.objects.create(
                order_type=order_type,
                identifier=identifier,
                purchaser_user=user,
                purchaser_customer=customer,
                payment_method="manager",
            )

            for service in services:
                policy_option = ServicePolicyPriceOption.objects.get(
                    id=service["id"]
                )

                OrderCart.objects.create(
                    order=order,
                    policy=policy_option,
                    quantity=int(service["count"]),
                    price=policy_option.price * int(service["count"]),
                    # is_ordered=True,
                )

            if order:
                order.manager.add(self.request.user)
                OrderLog.objects.create(
                    order=order,
                    to_status="estimate-request",
                    mtime=datetime.datetime.now(),
                    user=self.request.user,
                )
                extra_url = reverse_lazy(
                    "myinco_admin-order-detail", kwargs={"id": order.id}
                )
                make_system_log(
                    order,
                    "솔루션 주문",
                    request.environ["PATH_INFO"],
                    request.user,
                    "create",
                    identifier=order.id,
                    default_log=default_log,
                    extra_url=extra_url,
                )

                if order.purchaser_user:
                    target = order.purchaser_user.username
                    name = order.purchaser_user.profile.name
                elif order.purchaser_customer:
                    target = order.purchaser_customer.email
                    name = order.purchaser_customer.name

                content = "서비스 견적을 요청했어요."
                send_auto_email(
                    client_info=order,
                    email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
                    email_template="myinco_admin/order/order_email.html",
                    to_email=target,
                    sub_title=content,
                )

                return HttpResponseRedirect(
                    reverse_lazy("myinco_admin-order-list")
                )


def order_page_ajax(request):
    user_id = request.POST.get("user_id")
    keyword = request.POST.get("keyword")
    page = request.POST.get("page")
    queryset = Order.objects.all()

    if keyword:
        queryset = queryset.filter(
            Q(identifier__icontains=keyword)
            | Q(manager__profile__name__icontains=keyword)
            | Q(purchaser_customer__email__icontains=keyword)
            | Q(purchaser_customer__name__icontains=keyword)
            | Q(purchaser_customer__phone_number__icontains=keyword)
            | Q(
                purchaser_customer__organization__place_name__icontains=keyword
            )
            | Q(purchaser_user__username__icontains=keyword)
            | Q(purchaser_user__profile__name__icontains=keyword)
            | Q(purchaser_user__profile__phone_number__icontains=keyword)
            | Q(
                purchaser_user__profile__organization__place_name__icontains=keyword  # noqa
            )
            | Q(ordercart__policy__product_name__icontains=keyword)
            # | Q(ordercart__policy__product_name__get_service_code=keyword)
        )

    # 관련주문 제외
    # queryset = queryset.exclude(order_type="division")
    queryset = queryset.filter(is_deleted=False)

    queryset = queryset.annotate(
        is_bookmarked=Case(
            When(
                orderbookmark__user__id=user_id,
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
                    "myinco_admin/order/list_ajax.html", context
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


def bookmark_ajax(request):
    user = request.POST.get("user")
    order = request.POST.get("order")
    status = True if request.POST.get("status") == "true" else False

    bookmarks = OrderBookmark.objects.filter(
        order=Order.objects.get(identifier=order),
        user=User.objects.get(id=user),
    )

    if not status:
        if bookmarks:
            return JsonResponse({"data": "bookmark already added"}, status=200)
        else:
            OrderBookmark.objects.create(
                order=Order.objects.get(identifier=order),
                user=User.objects.get(id=user),
            )
            return JsonResponse({"data": "bookmark added"}, status=200)

    else:
        if not bookmarks:
            return JsonResponse(
                {"data": "bookmark already removed"}, status=200
            )
        else:
            OrderBookmark.objects.get(
                order=Order.objects.get(identifier=order),
                user=User.objects.get(id=user),
            ).delete()
            bookmarks = OrderBookmark.objects.filter(
                order=Order.objects.get(identifier=order),
                user=User.objects.get(id=user),
            )
            return JsonResponse({"data": "bookmark removed"}, status=200)


class MyincoAdminOrderDetailView(DetailView):
    template_name = "myinco_admin/order/detail.html"
    pk_url_kwarg = "id"
    model = Order

    def get_table_data(self):
        table_data = []
        for index, ordercart in enumerate(self.object.ordercart_set.all()):
            row = []
            row.append(index + 1)
            row.append(ordercart.policy.product_name)
            row.append("CODE:" + ordercart.policy.get_service_code())
            row.append(ordercart.quantity)
            row.append(ordercart.price)
            row.append(ordercart.quantity * ordercart.price)
            table_data.append(row)
            for each in ordercart.policy.get_options():
                sub_row = []
                sub_row.append("")
                sub_row.append("")
                sub_row.append(each.group_code.name + ":" + each.name)
                table_data.append(sub_row)
                sub_row.append("")
                sub_row.append("")
                sub_row.append("")
        return table_data

    def get_context_data(self, **kwargs):
        self.object = self.get_object()
        data = super().get_context_data(**kwargs)
        # purchaser = self.object.user

        # set quotation init information(receiver)
        receiver_name = ""
        receiver_organization = ""
        receiver_email = ""
        # 추후 user 업데이트 이후 다시 수정 예정
        # if isinstance(purchaser, Customer):
        #     order_list = purchaser.purchaser_customer.all()
        #     receiver_name = purchaser.name
        #     receiver_organization = purchaser.organization.place_name
        #     receiver_email = purchaser.email
        # else:
        #     order_list = purchaser.purchaser_user.all()
        #     receiver_email = purchaser.email

        if self.object.purchaser_user:
            synced_customer = self.object.purchaser_user.synced_user.first()
            if synced_customer:
                order_list = Order.objects.filter(
                    Q(purchaser_user=self.object.purchaser_user)
                    | Q(purchaser_customer=synced_customer)
                ).distinct()
                receiver_email = synced_customer.email
                if synced_customer.organization:
                    receiver_organization = (
                        synced_customer.organization.place_name
                    )
                receiver_name = synced_customer.name
            else:
                order_list = Order.objects.filter(
                    purchaser_user=self.object.purchaser_user
                )

            receiver_name = self.object.purchaser_user.profile.name
            if self.object.purchaser_user.profile.organization:
                receiver_organization = (
                    self.object.purchaser_user.profile.organization.place_name
                )
            receiver_email = self.object.purchaser_user.username
        elif self.object.purchaser_customer:
            synced_user = self.object.purchaser_customer.synced_user
            if synced_user:
                order_list = Order.objects.filter(
                    Q(purchaser_user=synced_user)
                    | Q(purchaser_customer=self.object.purchaser_customer)
                ).distinct()
            else:
                order_list = Order.objects.filter(
                    purchaser_customer=self.object.purchaser_customer
                )
            receiver_email = self.object.purchaser_customer.email
            if self.object.purchaser_customer.organization:
                receiver_organization = (
                    self.object.purchaser_customer.organization.place_name
                )  # noqa
            receiver_name = self.object.purchaser_customer.name

        # order_list = purchaser.purchaser_user.all()
        # if purchaser:
        #     receiver_email = purchaser.email
        #     receiver_organization = purchaser.organization
        #     receiver_name = purchaser.name
        data["order_list"] = order_list

        quotation_form = QuotationForm(
            initial={
                "manager": User.objects.filter(is_staff=True).first(),
                "receiver_name": receiver_name,
                "receiver_organization": receiver_organization,
                "receiver_email": receiver_email,
                "original_price": 0,
                "vat": 0,
                "final_price": 0,
            }
        )
        order_form = OrderDetailForm(instance=self.object)
        data["quotation_form"] = quotation_form
        data["quotation_data"] = self.get_table_data()

        # set existing quotation information
        quotations = self.object.quotation_set.all().order_by("-ctime")
        data["quotations"] = quotations
        quotation_form_list = []
        for each in quotations:
            each.context = mark_safe(json.dumps(each.context))
            each.remarks = mark_safe(json.dumps(each.remarks))
            update_quotation_form = QuotationForm(instance=each)
            quotation_form_list.append((update_quotation_form, each))

        data["quotation_form_list"] = quotation_form_list
        data["order_form"] = order_form

        try:
            data["order_purchase"] = self.object.purchaseorder
        except Exception:
            data["order_purchase"] = None

        data["order_payment"] = None
        if self.object.payment_set.filter(is_payment=True):
            data["order_payment"] = self.object.payment_set.filter(
                is_payment=True
            ).first()

        ordering = ["-profile__auth_grade", "profile__name"]
        data["managers"] = User.objects.filter(
            profile__auth_grade__in=[2, 3],
        ).order_by(*ordering)

        data["historys"] = SystemLog.objects.filter(
            model="Order", model_identifier=self.object.id
        ).order_by("-ctime")

        if "errors" in self.kwargs:
            data["errors"] = self.kwargs["errors"]
        return data

    def change_order_setting(self, request, *args, **kwargs):
        order = Order.objects.get(id=request.POST.get("order_id"))
        before_order = copy.deepcopy(order)
        if request.POST.get("order-cancel") == "true":
            print("주문 취소")
            default_log = SystemLog.objects.create(
                page_name="솔루션 주문",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )
            order.status = "order-cancel"
            order.save()
            etc = [["status", "order-cancel"]]
            make_system_log(
                before_order,
                "솔루션 주문",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=order.id,
                etc=etc,
                default_log=default_log,
            )

            # content = "주문이 취소되었어요."
            # send_auto_email(
            #     client_info=order,
            #     email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
            #     email_template="myinco_admin/order/order_email.html",
            #     to_email=target,
            #     sub_title=content,
            # )

        elif request.POST.get("order-cancel") == "false":
            print("주문 복구")
            default_log = SystemLog.objects.create(
                page_name="솔루션 주문",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )

            order.status = "estimate-request"
            order.save()

            etc = [["status", "estimate-request"]]
            make_system_log(
                before_order,
                "솔루션 주문",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=order.id,
                etc=etc,
                default_log=default_log,
            )

        if request.POST.get("order_publish") == "false":
            print("주문 비공개")
            default_log = SystemLog.objects.create(
                page_name="솔루션 주문",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )

            order.is_active = False
            order.save()

            etc = [["is_active", False]]
            make_system_log(
                before_order,
                "솔루션 주문",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=order.id,
                etc=etc,
                default_log=default_log,
            )

        elif request.POST.get("order_publish") == "true":
            print("주문 공개")
            default_log = SystemLog.objects.create(
                page_name="솔루션 주문",
                url=self.request.environ["PATH_INFO"],
                user=self.request.user,
                method="update",
                status_code="500",
            )

            order.is_active = True
            order.save()

            etc = [["is_active", True]]
            make_system_log(
                before_order,
                "솔루션 주문",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=order.id,
                etc=etc,
                default_log=default_log,
            )

        return HttpResponseRedirect(
            reverse_lazy(
                "myinco_admin-order-detail", kwargs={"id": kwargs["id"]}
            )
            + "?tab=0"
        )  # noqa

    def change_order_status(self, request, *args, **kwargs):
        default_log = SystemLog.objects.create(
            page_name="솔루션 주문",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="update",
            status_code="500",
        )
        status = request.POST.get("status")
        manager_ids = request.POST.getlist("manager")

        order = Order.objects.get(id=kwargs["id"])
        before_order = copy.deepcopy(order)

        etc = [["manager", manager_ids], ["status", status]]
        system_log = make_system_log(
            before_order,
            "솔루션 주문",
            request.environ["PATH_INFO"],
            request.user,
            "update",
            identifier=before_order.id,
            etc=etc,
            is_created=False,
            default_log=default_log,
        )

        order.manager.clear()

        manager_name = []
        order.status = status
        for manager_obj in User.objects.filter(id__in=manager_ids):
            # manager_obj = User.objects.get(id=manager_id)
            order.manager.add(manager_obj)
            manager_name.append(manager_obj.username)
        order.save()

        diff = "담당자("
        for each in manager_name:
            diff += each + ","
        diff += ")"

        OrderLog.objects.create(
            order=order,
            to_status=order.status,
            mtime=datetime.datetime.now(),
            diff=diff,
            user=User.objects.get(id=self.request.user.id),
        )

        # 성공시
        if system_log:
            system_log.save_with_url()
            if order.purchaser_user:
                target = order.purchaser_user.username
                name = order.purchaser_user.profile.name
            elif order.purchaser_customer:
                target = order.purchaser_customer.email
                name = order.purchaser_customer.name

            if status == "estimate-request":
                content = "서비스 견적이 요청되었어요."
            elif status == "request-cancel":
                content = "서비스 견적요청을 취소되했어요."
            elif status == "estimate-complete":
                content = "서비스 견적이 완료되었어요."
            elif status == "estimate-re-request":
                content = "서비스 재견적을 요청했어요."
            elif status == "estimate-expire":
                content = "서비스 견적이 만료되었어요."
            elif status == "payment-request":
                content = "서비스 결제가 요청되었어요."
            elif status == "payment-cancel":
                content = "서비스 결제가 취소되었어요."
            elif status == "payment-complete":
                content = "서비스 결제가 완료되었어요."
            elif status == "order-cancel":
                content = "서비스 주문이 취소되었어요."

            send_auto_email(
                client_info=order,
                email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
                email_template="myinco_admin/order/order_email.html",
                to_email=target,
                sub_title=content,
            )

        return HttpResponseRedirect(
            reverse_lazy(
                "myinco_admin-order-detail", kwargs={"id": kwargs["id"]}
            )
            + "?tab=0"
        )  # noqa

    @transaction.atomic
    def save_quotation_form(self, request, *args, **kwargs):
        default_log = SystemLog.objects.create(
            page_name="솔루션 주문",
            url=self.request.environ["PATH_INFO"],
            user=self.request.user,
            method="update",
            status_code="500",
        )
        order = Order.objects.get(id=kwargs["id"])
        # before_order = copy.deepcopy(order)
        sheet = request.POST.get("sheet")
        sheet = json.loads(sheet)
        sheet_arr = []
        for row in sheet[1:]:
            # if row[0] == "":
            #     continue
            row_json = {}
            row_json["연번"] = row[0]
            row_json["제품명"] = row[1]
            row_json["사양"] = row[2]
            row_json["수량"] = row[3]
            row_json["단가(₩)"] = row[4]
            row_json["금액(₩)"] = row[5]
            sheet_arr.append(row_json)

        # comment_json = json.dumps(request.POST.getlist("comment"))
        comment_json = request.POST.getlist("comment")

        sheet_json = {"data": sheet_arr}

        manager = User.objects.get(id=request.POST.get("manager"))

        pub_date_from = datetime.datetime.strptime(
            request.POST.get("pub_date_from"), "%Y년 %m월 %d일"
        ).date()
        pub_date_to = datetime.datetime.strptime(
            request.POST.get("pub_date_to"), "%Y년 %m월 %d일"
        ).date()

        # sid = transaction.savepoint()

        if request.POST.get("quotation_id") is not None:
            """
            Quotation update
            """
            if request.POST.get("is_published"):

                # 견적서 공개 변경 시 발주서 삭제
                default_purchase_log = SystemLog.objects.create(
                    page_name="솔루션 주문",
                    url=request.environ["PATH_INFO"],
                    user=request.user,
                    method="update",
                    status_code="500",
                )

                try:
                    purchase_order = PurchaseOrder.objects.get(order=order)
                except PurchaseOrder.DoesNotExist:
                    purchase_order = None
                if purchase_order:
                    before_order = copy.deepcopy(order)
                    extra_content = (
                        f"{purchase_order.file_name} 발주서 삭제"  # noqa
                    )
                    purchase_order.delete()
                    order.status = "estimate-re-request"
                    order.save()

                    etc = [["status", "estimate-re-request"]]
                    make_system_log(
                        before_order,
                        "솔루션 주문",
                        request.environ["PATH_INFO"],
                        request.user,
                        "update",
                        identifier=order.id,
                        etc=etc,
                        default_log=default_purchase_log,
                        extra_content=extra_content,
                        extra_url=reverse_lazy(
                            "myinco_admin-order-detail",
                            kwargs={"id": order.id},
                        ),
                    )

                    if order.purchaser_user:
                        target = order.purchaser_user.username
                        name = order.purchaser_user.profile.name
                    elif order.purchaser_customer:
                        target = order.purchaser_customer.email
                        name = order.purchaser_customer.name

                    send_auto_email(
                        client_info=order,
                        email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
                        email_template="myinco_admin/order/order_email.html",
                        to_email=target,
                        sub_title="서비스 재견적을 요청했어요.",
                    )

                # 견적서 공개 변경 시 결제 삭제

            quotation_id = request.POST.get("quotation_id")
            info = {"quotation": quotation_id}
            quotation = Quotation.objects.get(id=quotation_id)
            # before_quotation = quotation.first()
            before_quotation = copy.deepcopy(quotation)

            data_dict = {
                "order": order,
                "name": request.POST.get("name"),
                "pub_date_from": pub_date_from,
                "pub_date_to": pub_date_to,
                "is_published": request.POST.get("is_published"),
                "manager": manager,
                "write_date": datetime.datetime.now().date(),
                "receiver_name": request.POST.get("receiver_name"),
                "receiver_organization": request.POST.get(
                    "receiver_organization"
                ),
                "receiver_email": request.POST.get("receiver_email"),
                "context": json.dumps(sheet_json),
                "remarks": comment_json,
                "original_price": request.POST.get("original_price"),
                "special_offer_price": request.POST.get("special_offer_price"),
                "vat": request.POST.get("vat"),
                "final_price": request.POST.get("final_price"),
            }
            data_dict["is_published"] = (
                True if data_dict["is_published"] == "True" else False
            )

            try:
                is_published = request.POST.get("is_published")
                if is_published:
                    order.status = "estimate-complete"
                    # order.quotation_set.all().update(is_published=False)
                    if is_published == "True":
                        is_published = True
                    else:
                        is_published = False
                else:
                    order.status = "estimate-request"
                # quotation.update(**data_dict)
                quotation.order = order
                quotation.name = request.POST.get("name")
                quotation.pub_date_from = pub_date_from
                quotation.pub_date_to = pub_date_to
                quotation.is_published = is_published
                quotation.manager = manager
                quotation.user = request.user
                quotation.write_date = datetime.datetime.now().date()
                quotation.receiver_name = request.POST.get("receiver_name")
                quotation.receiver_organization = request.POST.get(
                    "receiver_organization"
                )
                quotation.receiver_email = request.POST.get("receiver_email")
                quotation.context = sheet_json
                quotation.remarks = comment_json
                quotation.original_price = request.POST.get("original_price")
                quotation.special_offer_price = request.POST.get(
                    "special_offer_price"
                )
                quotation.vat = request.POST.get("vat")
                quotation.final_price = request.POST.get("final_price")

                quotation.save()

                order.save()

                if order.purchaser_user:
                    target = order.purchaser_user.username
                    name = order.purchaser_user.profile.name
                elif order.purchaser_customer:
                    target = order.purchaser_customer.email
                    name = order.purchaser_customer.name

                if order.status == "estimate-request":
                    content = "서비스 견적이 요청되었어요."
                elif order.status == "estimate-complete":
                    content = "서비스 견적이 완료되었어요."

                send_auto_email(
                    client_info=order,
                    email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
                    email_template="myinco_admin/order/order_email.html",
                    to_email=target,
                    sub_title=content,
                )

            except PDFError as e:
                # PDF 생성 오류 시에 대한 로직 추가 필요
                print("PDF 생성 오류", e)
                error_msg = "pdf변환 중 오류가 발생하였습니다."
                raise QuotationError(error_msg, info=info)
            except ZeroDivisionError as e:
                # 견적 생성 오류 시에 대한 로직 추가 필요
                print("견적서 생성 오류", e)
                # transaction.savepoint_rollback(sid)
                print(e.__dict__)
                error_msg = "견적서 생성중 오류가 발생하였습니다. (" + str(e) + ")"
                info = {"quotation": "create"}
                raise QuotationError(error_msg, info=info)
            except Exception as e:
                # 견적 생성 오류 시에 대한 로직 추가 필요
                print("견적서 생성 오류", e)
                # transaction.savepoint_rollback(sid)
                error_msg = "견적서 생성중 오류가 발생하였습니다.", +str(e)
                info = {"quotation": "create"}
                raise QuotationError(error_msg, info=info)

            etc = list(data_dict.items())
            make_system_log(
                before_quotation,
                "솔루션 주문 - 견적관리",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=before_quotation.id,
                etc=etc,
                default_log=default_log,
            )
        else:
            """
            Quotation create
            """
            try:
                print("==============", sheet_json.__class__)
                quotation = Quotation.objects.create(
                    order=order,
                    name=request.POST.get("name"),
                    pub_date_from=pub_date_from,
                    pub_date_to=pub_date_to,
                    is_published=request.POST.get("is_published"),
                    manager=manager,
                    write_date=datetime.datetime.now(),
                    receiver_name=request.POST.get("receiver_name"),
                    receiver_organization=request.POST.get(
                        "receiver_organization"
                    ),
                    receiver_email=request.POST.get("receiver_email"),
                    # context=json.dumps(sheet_json),
                    context=sheet_json,
                    remarks=comment_json,
                    original_price=request.POST.get("original_price"),
                    special_offer_price=request.POST.get(
                        "special_offer_price"
                    ),
                    vat=request.POST.get("vat"),
                    final_price=request.POST.get("final_price"),
                )
            except PDFError as e:
                # PDF 생성 오류 시에 대한 로직 추가 필요
                print("PDF 생성 오류", e)
                error_msg = "pdf변환 중 오류가 발생하였습니다."
                info = {"quotation": "create"}
                raise QuotationError(error_msg, info=info)
            except ZeroDivisionError as e:
                # 견적 생성 오류 시에 대한 로직 추가 필요
                print("견적서 생성 오류", e)
                # transaction.savepoint_rollback(sid)
                print(e.__dict__)
                error_msg = "견적서 생성중 오류가 발생하였습니다. (" + str(e) + ")"
                info = {"quotation": "create"}
                raise QuotationError(error_msg, info=info)
            except Exception as e:
                # 견적 생성 오류 시에 대한 로직 추가 필요
                print("견적서 생성 오류", e)
                # transaction.savepoint_rollback(sid)
                error_msg = "견적서 생성중 오류가 발생하였습니다.", +str(e)
                info = {"quotation": "create"}
                raise QuotationError(error_msg, info=info)

            make_system_log(
                quotation,
                "솔루션 주문 - 견적관리",
                request.environ["PATH_INFO"],
                request.user,
                "create",
                identifier=quotation.id,
                default_log=default_log,
            )

        return quotation.pk

    def post(self, request, *args, **kwargs):
        """
        order_setting : 주문 공개/비공개, 주문 취소/재개
        order_status : 주문 상태 변경, 담당자 변경
        quotation_form : 견적서 생성, 수정
        """

        if request.POST.get("form_type") == "order_setting":
            return self.change_order_setting(request, *args, **kwargs)

        elif request.POST.get("form_type") == "order_status":
            return self.change_order_status(request, *args, **kwargs)

        elif request.POST.get("form_type") == "quotation_form":
            try:
                quotation_id = self.save_quotation_form(
                    request, *args, **kwargs
                )
                quotation = Quotation.objects.get(pk=quotation_id)
                # update_purchaseorder.delay(purchase_order.id)
                # quotation.make_pdf()
                update_quotation.delay(quotation.id)
                time.sleep(30)
            except Exception as e:
                print(e)
                context = self.get_context_data()
                if hasattr(e, "info"):
                    context.update(e.info)
                return self.render_to_response(context)
            return HttpResponseRedirect(
                reverse_lazy(
                    "myinco_admin-order-detail", kwargs={"id": kwargs["id"]}
                )
                + "?tab=1"
            )  # noqa

        return HttpResponseRedirect(
            reverse_lazy(
                "myinco_admin-order-detail", kwargs={"id": kwargs["id"]}
            )
            + "?tab=0"
        )  # noqa


def quotation_update_modal(request, id):
    quotation_id = request.POST.get("quotation_id")
    quotation = Quotation.objects.get(id=quotation_id)

    order_id = request.POST.get("order_id")
    order = Order.objects.get(id=order_id)

    quotation.context = mark_safe(json.dumps(quotation.context))
    quotation.remarks = mark_safe(json.dumps(quotation.remarks))
    update_quotation_form = QuotationForm(instance=quotation)

    quotations = order.quotation_set.all().order_by("-ctime")

    quotation_form_list = []
    for each in quotations:
        each.context = mark_safe(json.dumps(each.context))
        each.remarks = mark_safe(json.dumps(each.remarks))
        quotation_form_list.append(each)

    context = {
        "quotation_form_list": quotation_form_list,
        "object": order,
        "quotation": quotation,
        "user": request.user,
        "each": update_quotation_form,
    }
    return JsonResponse(
        {
            "data": render_to_string(
                "myinco_admin/order/quotation_update_modal.html", context
            ),
            "status": True,
        }
    )


def PurchaseattachmentAjax(request):
    status = True if request.POST.get("status") == "true" else False
    attachment = request.FILES.get("attachment")
    order_id = request.POST.get("order_id")
    file_name = request.POST.get("file_name")
    file_type = request.POST.get("file_type")
    file_size = request.POST.get("file_size")
    default_log = SystemLog.objects.create(
        page_name="솔루션 주문",
        url=request.environ["PATH_INFO"],
        user=request.user,
        method="update",
        status_code="500",
    )

    order = Order.objects.get(id=order_id)
    before_order = copy.deepcopy(order)
    quotation = Quotation.objects.filter(order=order, is_published=True)

    if len(quotation) == 0:
        return JsonResponse(
            {"data": "공개된 견적서가 없습니다. 먼저 견적서를 공개해주세요."}, status=400
        )
    else:
        quotation = quotation.first()

    if status:
        if PurchaseOrder.objects.filter(order=order).count() > 0:
            return JsonResponse(
                {"data": "이미 등록된 발주서가 존재합니다."}, status=400
            )  # noqa
        else:
            purchase_order = PurchaseOrder.objects.create(
                order=order,
                quotation=quotation,
                pdf_file=attachment,
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
            )

            order.status = "payment-wating"
            order.save()

            if purchase_order:
                extra_content = f"{purchase_order.file_name} 발주서 등록"  # noqa
                etc = [["status", "payment-wating"]]
                make_system_log(
                    before_order,
                    "솔루션 주문",
                    request.environ["PATH_INFO"],
                    request.user,
                    "update",
                    identifier=order.id,
                    etc=etc,
                    default_log=default_log,
                    extra_content=extra_content,
                    extra_url=reverse_lazy(
                        "myinco_admin-order-detail",
                        kwargs={"id": order.id},
                    ),
                )
            ctime = purchase_order.ctime
            data = {
                "file_name": purchase_order.file_name,
                "ctime": f'{ctime.strftime("%Y년 %m월 %d일")}',
                "final_price": str(purchase_order.quotation.final_price),
                "file_url": str(purchase_order.pdf_file.url),
                "order_status": order.status,
                "has_purchase_order": order.has_purchase_order(),
            }
            return JsonResponse({"data": json.dumps(data)}, status=200)
        pass
    else:
        try:
            purchase_order = PurchaseOrder.objects.get(order=order)
        except PurchaseOrder.DoesNotExist:
            purchase_order = None
        if purchase_order:
            extra_content = f"{purchase_order.file_name} 발주서 삭제"  # noqa
            purchase_order.delete()
            order.status = "estimate-re-request"
            order.save()

            etc = [["status", "estimate-re-request"]]
            make_system_log(
                before_order,
                "솔루션 주문",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=order.id,
                etc=etc,
                default_log=default_log,
                extra_content=extra_content,
                extra_url=reverse_lazy(
                    "myinco_admin-order-detail",
                    kwargs={"id": order.id},
                ),
            )

            data = {
                "order_status": order.status,
                "has_purchase_order": order.has_purchase_order(),
            }
            return JsonResponse({"data": json.dumps(data)}, status=200)
        else:
            return JsonResponse({"data": "fail"}, status=200)


def PaymentattachmentAjax(request):
    order_id = request.POST.get("order_id")
    user_id = request.POST.get("user_id")

    order = Order.objects.get(id=order_id)
    before_order = copy.deepcopy(order)
    quotation = Quotation.objects.filter(order=order, is_published=True)

    default_log = SystemLog.objects.create(
        page_name="솔루션 주문",
        url=request.environ["PATH_INFO"],
        user=request.user,
        method="update",
        status_code="500",
    )

    if len(quotation) == 0:
        return JsonResponse({"data": "Quotations is None"}, status=400)
    else:
        quotation = quotation.first()

    payment_method = request.POST.get("payment_method")
    data = {
        "order": order,
        "payment_method": payment_method,
        "tax_manager": quotation.manager,
        "user": User.objects.get(id=user_id),
        "token": myinco_token_generator.make_token(order.identifier),
    }
    if payment_method == "tax":
        request_date = datetime.datetime.strptime(
            request.POST.get("request_date"), "%Y년 %m월 %d일"
        )
        expected_payment_date = datetime.datetime.strptime(
            request.POST.get("expected_payment_date"), "%Y년 %m월 %d일"
        )
        data.update(
            {
                "tax_email": request.POST.get("tax_email"),
                "request_date": request_date,
                "expected_payment_date": expected_payment_date,
                "certificate": request.FILES.get("attachment"),
            }
        )

    elif payment_method == "direct":
        visit_date = datetime.datetime.strptime(
            request.POST.get("visit_date"), "%Y년 %m월 %d일"
        )
        visit_time_from = datetime.datetime.strptime(
            request.POST.get("visit_time_from"), "%p %I:%M"
        )
        visit_time_to = datetime.datetime.strptime(
            request.POST.get("visit_time_to"), "%p %I:%M"
        )
        data.update(
            {
                "visit_date": visit_date,
                "visit_time_from": visit_time_from,
                "visit_time_to": visit_time_to,
                "tax_manager": User.objects.get(
                    id=request.POST.get("visit_manager")
                ),
            }
        )

    elif payment_method == "manager":
        data.update(
            {
                "tax_manager": User.objects.get(
                    id=request.POST.get("consult_manager")
                ),
                "consult_content": request.POST.get("consult_content"),
            }
        )

    payment = Payment.objects.create(**data)
    if payment:
        order.status = "payment-request"
        order.save()
        etc = [["status", "payment-request"]]
        extra_content = (
            f"결제처리({payment.get_payment_method_display()}) 등록"  # noqa
        )
        make_system_log(
            before_order,
            "솔루션 주문",
            request.environ["PATH_INFO"],
            request.user,
            "update",
            identifier=before_order.id,
            etc=etc,
            extra_content=extra_content,
            default_log=default_log,
            extra_url=reverse_lazy(
                "myinco_admin-order-detail",
                kwargs={"id": order.id},
            ),
        )
        if order.purchaser_user:
            target = order.purchaser_user.username
            name = order.purchaser_user.profile.name
        elif order.purchaser_customer:
            target = order.purchaser_customer.email
            name = order.purchaser_customer.name

        content = "결제가 요청되었어요."
        send_auto_email(
            client_info=payment,
            email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
            email_template="myinco_admin/order/payment_email.html",
            to_email=target,
            sub_title=content,
        )
        return JsonResponse({"data": "success"}, status=200)
    else:
        return JsonResponse({"data": "false"}, status=200)

    # status = True if request.POST.get("status") == "true" else False


def PaymentattApplyAjax(request):
    status = True if request.POST.get("status") == "true" else False
    payment_id = request.POST.get("payment_id")
    order_id = request.POST.get("order_id")

    order = Order.objects.get(id=order_id)
    before_order = copy.deepcopy(order)
    payment = Payment.objects.get(id=payment_id)
    active_payments = Payment.objects.filter(order=order, is_payment=True)

    default_log = SystemLog.objects.create(
        page_name="솔루션 주문",
        url=request.environ["PATH_INFO"],
        user=request.user,
        method="update",
        status_code="500",
    )

    if status:
        if active_payments:
            if payment in active_payments:
                return JsonResponse({"data": "이미 발행된 계산서입니다."}, status=400)
            else:
                return JsonResponse({"data": "이미 발행된 계산서가 존재합니다."}, status=400)
        else:
            for each in active_payments:
                each.is_payment = False
                each.save()

            payment.is_payment = True
            payment.tax_status = "completed"
            payment.save()

            order.status = "payment-complete"
            order.save()

            ctime = payment.ctime
            context = {
                "tax_manager_name": payment.tax_manager.profile.name,
                "ctime": f'{ctime.strftime("%Y년 %m월 %d일")}',
                "tax_email": payment.tax_email,
                "payment_id": payment.id,
                "payment_status": payment.get_tax_status_display(),
                "order_status": order.status,
            }
            etc = [["status", "payment-complete"]]
            extra_content = (
                f"결제처리({payment.get_payment_method_display()}) 발행"  # noqa
            )
            make_system_log(
                before_order,
                "솔루션 주문",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=before_order.id,
                etc=etc,
                extra_content=extra_content,
                default_log=default_log,
                extra_url=reverse_lazy(
                    "myinco_admin-order-detail",
                    kwargs={"id": order.id},
                ),
            )

            if order.purchaser_user:
                target = order.purchaser_user.username
                name = order.purchaser_user.profile.name
            elif order.purchaser_customer:
                target = order.purchaser_customer.email
                name = order.purchaser_customer.name

            content = "결제가 완료되었어요."
            send_auto_email(
                client_info=payment,
                email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
                email_template="myinco_admin/order/payment_email.html",
                to_email=target,
                sub_title=content,
            )
            return JsonResponse({"data": json.dumps(context)}, status=200)
    else:
        completes = order.payment_set.filter(is_payment=True)
        flag = True
        if len(completes) > 0:
            for each in completes:
                if each.id == payment.id:
                    flag = False
        if len(completes) == 0:
            return JsonResponse({"data": "발행된 계산서가 없습니다."}, status=400)
        if flag:
            return JsonResponse(
                {"data": "이미 취소되었거나 다른 계산서가 발행되어있습니다."}, status=400
            )

        if payment.is_payment is False and payment.tax_status == "canceled":
            return JsonResponse(
                {"data": "이미 취소되었거나 다른 계산서가 발행되어있습니다."}, status=400
            )
        else:
            payment.is_payment = False
            payment.tax_status = "canceled"
            payment.save()

            order.status = "payment-wating"
            order.save()

            ctime = payment.ctime
            etc = [["status", "payment-wating"]]
            extra_content = (
                f"결제처리({payment.get_payment_method_display()}) 발행취소"  # noqa
            )
            make_system_log(
                before_order,
                "솔루션 주문",
                request.environ["PATH_INFO"],
                request.user,
                "update",
                identifier=before_order.id,
                etc=etc,
                extra_content=extra_content,
                default_log=default_log,
                extra_url=reverse_lazy(
                    "myinco_admin-order-detail",
                    kwargs={"id": order.id},
                ),
            )

            if order.purchaser_user:
                target = order.purchaser_user.username
                name = order.purchaser_user.profile.name
            elif order.purchaser_customer:
                target = order.purchaser_customer.email
                name = order.purchaser_customer.name

            content = "결제가 취소되었어요."
            send_auto_email(
                client_info=payment,
                email_subject=f"[(주)인실리코젠] {name}님, 요청하신 주문의 변경사항 안내 드립니다.",
                email_template="myinco_admin/order/payment_email.html",
                to_email=target,
                sub_title=content,
            )
            context = {
                "tax_manager_name": payment.tax_manager.profile.name,
                "ctime": f'{ctime.strftime("%Y년 %m월 %d일")}',
                "tax_email": payment.tax_email,
                "payment_id": payment.id,
                "payment_status": payment.get_tax_status_display(),
                "order_status": order.status,
            }
            return JsonResponse({"data": json.dumps(context)}, status=200)


def open_order_history_modal(request):
    object_id = request.POST.get("order_id")

    order = Order.objects.get(id=object_id)
    historys = SystemLog.objects.filter(
        model="Order", model_identifier=order.id
    ).order_by("-ctime")

    context = {
        "object": order,
        "user": request.user,
        "historys": historys,
    }

    return JsonResponse(
        {
            "data": render_to_string(
                "myinco_admin/order/history_modal.html", context
            ),
            "status": True,
        }
    )
