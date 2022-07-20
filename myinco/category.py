import json
import pandas as pd
import numpy as np

from django import forms
from django.db import transaction
from django.views.generic import (
    ListView,
    DetailView,
    View,
    CreateView,
    UpdateView,
    FormView,
)

from django.http import JsonResponse

from isghome.models import (
    Product,
    ProductCategory,
    ServicePolicy,
    ServicePolicyGroupCode,
    ServicePolicyCode,
    ServicePolicyPriceOption,
)
# from isghome.views import URLArgument
from isghome.utils import MyIncoCodeValidator


"""
콘텐츠 설명 규칙
* 아래 규칙으로 일괄 처리 가능
* 참고용 규칙: {서비스명},", ",{라이선스 타입},", ",{사용자수},", ",{라이선스 기간}," for ",{라이선스 정책}

코드 생성 규칙
* 아래 규칙으로 일괄 처리 가능
* 참고용 규칙: {대표 코드},"-",{라이선스 정책},{라이선스 타입},{사용자수},"-",{라이선스 기간},"-",{버전}
* 위 {중괄호} 내부에서 따오는 기준:
  * 데이터 중 대문자 따올 것
  * 데이터 중 숫자 따올 것
  * 데이터 중 공백 있을 시 제거할 것
  * 버전은 뒤의 두 자리만 적용

예시 데이터
* 예시 콘텐츠 설명: HGMD Online, Clinical use, 10Users, 1Year for Academic
* 예시 생성코드: ISG-BBHO-AC10U-1Y-21.1
* 콘텐츠 설명 예시2
  * IPA 100 datasets with Analysis Match / ISG-IGMD / Government / Limited Named User License / 1User / 1Year / v21.1
  * {서비스명}, {라이선스 타입}, {사용자수}, {라이선스 기간} for {라이선스 정책}
  * IPA 100 datasets with Analysis Match, Limited Named User License, 1User, 1Year for Government
* 코드 생성 예시2
  * =E36&"-"&LEFT(F36,1)&LEFT(G36,1)&LEFT(H36,2)&"-"&SUBSTITUTE(LEFT(I36,2)," ","")&"-"&SUBSTITUTE(K36,"v","")
  * IPA 100 datasets with Analysis Match / ISG-IGMD / Government / Limited Named User License / 1User / 1Year / v21.1
  * {대표코드}-{라이선스 정책}{라이선스 타입}{사용자수}-{라이선스 기간 }-{버전}
  * ISG-IGMD-GL1U-1Y-21.1

규칙에 사용 가능한 변수
* 서비스명: 제품명을 말함. ex) CLC Genomics Workbench
* 대표코드: 제픔/서비스 등록 시 등록한 코드 ex) ISG-CBGW
* 버전: 해당 정책의 버전 ex) v21.1
* 이 외에는 정책에 등록한 옵션 명을 사용할 수 있음


규칙에 사용 가능한 문법
 * {변수} :
>>> import re
>>> query = '{product_name}, {라이센스 타입}, {사용자수}, {라이센스 기간}, for {라이센스 정책}'
>>> re.findall('\{[\w\s:]+\}', query)
['{product_name}', '{라이센스 타입}', '{사용자수}', '{라이센스 기간}', '{라이센스 정책}']
"""


class MyincoAdminCategoryListView(ListView):
    template_name = "myinco_admin/category/list.html"
    model = ProductCategory

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(category_type="main")
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["main_categories"] = ProductCategory.objects.filter(
            category_type="main"
        )
        return context


class MyincoAdminCategoryDetailView(DetailView):
    template_name = "myinco_admin/category/detail.html"
    model = ProductCategory


class ProductCategoryCreateForm(forms.Form):
    main_category = forms.ModelChoiceField(
        queryset=ProductCategory.objects.filter(category_type="main"),
    )
    category_name = forms.CharField()

    def clean_category_name(self):
        category_name = self.cleaned_data.get("category_name")
        category_name = category_name.strip()
        if not category_name:
            raise forms.ValidationError("카테고리 이름을 입력해주세요.")
        if ProductCategory.objects.filter(name=category_name).count() > 0:
            raise forms.ValidationError("동일한 제품군명이 존재합니다.")
        return category_name


