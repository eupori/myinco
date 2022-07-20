import pandas as pd
import datetime
from datetime import date, time

from io import BytesIO as IO
from django.http import HttpResponse
from isghome.models import *  # noqa

from django.db import models
from django.contrib.auth.models import User
from django.contrib import auth


def excel_download(request):
    target = request.GET.get("target")

    return make_df(target)


def make_df(target):
    if target == "order":
        col_names = [
            "주문번호",
            "주문구성",
            "주문방식",
            "구매고객",
            "주문상태",
            "결제방식",
            "금액",
            "생성일",
        ]

        rows = [
            (
                order.identifier,
                ", ".join(
                    list(
                        ServicePolicyPriceOption.objects.filter(  # noqa
                            ordercart__order=order
                        ).values_list("product_name", flat=True)
                    )
                ),
                order.get_order_type_display(),
                order.purchaser_customer.name
                + "/"
                + order.purchaser_customer.organization.place_name
                + "/"
                + order.purchaser_customer.get_grade_display()
                if not order.purchaser_user
                else order.purchaser_user.profile.name
                + "/"
                + order.purchaser_user.profile.organization.place_name
                + "/"
                + order.purchaser_user.profile.get_grade_display(),
                order.get_status_display(),
                order.get_payment_method_display(),
                order.total_sales(),
                order.get_ctime(),
            )
            for order in Order.objects.all()  # noqa
        ]
        df = pd.DataFrame(columns=col_names, data=rows)
    elif target == "customer":
        col_names = [
            "고객명",
            "소속정보",
            "이메일",
            "휴대전화",
            "관련영업",
            "연구분야",
            "담당자",
            "총매출",
            "생성일",
        ]

        rows = [
            (
                customer.name,
                customer.organization.place_name
                if customer.organization
                else "",
                customer.email,
                customer.phone_number,
                "",
                ", ".join(
                    [
                        f"{en}({ko})"
                        for ko, en in customer.research_field.all().values_list(  # noqa
                            "ko_name", "en_name"
                        )
                    ]
                ),
                ", ".join(
                    list(
                        customer.manager.all().values_list(
                            "profile__name", flat=True
                        )
                    )
                ),
                customer.total_sales(),
                customer.get_ctime(),
            )
            for customer in Customer.objects.all()  # noqa
        ]
        df = pd.DataFrame(columns=col_names, data=rows)
    elif target == "user":
        col_names = [
            "ID",
            "이름",
            "소속정보",
            "이메일",
            "휴대전화",
            "연구분야",
            "연동여부",
            "총매출",
            "생성일",
        ]

        rows = [
            (
                profile.user.username,
                profile.name,
                profile.organization.place_name
                if profile.organization
                else "",
                profile.user.email,
                profile.phone_number,
                ", ".join(
                    [
                        f"{en}({ko})"
                        for ko, en in profile.research_field.all().values_list(
                            "ko_name", "en_name"
                        )
                    ]
                ),
                "O" if profile.user.synced_user.first() is not None else "X",
                profile.total_sales(),
                profile.get_ctime(),
            )
            for profile in UserProfile.objects.all()  # noqa
        ]
        df = pd.DataFrame(columns=col_names, data=rows)
    elif target == "organization":
        col_names = [
            "고객사명",
            "주소",
            "상세주소",
            "소속고객",
            "매니저",
            "총매출",
            "생성일",
        ]

        rows = [
            (
                organization.place_name,
                organization.address,
                organization.address_detail,
                str(organization.customer_set.all().count()) + "명",
                ", ".join(
                    list(
                        organization.manager.all().values_list(
                            "profile__name", flat=True
                        )
                    )
                ),
                organization.total_sales(),
                organization.get_ctime(),
            )
            for organization in Organization.objects.all()  # noqa
        ]
        df = pd.DataFrame(columns=col_names, data=rows)
    elif target == "auth_group":
        col_names = [
            "그룹명",
            "설명",
            "소속 사용자",
            "소속 인원수",
            "소속 그룹",
            "소속 그룹수",
            "소유자",
            "공개여부",
            "생성일",
        ]

        rows = [
            (
                auth_group.name,
                auth_group.description,
                ", ".join(
                    list(
                        auth_group.members.all().values_list(
                            "profile__name", flat=True
                        )
                    )
                ),
                str(auth_group.members.all().count()) + "명",
                ", ".join(
                    list(
                        auth_group.target_group.all().values_list(
                            "group_member__name", flat=True
                        )
                    )
                ),
                str(auth_group.target_group.all().count()) + "개",
                auth_group.owner.profile.name,
                auth_group.get_publish_display(),
                auth_group.get_ctime(),
            )
            for auth_group in AuthGroup.objects.all()  # noqa
        ]
        df = pd.DataFrame(columns=col_names, data=rows)
    elif target == "system_log":
        col_names = [
            "로그 일시",
            "계정 아이디",
            "이름",
            "페이지명",
            "URL",
            "로그내용",
            "처리구분",
        ]

        rows = [
            (
                system_log.get_ctime(),
                system_log.user.username,
                system_log.user.profile.name,
                system_log.page_name,
                system_log.url,
                system_log.display_diff(),
                system_log.status_code,
            )
            for system_log in SystemLog.objects.all()  # noqa
        ]
        df = pd.DataFrame(columns=col_names, data=rows)

    return make_excel(df, target)


