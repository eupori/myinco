from django import forms
from django.views.generic import (
    ListView, DetailView,
    CreateView, UpdateView,
    # DeleteView,
)
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Q
# from django.forms.models import inlineformset_factory
from django.utils.safestring import mark_safe

# from django_summernote.widgets import SummernoteWidget
from ckeditor.widgets import CKEditorWidget

from isghome.models import (
    ServicePolicy, ServicePolicyPriceOption,
    Product, ProductDescription, ProductCategory,
)
from isghome.views import MultipleCharField


class MyincoProductListView(ListView):
    model = Product
    # ordering = ('display_order', '-mtime')
    ordering = ('-ctime')
    template_name = 'myinco_admin/product/list.html'

    def get_queryset(self):
        keyword = self.request.GET.get('keyword')
        queryset = super().get_queryset()
        queryset = queryset.filter(productdescription__isnull=False)
        if keyword:
            queryset = queryset.filter(
                Q(product_name__icontains=keyword) |
                Q(category__name__icontains=keyword) |
                Q(category__parent__name__icontains=keyword))
        queryset = queryset.distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['main_categories'] = ProductCategory.objects.filter(
                category_type='main')
        related_tags = Product.objects.exclude(
                related_tags='').values_list(
                        'related_tags', flat=True)
        tag_list = []
        for tags in related_tags:
            if tags:
                for t in tags.split(','):
                    if t not in tag_list:
                        tag_list.append(t)
        context_data['tag_list'] = tag_list
        return context_data


class ProductDescriptionForm(forms.ModelForm):
    # content = forms.CharField(widgets=CKEditorWidget())

    class Meta:
        model = ProductDescription
        fields = (
            'main_image',
            'main_image2',
            'main_image3',
            'main_image4',
            'main_image5',
            'thumbnail_image',
            'oneline_description',
            'content',
        )
        widgets = {
            # 'content': CKEditorWidget(),
        }


class ProductCreateForm(forms.ModelForm):
    product_name = forms.CharField(min_length=3)
    product_code = forms.CharField(min_length=3)
    related_tags = MultipleCharField(required=False)

    class Meta:
        model = Product
        exclude = ('manufacturer', 'ctime', 'mtime', 'user', 'ip_addr')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        name = ProductDescriptionForm.__name__.lower()
        setattr(self, name, ProductDescriptionForm(*args, **kwargs))
        form = getattr(self, name)
        self.fields.update(form.fields)
        self.initial.update(form.initial)

    def is_valid(self):
        isValid = True
        name = ProductDescriptionForm.__name__.lower()
        form = getattr(self, name)
        if not form.is_valid():
            isValid = False
        # is_valid will trigger clean method
        # so it should be called after all other forms is_valid are called
        # otherwise clean_data will be empty
        if not super().is_valid():
            isValid = False
        name = ProductDescriptionForm.__name__.lower()
        form = getattr(self, name)
        self.errors.update(form.errors)
        return isValid

    def clean(self):
        cleaned_data = super().clean()
        name = ProductDescriptionForm.__name__.lower()
        form = getattr(self, name)
        cleaned_data.update(form.cleaned_data)
        return cleaned_data

    def clean_related_tags(self):
        related_tags = self.cleaned_data.get('related_tags')
        if related_tags:
            related_tags = ','.join(related_tags)
        return related_tags