class MyincoAdminCategoryCreateView(FormView):
    template_name = "myinco_admin/category/create.html"
    model = ProductCategory
    form_class = ProductCategoryCreateForm

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        main_category = data.get("main_category")
        category_name = data.get("category_name")
        try:
            ProductCategory.objects.create(
                parent=main_category, category_type="sub", name=category_name
            )
        except Exception as e:
            print("ProductCategory.objects.create Error!", e)
            return JsonResponse(
                {"is_success": False, "message": "알 수 없는 에러 발생!!"}
            )
        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class ProductCategoryChangeForm(forms.Form):
    sub_category = forms.ModelChoiceField(
        queryset=ProductCategory.objects.filter(category_type="sub"),
    )
    category_name_before = forms.CharField()
    category_name_after = forms.CharField()

    def clean_category_name_after(self):
        cna = self.cleaned_data.get("category_name_after")
        cna = cna.strip()
        if not cna:
            raise forms.ValidationError("카테고리 이름을 입력해주세요.")
        if ProductCategory.objects.filter(name=cna).count() > 0:
            raise forms.ValidationError("동일한 제품군명이 존재합니다.")
        return cna


class MyincoAdminCategoryChangeView(FormView):
    template_name = "myinco_admin/category/change.html"
    model = ProductCategory
    form_class = ProductCategoryChangeForm

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        sub_category = data.get("sub_category")
        category_name_after = data.get("category_name_after")
        try:
            sub_category.name = category_name_after
            sub_category.save()
        except Exception as e:
            print("ProductCategory.objects.update Error!", e)
            return JsonResponse(
                {"is_success": False, "message": "알 수 없는 에러 발생!!"}
            )
        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class ProductCategoryDeleteForm(forms.Form):
    sub_category = forms.ModelChoiceField(
        queryset=ProductCategory.objects.filter(category_type="sub"),
    )


class MyincoAdminCategoryDeleteView(FormView):
    template_name = "myinco_admin/category/delete.html"
    model = ProductCategory
    form_class = ProductCategoryDeleteForm

    def is_can_delete(self, sub_category):
        if ServicePolicy.objects.filter(category=sub_category).count() > 0:
            return False
        if Product.objects.filter(category=sub_category).count() > 0:
            return False
        return True

    def form_valid(self, form):
        data = form.cleaned_data
        sub_category = data.get("sub_category")
        if self.is_can_delete(sub_category):
            sub_category.delete()
        else:
            print("ProductCategory.objects.delete Error!")
            return JsonResponse(
                {"is_success": False, "message": "알 수 없는 에러 발생!!"}
            )
        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class MyincoAdminServicePolicyDetailView(DetailView):
    model = ServicePolicy

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        data = self.get_data()
        # context = self.get_context_data(object=self.object)
        return JsonResponse({"data": data, "is_success": True})

    def get_data(self):
        data = {
            "id": self.object.id,
            "main_category": self.object.category.parent.name,
            "sub_category": self.object.category.name,
            "desc_rule": self.object.desc_rule,
            "code_rule": self.object.code_rule,
            "version": self.object.version,
            "is_promotion": self.object.is_promotion_p,
            "is_active": self.object.is_active_p,
            "is_active_homepage": self.object.is_active_homepage_p,
            "desc_rule": self.object.desc_rule,
            "code_rule": self.object.code_rule,
            "ctime": f'{self.object.ctime.strftime("%Y년 %m월 %d일")}·생성됨',
        }
        options = []
        for group_code in self.object.servicepolicygroupcode_set.all():
            text = ";".join(
                [code.name for code in group_code.servicepolicycode_set.all()]
            )  # noqa
            option = {
                "id": group_code.id,
                "name": group_code.name,
                "text": text,
                "is_required": group_code.is_required,
            }
            options.append(option)
        data["options"] = options
        return data


class MyincoAdminServicePolicyOptionInfoView(DetailView):
    model = ServicePolicy

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        data = self.get_data()
        # context = self.get_context_data(object=self.object)
        print('data:', data)
        return JsonResponse({
                "data": data,
                "is_success": True})

    def get_data(self):
        data = {
            "id": self.object.id,
            "version": self.object.version,
            "is_promotion": self.object.is_promotion_p,
            "is_active": self.object.is_active_p,
            "is_active_homepage": self.object.is_active_homepage_p,
            "desc_rule": self.object.desc_rule,
            "code_rule": self.object.code_rule,
            "ctime": f'{self.object.ctime.strftime("%Y년 %m월 %d일")}·생성됨',
        }

        option_set = self.object.servicepolicypriceoption_set.all()
        product_id = self.request.GET.get("product")
        if product_id:
            product = Product.objects.get(id=product_id)
            option_set = option_set.filter(product=product)

        options = [
            # ["연번", "생성 코드", "서비스 설명", "즉시 구매", "단가(₩)"],
        ]
        meta = {}
        for i, po in enumerate(option_set):
            no = str(i+1)
            service_code = po.get_service_code()
            service_description = po.get_service_description()
            price = po.price
            options.append([
                no, service_code, service_description,
                po.is_buy_now, price])
            meta[f'A{i+1}'] = {'pk': po.pk}

        data["data"] = options
        data["meta"] = meta
        # data["code"] = code_dict
        # data["info"] = info_dict
        return data