def make_excel(df, target):
    now = datetime.now()
    now_str = datetime.strftime(now, "%Y-%m-%d")
    response = HttpResponse(content_type="application/vnd.ms-excel")
    response[
        "Content-Disposition"
    ] = f"attachment; filename={target}-{now_str}.xlsx"

    excel_file = IO()

    xlwriter = pd.ExcelWriter(excel_file, engine="xlsxwriter")

    df.to_excel(xlwriter, target)

    xlwriter.save()
    xlwriter.close()
    excel_file.seek(0)

    response.write(excel_file.read())

    return response


""" 로그 기록 함수
* 필요한 곳에 아래 코드를 삽입 후 관련 모델 넣기
* etc : 변경된 필드 ex>[ "id", "ctime", "is_active" ... ]
* make_system_log : 로그 기록 함수 호출 (model_object, 기록자, 처리(생성, 수정, 삭제), 변경필드)

etc = list(data_dict.items())
make_system_log(
    quotation.first(),
    quotation.first().id,
    "솔루션 주문 - 견적관리",
    request.environ["PATH_INFO"],
    request.user,
    "update",
    etc=etc,
)
"""


# 로그 기록 제외 필드
exclude_dict = {"Quotation": ["context", "remarks"]}


def make_system_log(
    model_object,
    page_name,
    url,
    user,
    method,
    form=None,
    etc=None,
    identifier=None,
    is_created=True,
    extra_content=None,
    status_code="200",
    default_log=None,
    extra_url=None,
):
    if not extra_content:
        if method == "create":
            extra_content = f"{page_name} 생성 실패"
        if method == "update":
            extra_content = f"{page_name} 수정 실패"
        if method == "delete":
            extra_content = f"{page_name} 삭제 실패"

    if method == "delete":
        print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
        print(model_object)
        print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
        if model_object:
            model_name = model_object._meta.model.__name__
            SystemLog(  # noqa
                id=default_log.id,
                model=model_name,
                model_identifier=identifier,
                page_name=page_name,
                url=url,
                method=method,
                user=user,
                extra_content=extra_content,
                status_code=status_code,
            ).save_with_url(extra_url)
        else:
            SystemLog(  # noqa
                id=default_log.id,
                page_name=page_name,
                url=url,
                method=method,
                user=user,
                extra_content=extra_content,
                status_code=status_code,
            ).save_with_url(extra_url)

    elif method == "update":
        model_name = model_object._meta.model.__name__
        changed_dict = ""
        # form도 있는 경우
        if form and etc:
            etc += [[key, form.cleaned_data[key]] for key in form.changed_data]
        # form을 사용했을 경우
        elif form and not etc:
            etc = [[key, form.cleaned_data[key]] for key in form.changed_data]
        changed_dict = {}
        for key, value in etc:
            # 로그 기록 제외 필드 건너뛰기
            if model_name in exclude_dict and key in exclude_dict[model_name]:
                continue
            try:
                # 변경된 필드값이 many to many field일 경우
                if isinstance(
                    getattr(model_object, key).all(), models.query.QuerySet
                ):
                    if isinstance(
                        getattr(model_object, key).first(), auth.models.User
                    ):
                        before = [
                            item.profile.name
                            for item in getattr(model_object, key).all()
                        ]
                        print(before)
                    elif isinstance(
                        getattr(model_object, key).first(), AuthGroup  # noqa
                    ):
                        before = [
                            item.name
                            for item in getattr(model_object, key).all()
                        ]
                        print(before)
                    else:
                        before = [
                            item.__str__()
                            for item in getattr(model_object, key).all()
                        ]

                    model = getattr(model_object, key).__dict__["model"]
                    if model == User:
                        value = [
                            item.profile.name
                            for item in model.objects.filter(id__in=value)
                        ]
                    elif model == AuthGroup:  # noqa
                        value = [
                            item.name
                            for item in model.objects.filter(id__in=value)
                        ]
                    else:
                        value = [
                            item.__str__()
                            for item in model.objects.filter(id__in=value)
                        ]

            except Exception as e:
                # 변경된 필드값의 타입이 Datetime, Date일 경우
                if (
                    isinstance(getattr(model_object, key), datetime)
                    or isinstance(getattr(model_object, key), date)
                    or isinstance(getattr(model_object, key), time)
                ):
                    before = str(getattr(model_object, key))
                    value = str(value)
                # 변경된 필드가 ForeignKey일 경우
                elif isinstance(getattr(model_object, key), models.Model):
                    before = getattr(model_object, key).__str__()
                    model = getattr(model_object, key)._meta.model
                    if isinstance(value, models.Model):
                        value = value.__str__()
                    else:
                        value = model.objects.get(id=value).__str__()
                # 그 외 경우
                else:
                    before = getattr(model_object, key)
            if before != value:
                changed_dict[key] = {
                    "before": before,
                    "value": value,
                }

        if changed_dict:
            system_log = SystemLog(  # noqa
                id=default_log.id,
                model=model_name,
                model_identifier=identifier,
                page_name=page_name,
                url=url,
                diff=changed_dict,
                method=method,
                user=user,
                extra_content=extra_content,
                status_code=status_code,
            )
            if is_created:
                system_log.save_with_url(extra_url)
            else:
                return system_log

    elif method == "create":
        model_name = model_object._meta.model.__name__
        changed_dict = ""
        SystemLog(  # noqa
            id=default_log.id,
            model=model_name,
            model_identifier=identifier,
            page_name=page_name,
            url=url,
            method=method,
            user=user,
            extra_content=extra_content,
            status_code=status_code,
        ).save_with_url(extra_url)


# model_object,
# page_name,
# url,
# user,
# method,
# form=None,
# etc=None,
# identifier=None,