class MyincoProductCreateView(CreateView):
    model = Product
    # ordering = ('display_order', '-mtime')
    ordering = ('-ctime')
    template_name = 'myinco_admin/product/list.html'
    form_class = ProductCreateForm

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['main_categories'] = ProductCategory.objects.filter(
                category_type='main')
        related_tags = Product.objects.exclude(
                related_tags='').values_list(
                        'related_tags', flat=True)
        tag_list = []
        for tags in related_tags:
            if tags:
                for t in tags.split(','):
                    if t not in tag_list:
                        tag_list.append(t)
        context_data['tag_list'] = tag_list
        return context_data

    def get_success_url(self):
        if self.object:
            return reverse_lazy(
                    'myinco_admin-product-update',
                    kwargs={'pk': self.object.pk})
        else:
            return reverse_lazy('myinco_admin-product-list')

    def check_same_name(self, data):
        product_name = data.get('product_name')
        if Product.objects.filter(product_name=product_name).exists():
            return True
        return False

    def check_same_code(self, data):
        product_code = data.get('product_code')
        if Product.objects.filter(product_code=product_code).exists():
            return True
        return False

    @transaction.atomic
    def save_product(self, form):
        data = form.cleaned_data
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()
        ProductDescription.objects.create(
            product=self.object,
            main_image=data.get('main_image'),
            main_image2=data.get('main_image2'),
            main_image3=data.get('main_image3'),
            main_image4=data.get('main_image4'),
            main_image5=data.get('main_image5'),
            thumbnail_image=data.get('thumbnail_image'),
            oneline_description=data.get('oneline_description'),
            content=data.get('content'),
            is_active=True,
        )

    def form_valid(self, form):
        is_success = False
        err_messages = ''
        redirect_url = ''
        data = form.cleaned_data
        if self.check_same_name(data):
            err_messages = '같은 이름의 서비스가 이미 존재합니다.'
            return JsonResponse({
                'is_success': is_success,
                'err_messages': err_messages})
        if self.check_same_code(data):
            err_messages = '같은 코드의 서비스가 이미 존재합니다.'
            return JsonResponse({
                'is_success': is_success,
                'err_messages': err_messages})
        try:
            self.save_product(form)
            is_success = True
            redirect_url = self.get_success_url()
        except Exception as e:
            err_messages = str(e)
        return JsonResponse({
            'is_success': is_success,
            'product_name': data.get('product_name'),
            'err_messages': err_messages,
            'redirect_url': redirect_url})

    def form_invalid(self, form):
        errors = []
        for error_key in form.errors:
            for error in form.errors[error_key]:
                errors.append(
                        f'"{error_key}: {error}"')
        err_messages = '<br>'.join(errors)
        print('errors:', errors)
        return JsonResponse({
            'is_success': False,
            'err_messages': mark_safe(err_messages)})


class ProductUpdateForm(forms.ModelForm):
    product_name = forms.CharField(min_length=3)
    product_code = forms.CharField(min_length=3)
    related_tags = MultipleCharField(required=False)

    class Meta:
        model = Product
        exclude = ('manufacturer', 'ctime', 'mtime', 'user', 'ip_addr')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        name = ProductDescriptionForm.__name__.lower()
        setattr(self, name, ProductDescriptionForm(*args, **kwargs))
        form = getattr(self, name)
        self.fields.update(form.fields)
        self.initial.update(form.initial)

    def is_valid(self):
        isValid = True
        name = ProductDescriptionForm.__name__.lower()
        form = getattr(self, name)
        if not form.is_valid():
            isValid = False
        # is_valid will trigger clean method
        # so it should be called after all other forms is_valid are called
        # otherwise clean_data will be empty
        if not super().is_valid():
            isValid = False
        name = ProductDescriptionForm.__name__.lower()
        form = getattr(self, name)
        self.errors.update(form.errors)
        return isValid

    def clean(self):
        cleaned_data = super().clean()
        name = ProductDescriptionForm.__name__.lower()
        form = getattr(self, name)
        cleaned_data.update(form.cleaned_data)
        return cleaned_data

    def clean_related_tags(self):
        related_tags = self.cleaned_data.get('related_tags')
        if related_tags:
            related_tags = ','.join(related_tags)
        return related_tags