class MyincoAdminServicePolicyBatchTestView(View):
    sp_header = ["연번", "제품군", "생성 코드", "서비스 설명", "단가(₩)"]

    def post(self, request, *args, **kwargs):
        is_success = False
        sub_category_id = request.POST.get("sub_category")
        try:
            ProductCategory.objects.get(id=sub_category_id)
        except Exception as e:
            print("Error:", e)
            return JsonResponse({"is_success": is_success})
        upload_file = request.FILES.get("file")
        data, errors, meta, count_dict = self.get_verified_data(upload_file)
        is_success = True
        return JsonResponse(
            {
                "is_success": is_success,
                "data": data,
                "errors": errors,
                "meta": meta,
                "count_dict": count_dict,
            }
        )

    def get_verified_data(self, upload_file):
        data, errors = [], []
        meta, code_dict, info_dict = {}, {}, {}

        rule_df = pd.read_excel(
                upload_file, sheet_name="system-rule",
                header=None, index_col=0).transpose()
        rule_df = rule_df.replace(np.nan, "")
        desc_rule = rule_df["콘텐츠 설명 규칙"][1]
        code_rule = rule_df["코드 생성 규칙"][1]
        df = pd.read_excel(upload_file, sheet_name="version")
        df = df.replace(np.nan, "")
        columns = list(df.columns)
        start = columns.index("대표코드")
        end = columns.index("단가")
        groupcode_index = df.columns[start + 1 : end]  # noqa
        for i, gc_name in enumerate(groupcode_index):
            values = list(df[gc_name].drop_duplicates().values)
            code_dict[gc_name] = values

        vc_normal = 0
        vc_error = 0
        vc_all = 0
        for i, row in df.iterrows():
            is_valid = True
            no = row["번호"]
            no = str(no)
            # category = row['제품군']
            service_code = row["서비스 코드(함수적용)"]
            # service_code = row["서비스 코드(함수적용)"].strip()
            product_name = row["서비스명"].strip()
            print(product_name)
            try:
                Product.objects.get(product_name=product_name)
            except Product.DoesNotExist:
                print('Product.DoesNotExist!!', product_name)
                errors.append(f"B{i+1}")
                meta[f"B{i+1}"] = {"is_valid": False}
                is_valid = False
            # representative_code = row['대표 코드']
            price = row["단가"]
            # version = row['버전']
            service_description = row["콘텐츠 설명"].strip()
            if product_name not in service_description:
                errors.append(f"D{i+1}")
                meta[f"D{i+1}"] = {"is_valid": False}
                is_valid = False
            for gc_name in groupcode_index:
                keyword = row[gc_name]
                print('keyword:', keyword, '||')
                if no in info_dict:
                    info_dict[no].update({gc_name: keyword})
                else:
                    info_dict[no] = {gc_name: keyword}
                if keyword and keyword not in service_description:
                    meta[f"D{i+1}"] = {"is_valid": False}
                    is_valid = False
            data.append(
                [no, product_name, service_code, service_description, price]
            )
            if is_valid:
                vc_normal += 1
            else:
                vc_error += 1
            vc_all += 1
        count_dict = {
            "vc_all": vc_all,
            "vc_normal": vc_normal,
            "vc_error": vc_error,
        }
        # data.insert(0, self.sp_header)
        meta["CODE"] = code_dict
        meta["INFO"] = info_dict
        meta["RULE"] = {
            'desc_rule': desc_rule,
            'code_rule': code_rule,
        }
        return data, errors, meta, count_dict


class MyincoAdminServicePolicyBatchVerifyView(View):
    def post(self, request, *args, **kwargs):
        data = request.POST.get("data")
        data = json.loads(data)
        meta = request.POST.get("meta")
        meta = json.loads(meta)
        code_dict = meta.get("CODE", {})
        info_dict = meta.get("INFO", {})
        rule_dict = meta.get("RULE", {})
        errors = []
        meta = {}

        vc_normal = 0
        vc_error = 0
        vc_all = 0
        for i, record in enumerate(data):
            is_valid = True
            no, product_name, service_code, service_description, price = record
            if no == "연번":
                continue
            try:
                Product.objects.get(product_name=product_name)
            except Product.DoesNotExist:
                print('Product.DoesNotExist', product_name)
                errors.append(f"B{i+1}")
                meta[f"B{i+1}"] = {"is_valid": False}
            if product_name not in service_description:
                errors.append(f"D{i+1}")
                meta[f"D{i+1}"] = {"is_valid": False}
            # code validation ??
            if is_valid:
                vc_normal += 1
            else:
                vc_error += 1
            vc_all += 1
        meta["CODE"] = code_dict
        meta["INFO"] = info_dict
        meta["RULE"] = rule_dict
        count_dict = {
            "vc_all": vc_all,
            "vc_normal": vc_normal,
            "vc_error": vc_error,
        }
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
                "errors": errors,
                "meta": meta,
                "count_dict": count_dict,
            }
        )


class MyincoAdminServicePolicyEachVerifyView(View):
    def post(self, request, *args, **kwargs):
        data = request.POST.get("data")
        data = json.loads(data)
        meta = request.POST.get("meta")
        meta = json.loads(meta)
        # code_dict = meta.get("CODE", {})
        # info_dict = meta.get("INFO", {})
        errors = []
        meta = {}

        vc_normal = 0
        vc_error = 0
        vc_all = 0
        for i, record in enumerate(data):
            is_valid = True
            no, product_name, service_code, service_description, price = record
            if no == "연번":
                continue
            try:
                Product.objects.get(product_name=product_name)
            except Product.DoesNotExist:
                errors.append(f"B{i+1}")
                meta[f"B{i+1}"] = {"is_valid": False}
            if product_name not in service_description:
                errors.append(f"D{i+1}")
                meta[f"D{i+1}"] = {"is_valid": False}
            if is_valid:
                vc_normal += 1
            else:
                vc_error += 1
            vc_all += 1
        # meta["CODE"] = code_dict
        # meta["INFO"] = info_dict
        count_dict = {
            "vc_all": vc_all,
            "vc_normal": vc_normal,
            "vc_error": vc_error,
        }
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
                "errors": errors,
                "meta": meta,
                "count_dict": count_dict,
            }
        )


class MyincoAdminServicePolicyServiceVerifyView(View):
    policy = None
    product = None

    def get_data(self, request):
        # code_dict = meta.get("CODE", {})
        # info_dict = meta.get("INFO", {})
        data = request.POST.get("data")
        data = json.loads(data)
        meta = request.POST.get("meta")
        meta = json.loads(meta)
        policy_id = request.POST.get("policy_id")
        product_id = request.POST.get('product_id')
        if policy_id:
            self.policy = ServicePolicy.objects.get(id=policy_id)
        if product_id:
            self.product = Product.objects.get(id=product_id)
        return data, meta

    def check_rule_value(self, syntax, text):
        print('syntax:', syntax)
        print('input text:', text)
        return True

    def post(self, request, *args, **kwargs):
        print('request.POST:', request.POST)
        data, meta = self.get_data(request)
        product_name = self.product.product_name

        errors = []
        meta = {}

        vc_normal = 0
        vc_error = 0
        vc_all = 0
        validator = MyIncoCodeValidator()
        candidates = validator.get_available_code_set(
                                    self.policy, self.product)
        for i, record in enumerate(data):
            is_valid = True
            no, service_code, service_description, is_buy_now, price = record
            if no == "연번":
                continue
            if not price or not service_description or not service_code:
                continue
            if product_name not in service_description:
                errors.append(f"C{i+1}")
                meta[f"C{i+1}"] = {"is_valid": False}
                is_valid = False

            if service_code in candidates:
                if candidates.get(service_code) != service_description:
                    print('==============')
                    print(candidates.get(service_code))
                    print(service_description)
                    errors.append(f"C{i+1}")
                    meta[f"C{i+1}"] = {"is_valid": False, "error_msg": "desc error"}
                    is_valid = False
            else:
                errors.append(f"B{i+1}")
                meta[f"B{i+1}"] = {"is_valid": False, "error_msg": "code error"}
                is_valid = False
            if is_valid:
                vc_normal += 1
            else:
                vc_error += 1
            vc_all += 1
        # meta["CODE"] = code_dict
        # meta["INFO"] = info_dict
        count_dict = {
            "vc_all": vc_all,
            "vc_normal": vc_normal,
            "vc_error": vc_error,
        }
        print('errors:', errors)
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
                "errors": errors,
                "meta": meta,
                "count_dict": count_dict,
            }
        )