class MyincoProductUpdateView(UpdateView):
    model = Product
    form_class = ProductUpdateForm
    template_name = 'myinco_admin/product/update.html'
    is_update_view = True
    description_fields = [
        'main_image',
        'main_image2',
        'main_image3',
        'main_image4',
        'main_image5',
        'thumbnail_image',
        'oneline_description',
        'content',
        ]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['main_categories'] = ProductCategory.objects.filter(
                category_type='main')
        all_tags = Product.objects.exclude(
                related_tags='').values_list(
                        'related_tags', flat=True)
        tag_list = []
        for tags in all_tags:
            if tags:
                for t in tags.split(','):
                    if t not in tag_list:
                        tag_list.append(t)
        context['tag_list'] = tag_list
        related_tags = []
        if self.object.related_tags:
            related_tags = self.object.related_tags.split(',')
        context['related_tags'] = related_tags
        spos = ServicePolicyPriceOption.objects.filter(
                product=self.object).values_list('policy')
        sp_ids = [values[0] for values in spos]
        policy_set = ServicePolicy.objects.filter(
                id__in=sp_ids).order_by('-ctime')
        empty_policy_set = []
        empty_policy_set = ServicePolicy.objects.filter(
                category=self.object.category).exclude(id__in=sp_ids)
        empty_policy_ids = []
        for policy in empty_policy_set:
            if policy.servicepolicypriceoption_set.count() == 0:
                empty_policy_ids.append(policy.id)
        context['policy_set'] = policy_set
        context['empty_policy_set'] = ServicePolicy.objects.filter(
                id__in=empty_policy_ids)
        return context

    def get_initial(self):
        c_desc = self.object.get_current_description()
        if c_desc:
            self.initial.update({
                'main_image': c_desc.main_image,
                'main_image2': c_desc.main_image2,
                'main_image3': c_desc.main_image3,
                'main_image4': c_desc.main_image4,
                'main_image5': c_desc.main_image5,
                'thumbnail_image': c_desc.thumbnail_image,
                'oneline_description': c_desc.oneline_description,
                'content': c_desc.content,
            })
        return self.initial.copy()

    def get_success_url(self):
        return reverse_lazy(
                'myinco_admin-product-update',
                kwargs={'pk': self.object.pk})

    @transaction.atomic
    def _form_valid(self, form, formset, request):
        # print('form data:', form.cleaned_data)
        self.object = form.save()
        self.object.user = self.request.user
        self.object.save()
        formset.instance = self.object
        current_descriptions = formset.save(commit=False)
        if current_descriptions:
            current_descriptions[0].is_active = True
            current_descriptions[0].save()
        # print('save success')
        return HttpResponseRedirect(self.get_success_url())
        """
        context = self.get_context_data()
        context['current_tab'] = 'tabs-01'
        context['is_update'] = True
        return self.render_to_response(context)
        """

    def check_same_name(self, data):
        product_name = data.get('product_name')
        if Product.objects.filter(product_name=product_name).exists():
            return True
        return False

    def check_same_code(self, data):
        product_code = data.get('product_code')
        if Product.objects.filter(product_code=product_code).exists():
            return True
        return False

    def is_changed_description(self, form):
        isChanged = False
        for field_name in self.description_fields:
            if field_name in form.changed_data:
                isChanged = True
                break
        return isChanged

    @transaction.atomic
    def save_product(self, form):
        self.object = form.save()
        data = form.cleaned_data
        if self.is_changed_description(form):
            c_desc = self.object.get_current_description()
            c_desc.is_active = False
            c_desc.save()
            c_desc.pk = None
            c_desc.id = None
            for field_name in self.description_fields:
                if field_name in form.changed_data:
                    setattr(c_desc, field_name, data.get(field_name))
            c_desc.is_active = True
            c_desc.save()
            """
            ProductDescription.objects.create(
                product=self.object,
                main_image=data.get('main_image'),
                main_image2=data.get('main_image2'),
                main_image3=data.get('main_image3'),
                main_image4=data.get('main_image4'),
                main_image5=data.get('main_image5'),
                thumbnail_image=data.get('thumbnail_image'),
                oneline_description=data.get('oneline_description'),
                content=data.get('content'),
                is_active=True,
            )
            """

    def form_valid(self, form):
        is_success = False
        err_messages = ''
        redirect_url = ''
        data = form.cleaned_data
        print('isValid!!!')
        print(form.changed_data)
        print(self.request.POST.get('content'))
        if 'product_name' in form.changed_data:
            if self.check_same_name(data):
                err_messages = '같은 이름의 서비스가 이미 존재합니다.'
                return JsonResponse({
                    'is_success': is_success,
                    'err_messages': err_messages})
        if 'product_code' in form.changed_data:
            if self.check_same_code(data):
                err_messages = '같은 코드의 서비스가 이미 존재합니다.'
                return JsonResponse({
                    'is_success': is_success,
                    'err_messages': err_messages})
        try:
            self.save_product(form)
            is_success = True
            redirect_url = self.get_success_url()
        except Exception as e:
            err_messages = str(e)
        return JsonResponse({
            'is_success': is_success,
            'product_name': data.get('product_name'),
            'err_messages': err_messages,
            'redirect_url': redirect_url})

    def form_invalid(self, form):
        errors = []
        for error_key in form.errors:
            for error in form.errors[error_key]:
                errors.append(
                        f'"{error_key}: {error}"')
        err_messages = '<br>'.join(errors)
        print('errors:', errors)
        return JsonResponse({
            'is_success': False,
            'err_messages': mark_safe(err_messages)})


class MyincoProductSupportUpdateView(UpdateView):
    model = Product
    template_name = ''
    NAME_CHOICES = (
        'trial_available',
        'reinstall_available',
        'event_available')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        name = request.POST.get('name')
        value = request.POST.get('value')
        is_success = False
        if name and name in self.NAME_CHOICES:
            if value:
                if value == 'true':
                    value = True
                else:
                    value = False
                setattr(self.object, name, value)
                self.object.save()
                is_success = True
        return JsonResponse({'is_success': is_success})


class MyincoProductInfoView(DetailView):
    model = ProductCategory
    template_name = ""

    def get(self, request, *args, **kwargs):
        category = self.get_object()
        product_list = []
        for product in Product.objects.filter(category=category):
            product_list.append({
                'pk': product.pk,
                'name': product.product_name,
            })
        data = {
            'product_list': product_list,
        }
        return JsonResponse(
            {
                "is_success": True,
                "data": data,
            }
        )