class ServicePolicyBatchCreateForm(forms.ModelForm):
    TRUE_FALSE_CHOICES = (
        ("true", "True"),
        ("false", "False"),
    )
    data = forms.CharField(max_length=5000)
    meta = forms.CharField(max_length=5000)
    is_promotion = forms.ChoiceField(
        required=False,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )
    is_active = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="true",
    )
    is_active_homepage = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )

    field_order = [
        "category",
        "version",
        "is_promotion",
        "is_active",
        "is_active_homepage",
        "data",
        "meta",
    ]

    def clean_category(self):
        category = self.cleaned_data["category"]
        if not category.parent:
            raise forms.ValidationError("카테고리 정보가 잘못되었습니다.")
        return category

    def clean_version(self):
        version = self.cleaned_data["version"]
        if not version:
            raise forms.ValidationError("")
        category = self.cleaned_data["category"]
        if (
            ServicePolicy.objects.filter(
                version=version, category=category
            ).count()
            > 0
        ):
            raise forms.ValidationError("중복된 이름의 버전이 존재합니다.")
        return version

    def clean_is_promotion(self):
        is_promotion = self.cleaned_data["is_promotion"]
        if is_promotion == "true":
            is_promotion = True
        else:
            is_promotion = False
        return is_promotion

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if is_active == "false":
            is_active = False
        else:
            is_active = True
        return is_active

    def clean_is_active_homepage(self):
        is_active_homepage = self.cleaned_data["is_active_homepage"]
        if is_active_homepage == "true":
            is_active_homepage = True
        else:
            is_active_homepage = False
        return is_active_homepage

    def clean_data(self):
        data = self.cleaned_data["data"]
        data = json.loads(data)
        return data

    def clean_meta(self):
        meta = self.cleaned_data["meta"]
        meta = json.loads(meta)
        return meta

    class Meta:
        model = ServicePolicy
        fields = [
            "category",
            "is_promotion",
            "is_active",
            "is_active_homepage",
            "version",
        ]


class MyincoAdminServicePolicyBatchCreateView(CreateView):
    model = ServicePolicy
    form_class = ServicePolicyBatchCreateForm
    template_name = "myinco_admin/category/policy_create.html"

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        # print('request.POST:', request.POST)
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        print("data!!:", form.cleaned_data)
        self.object = form.save()
        if self.object.is_active_homepage is True:
            ServicePolicy.objects.filter(
                category=self.object.category,
            ).update(is_active_homepage=False)
            self.object.is_active_homepage = True
            self.object.save()
        data = form.cleaned_data
        code_dict = data["meta"]["CODE"]
        info_dict = data["meta"]["INFO"]
        rule_dict = data["meta"]["RULE"]
        self.object.desc_rule = rule_dict["desc_rule"]
        self.object.code_rule = rule_dict["code_rule"]
        self.object.save()
        for i, gc_name in enumerate(code_dict):
            values = code_dict[gc_name]
            group_code = ServicePolicyGroupCode.objects.create(
                policy=self.object,
                name=gc_name,
                display_order=i + 1,
            )
            for i, value in enumerate(values):
                code = ServicePolicyCode.objects.create(
                    group_code=group_code,
                    name=value,
                    display_order=i + 1,
                )
        for record in data["data"]:
            no = record[0]
            if no == "연번":
                continue
            product_name = record[1]
            service_code = record[2]
            service_description = record[3]
            price = record[4]
            if not product_name:
                continue
            product = Product.objects.get(product_name=product_name)
            price_option = ServicePolicyPriceOption.objects.create(
                policy=self.object,
                product=product,
                product_name=product_name,
                service_code=service_code,
                service_description=service_description,
                price=price,
            )
            for gc_name, code_name in info_dict[no].items():
                group_code = ServicePolicyGroupCode.objects.get(
                    policy=self.object, name=gc_name
                )
                code = ServicePolicyCode.objects.get(
                    group_code=group_code, name=code_name
                )
                price_option.options.add(code)
        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class ServicePolicyEachCreateForm(forms.ModelForm):
    TRUE_FALSE_CHOICES = (
        ("true", "True"),
        ("false", "False"),
    )
    """
    desc_rule = forms.CharField(
        max_length=500,
        required=False,
    )
    code_rule = forms.CharField(
        max_length=500,
        required=False
    )
    """
    """
    group_name = forms.CharField(
        max_length=1000,
        required=False,
    )
    options = forms.CharField(
        max_length=2000,
        required=False,
    )
    """
    code_options = forms.CharField(
        max_length=5000,
        required=True,
    )
    is_promotion = forms.ChoiceField(
        required=False,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )
    is_active = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="true",
    )
    is_active_homepage = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )

    field_order = [
        "category",
        "version",
        "is_promotion",
        "is_active",
        "is_active_homepage",
        "desc_rule",
        "code_rule",
        # "group_name",
        # "options",
        'code_options',
    ]

    def clean_category(self):
        category = self.cleaned_data["category"]
        if not category.parent:
            raise forms.ValidationError("카테고리 정보가 잘못되었습니다.")
        return category

    def clean_version(self):
        version = self.cleaned_data["version"]
        if not version:
            raise forms.ValidationError("")
        category = self.cleaned_data["category"]
        if (
            ServicePolicy.objects.filter(
                version=version, category=category
            ).count()
            > 0
        ):
            raise forms.ValidationError("중복된 이름의 버전이 존재합니다.")
        return version

    def clean_is_promotion(self):
        is_promotion = self.cleaned_data["is_promotion"]
        if is_promotion == "true":
            is_promotion = True
        else:
            is_promotion = False
        return is_promotion

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if is_active == "false":
            is_active = False
        else:
            is_active = True
        return is_active

    def clean_is_active_homepage(self):
        is_active_homepage = self.cleaned_data["is_active_homepage"]
        if is_active_homepage == "true":
            is_active_homepage = True
        else:
            is_active_homepage = False
        return is_active_homepage

    def check_rule_syntax(self, rule):
        isValid = True
        # {, } 카운트 체크
        # 열었으면 닫아야 한다 체크
        if rule.count('{') != rule.count('}'):
            isValid = False
        else:
            is_opened = False
            count = 0
            for char in rule:
                print(is_opened, count)
                if char == '{':
                    if is_opened:
                        isValid = False
                        break
                    is_opened = True
                elif char == '}':
                    if not is_opened:
                        isValid = False
                        break
                    if count == 0:
                        isValid = False
                        break
                    is_opened = False
                    count = 0
                elif is_opened is True:
                    count += 1
        return isValid

    def clean_desc_rule(self):
        desc_rule = self.cleaned_data["desc_rule"]
        if desc_rule:
            isValid = self.check_rule_syntax(desc_rule)
            if not isValid:
                raise forms.ValidationError(
                    "콘텐츠 설명 규칙의 형식이 잘못되었습니다.")
        return desc_rule

    def clean_code_rule(self):
        code_rule = self.cleaned_data["code_rule"]
        if code_rule:
            isValid = self.check_rule_syntax(code_rule)
            if not isValid:
                raise forms.ValidationError(
                    "코드 생성 규칙의 형식이 잘못되었습니다.")
        return code_rule

    """
    def clean_group_name(self):
        group_name = self.cleaned_data["group_name"]
        return group_name

    def clean_options(self):
        options = self.cleaned_data["options"]
        return options
    """

    def clean_code_options(self):
        code_options = self.cleaned_data["code_options"]
        if code_options:
            code_options = json.loads(code_options)
        return code_options

    class Meta:
        model = ServicePolicy
        fields = [
            "category",
            "is_promotion",
            "is_active",
            "is_active_homepage",
            "version",
            "desc_rule",
            "code_rule",
        ]


class MyincoAdminServicePolicyEachCreateView(CreateView):
    model = ServicePolicy
    form_class = ServicePolicyEachCreateForm
    template_name = "myinco_admin/category/policy_create.html"

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        print('request.POST:', request.POST)
        form = self.get_form()
        if form.is_valid():
            print(' == form is_valid')
            return self.form_valid(form)
        else:
            print(' == form is_invalid!!!!!!!!!!')
            return self.form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        print("data!!:", form.cleaned_data)
        self.object = form.save()
        if self.object.is_active_homepage is True:
            ServicePolicy.objects.filter(
                category=self.object.category,
            ).update(is_active_homepage=False)
            self.object.is_active_homepage = True
            self.object.save()
        data = form.cleaned_data

        for i, options in enumerate(data['code_options']):
            print(options)
            gc_name = options["option_name"]
            group_code = ServicePolicyGroupCode.objects.create(
                policy=self.object,
                name=gc_name,
                display_order=i + 1,
            )
            for i, value in enumerate(options["option_value"].split(';')):
                value = value.strip()
                code = ServicePolicyCode.objects.create(
                    group_code=group_code,
                    name=value,
                    display_order=i + 1,
                )
        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class ServicePolicyUpdateForm(forms.ModelForm):
    TRUE_FALSE_CHOICES = (
        ("true", "True"),
        ("false", "False"),
    )
    is_promotion = forms.ChoiceField(
        required=False,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )
    is_active = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="true",
    )
    is_active_homepage = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )

    field_order = ["is_promotion", "is_active", "is_active_homepage"]

    def clean_is_promotion(self):
        is_promotion = self.cleaned_data["is_promotion"]
        if is_promotion == "true":
            is_promotion = True
        else:
            is_promotion = False
        return is_promotion

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if is_active == "false":
            is_active = False
        else:
            is_active = True
        return is_active

    def clean_is_active_homepage(self):
        is_active_homepage = self.cleaned_data["is_active_homepage"]
        if is_active_homepage == "true":
            is_active_homepage = True
        else:
            is_active_homepage = False
        return is_active_homepage

    class Meta:
        model = ServicePolicy
        fields = ["is_promotion", "is_active", "is_active_homepage"]


class MyincoAdminServicePolicyUpdateView(UpdateView):
    model = ServicePolicy
    form_class = ServicePolicyUpdateForm
    template_name = ""

    @transaction.atomic
    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        print("data!!:", form.cleaned_data)
        """How to know ? value changed..."""
        self.object = form.save()
        if self.object.is_active_homepage is True:
            ServicePolicy.objects.filter(
                category=self.object.category,
            ).update(is_active_homepage=False)
            self.object.is_active_homepage = True
            self.object.save()
        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class ServicePolicyServiceUpdateForm(forms.ModelForm):
    TRUE_FALSE_CHOICES = (
        ("true", "True"),
        ("false", "False"),
    )
    data = forms.CharField(max_length=5000)
    meta = forms.CharField(max_length=5000)
    is_promotion = forms.ChoiceField(
        required=False,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )
    is_active = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="true",
    )
    is_active_homepage = forms.ChoiceField(
        required=True,
        choices=TRUE_FALSE_CHOICES,
        initial="false",
    )

    field_order = [
        "is_promotion",
        "is_active",
        "is_active_homepage",
        'data',
        'meta',
    ]

    def clean_is_promotion(self):
        is_promotion = self.cleaned_data["is_promotion"]
        if is_promotion == "true":
            is_promotion = True
        else:
            is_promotion = False
        return is_promotion

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if is_active == "false":
            is_active = False
        else:
            is_active = True
        return is_active

    def clean_is_active_homepage(self):
        is_active_homepage = self.cleaned_data["is_active_homepage"]
        if is_active_homepage == "true":
            is_active_homepage = True
        else:
            is_active_homepage = False
        return is_active_homepage

    def check_rule_syntax(self, rule):
        isValid = True
        # {, } 카운트 체크
        # 열었으면 닫아야 한다 체크
        if rule.count('{') != rule.count('}'):
            isValid = False
        else:
            is_opened = False
            count = 0
            for char in rule:
                print(is_opened, count)
                if char == '{':
                    if is_opened:
                        isValid = False
                        break
                    is_opened = True
                elif char == '}':
                    if not is_opened:
                        isValid = False
                        break
                    if count == 0:
                        isValid = False
                        break
                    is_opened = False
                    count = 0
                elif is_opened is True:
                    count += 1
        return isValid

    def clean_desc_rule(self):
        desc_rule = self.cleaned_data["desc_rule"]
        if desc_rule:
            isValid = self.check_rule_syntax(desc_rule)
            if not isValid:
                raise forms.ValidationError(
                    "콘텐츠 설명 규칙의 형식이 잘못되었습니다.")
        return desc_rule

    def clean_code_rule(self):
        code_rule = self.cleaned_data["code_rule"]
        if code_rule:
            isValid = self.check_rule_syntax(code_rule)
            if not isValid:
                raise forms.ValidationError(
                    "코드 생성 규칙의 형식이 잘못되었습니다.")
        return code_rule

    def clean_code_options(self):
        code_options = self.cleaned_data["code_options"]
        if code_options:
            code_options = json.loads(code_options)
        return code_options

    def clean_data(self):
        data = self.cleaned_data["data"]
        data = json.loads(data)
        return data

    def clean_meta(self):
        meta = self.cleaned_data["meta"]
        meta = json.loads(meta)
        return meta

    class Meta:
        model = ServicePolicy
        fields = [
            "is_promotion",
            "is_active",
            "is_active_homepage",
        ]


class MyincoAdminServicePolicyServiceUpdateView(UpdateView):
    model = ServicePolicy
    form_class = ServicePolicyServiceUpdateForm
    template_name = "myinco_admin/category/policy_create.html"

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        print('request.POST:', request.POST)
        form = self.get_form()
        if form.is_valid():
            print(' == form is_valid')
            return self.form_valid(form)
        else:
            print(' == form is_invalid!!!!!!!!!!')
            return self.form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        print("data!!:", form.cleaned_data)
        # self.object = form.save()
        self.object = self.get_object()
        self.product = Product.objects.get(id=self.request.POST.get('product_id'))
        if self.object.is_active_homepage is True:
            ServicePolicy.objects.filter(
                category=self.object.category,
            ).update(is_active_homepage=False)
            self.object.is_active_homepage = True
            self.object.save()
        data = form.cleaned_data

        for record in data["data"]:
            no, service_code, service_description, is_buy_now, price = record
            if no == "연번":
                continue
            """
            if ServicePolicyPriceOption.objects.filter(service_code=service_code).exists():
                price_option = ServicePolicyPriceOption.objects.get(service_code=service_code)
            else:
                price_option = ServicePolicyPriceOption.objects.create(
                    policy=self.object,
                    product=self.product,
                    product_name=self.product.product_name,
                    price=price,
                )
            for gc_name, code_name in info_dict[no].items():
                group_code = ServicePolicyGroupCode.objects.get(
                    policy=self.object, name=gc_name
                )
                code = ServicePolicyCode.objects.get(
                    group_code=group_code, name=code_name
                )
                price_option.options.add(code)
            """


        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class MyincoAdminServicePolicyServiceCreateView(CreateView):
    model = ServicePolicy
    form_class = ServicePolicyServiceUpdateForm
    template_name = "myinco_admin/category/policy_create.html"

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        print('request.POST:', request.POST)
        form = self.get_form()
        if form.is_valid():
            print(' == form is_valid')
            return self.form_valid(form)
        else:
            print(' == form is_invalid!!!!!!!!!!')
            return self.form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        print("data!!:", form.cleaned_data)
        # self.object = form.save()
        self.object = self.get_object()
        self.product = Product.objects.get(id=self.request.POST.get('product_id'))
        if self.object.is_active_homepage is True:
            ServicePolicy.objects.filter(
                category=self.object.category,
            ).update(is_active_homepage=False)
            self.object.is_active_homepage = True
            self.object.save()
        data = form.cleaned_data

        for record in data["data"]:
            no, service_code, service_description, is_buy_now, price = record
            if no == "연번":
                continue
            """
            if ServicePolicyPriceOption.objects.filter(service_code=service_code).exists():
                price_option = ServicePolicyPriceOption.objects.get(service_code=service_code)
            else:
                price_option = ServicePolicyPriceOption.objects.create(
                    policy=self.object,
                    product=self.product,
                    product_name=self.product.product_name,
                    price=price,
                )
            for gc_name, code_name in info_dict[no].items():
                group_code = ServicePolicyGroupCode.objects.get(
                    policy=self.object, name=gc_name
                )
                code = ServicePolicyCode.objects.get(
                    group_code=group_code, name=code_name
                )
                price_option.options.add(code)
            """


        return JsonResponse({"is_success": True})

    def form_invalid(self, form):
        print("Form.Errors:", form.errors)
        return JsonResponse({"is_success": False})


class ProductCategoryInfoView(DetailView):
    model = ProductCategory
    template_name = ""

    def get(self, request, *args, **kwargs):
        main_category = self.get_object()
        sub_category_list = []
        for sub in main_category.productcategory_set.all():
            sub_category_list.append({
                'pk': sub.pk,
                'name': sub.name,
            })
        data = {
            'sub_category_list': sub_category_list,
        }
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
            }
        )
