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
from django.utils import timezone
from isghome.models import (
    CustomerQuestion,
    CustomerQuestionAttachment,
    FAQ,
    FAQType,
    TrialLicenseRequest,    
    ReinstallRequest,
    DownloadCenter,
    ProductCategory,
    InstallFile,
    ManualLink,
    Product,
)
from isghome.views import send_auto_email
from isghome.utils import get_strftime


class MyincoCustomerQuestionListView(ListView):
    model = CustomerQuestion
    template_name = "myinco_admin/cs/question_list.html"
    
    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by('-ctime')
        return queryset


class MyincoCustomerQuestionDetailView(DetailView):
    model = CustomerQuestion
    template_name = "myinco_admin/cs/question_detail.html"

    def get(self, request, *args, **kwargs):
        q = self.get_object()
        user_images = []
        manager_images = []
        for attach in q.get_user_attachment():
            image_link = f'''<a href="{attach.attachment.url}" target="_blank" style="background-image: url('{attach.attachment.url}')"></a>'''
            user_images.append(image_link)
        for attach in q.get_etc_attachment():
            image_link = f'''<a href="{attach.attachment.url}" target="_blank" style="background-image: url('{attach.attachment.url}')"></a>'''
            manager_images.append(image_link)
        data = {
            'question_type': str(q.question_type),
            'ctime': q.ctime.strftime('%Y-%m-%d'),
            'fixed_time': q.fixed_time.strftime('%Y-%m-%d') if q.fixed_time else '',
            'order': q.order.identifier if q.order else '',
            'title': q.title,
            'content': q.content,
            'fixed_memo': q.fixed_memo,
            'name': q.user.profile.name,
            'email': q.user.username,
            'phone_number': q.user.profile.phone_number.as_national,
            'organization': q.user.profile.organization.place_name,
            'user_images': user_images,
            'manager_images': manager_images,
            'status2': q.status2,
        }
        return JsonResponse(data)


class CustomerQuestionUpdateForm(forms.ModelForm):
    attachment = forms.FileField(required=False)

    class Meta:
        model = CustomerQuestion
        fields = ('fixed_memo', 'status2')


class MyincoCustomerQuestionUpdateView(UpdateView):
    model = CustomerQuestion
    form_class = CustomerQuestionUpdateForm
    template_name = 'myinco_admin/cs/question_update.html'

    @transaction.atomic
    def form_valid(self, form):
        self.object = form.save()
        for attachment in self.request.FILES.getlist('attachment'):
            CustomerQuestionAttachment.objects.create(
                    question=self.object,
                    attachmented_by='manager',
                    attachment=attachment,
                    user=self.request.user)
        if self.object.status2 in ('done_with_email', 'done_withnot_email'):
            self.object.fixed_time = timezone.now()
            self.object.fixed_user = self.request.user
            self.object.save()
        if self.object.status2 == 'done_with_email':
            name = self.object.user.profile.name
            send_auto_email(
                client_info=self.object,
                email_subject=f"[(주)인실리코젠] {name}님, 문의내용의 답변이 도착했어요.",
                email_template="mail/customerquestion_answer.html",
                to_email=self.object.user.username,
            )
        return JsonResponse({'is_success': True})

    def form_invalid(self, form):
        print(form.errors)
        return JsonResponse({'is_success': False})


class MyincoFAQListView(ListView):
    model = FAQ
    template_name = "myinco_admin/cs/faq_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by('-ctime')
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['faq_type_set'] = FAQType.objects.all()
        related_tags = Product.objects.exclude(
                related_tags='').values_list(
                        'related_tags', flat=True)
        tag_list = []
        for tags in related_tags:
            if tags:
                for t in tags.split(','):
                    if t not in tag_list:
                        tag_list.append(t)
        context['tag_list'] = tag_list
        return context


class MyincoFAQDetailView(DetailView):
    model = FAQ
    template_name = "myinco_admin/cs/faq_detail.html"

    def get(self, request, *args, **kwargs):
        faq = self.get_object()
        data = {
            'title': faq.title,
            'anwser': faq.anwser,
            'faq_type': faq.faq_type.pk,
            'is_active': 'True' if faq.is_active else 'False',
        }
        return JsonResponse(data)


class FAQCreateForm(forms.ModelForm):

    class Meta:
        model = FAQ
        fields = (
            'faq_type', 'title', 'anwser',
            'attachment1', 'attachment2','is_active')


class MyincoFAQCreateView(CreateView):
    model = FAQ
    form_class = FAQCreateForm

    def post(self, request, *args, **kwargs):
        print(request.POST)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()
        related_tags = self.request.POST.getlist('related_tags')
        if related_tags:
            self.object.tags = ','.join(related_tags)
        return JsonResponse({'is_success': True})

    def form_invalid(self, form):
        print(form.errors)
        return JsonResponse({'is_success': False})


class FAQUpdateForm(forms.ModelForm):

    class Meta:
        model = FAQ
        fields = (
            'faq_type', 'title', 'anwser',
            'attachment1', 'attachment2','is_active')


class MyincoFAQUpdateView(UpdateView):
    model = FAQ
    form_class = FAQUpdateForm

    def form_valid(self, form):
        self.object = form.save()
        related_tags = self.request.POST.getlist('related_tags')
        if related_tags:
            self.object.tags = ','.join(related_tags)
        return JsonResponse({'is_success': True})

    def form_invalid(self, form):
        return JsonResponse({'is_success': False})


class MyincoFAQDeleteView(DeleteView):
    model = FAQ

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return JsonResponse({'is_success': True})

    def form_valid(self, form):
        self.object.delete()
        return JsonResponse({'is_success': True})

    def form_invalid(self, form):
        return JsonResponse({'is_success': False})


class MyincoTrialLicenseRequestListView(ListView):
    model = TrialLicenseRequest
    template_name = "myinco_admin/cs/trial_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by('-ctime')
        return queryset


class MyincoTrialLicenseRequestDetailView(DetailView):
    model = TrialLicenseRequest
    template_name = "myinco_admin/cs/trial_detail.html"

    def get(self, request, *args, **kwargs):
        tr = self.get_object()
        manager = ''
        if tr.user.profile.manager:
            manager = tr.user.profile.manager.profile.name
        ctime = get_strftime(tr.ctime, '%Y-%m-%d %H:%M:%S')
        fixed_time = ''
        if tr.fixed_time:
            fixed_time = get_strftime(tr.fixed_time, '%Y-%m-%d %H:%M:%S')
        data = {
            'product_name': tr.product.product_name,
            'en_organization': tr.en_organization,
            'en_name': tr.en_name,
            'phone_number': tr.user.profile.phone_number.as_national,
            'email': tr.user.username,
            'address': tr.user.profile.address,
            'address_detail': tr.user.profile.address_detail,
            'purchase_intention': tr.get_purchase_intention_display(),
            'manager': manager,
            'ctime': ctime,
            'fixed_time': fixed_time,
            'is_fixed': 'y' if tr.is_fixed else 'n',
        }
        return JsonResponse(data)


class MyincoTrialLicenseRequestUpdateForm(forms.ModelForm):
    TRUE_FALSE_CHOICES = (
        ('y', 'Yes'),
        ('n', 'No')
    )
    is_fixed = forms.ChoiceField(
        choices=TRUE_FALSE_CHOICES,
    )

    class Meta:
        model = TrialLicenseRequest
        fields = []


class MyincoTrialLicenseRequestUpdateView(UpdateView):
    model = TrialLicenseRequest
    form_class = MyincoTrialLicenseRequestUpdateForm
    template_name = "myinco_admin/cs/trial_update.html"

    def form_valid(self, form):
        data = form.cleaned_data
        tr = self.get_object()
        before_is_fixed = 'y' if tr.is_fixed else 'n'
        if data.get('is_fixed') == 'y':
            tr.is_fixed = True
            tr.fixed_user = self.request.user
            tr.fixed_time = timezone.now()
            """
            if before_is_fixed:
                pass
            else:
                pass
            """
        else:
            tr.is_fixed = False
            """
            if before_is_fixed:
                pass
            else:
                pass
            """
        tr.save()
        return JsonResponse({'is_success': True})

    def form_invalid(self, form):
        err_messages = '-'
        return JsonResponse({
            'is_success': False,
            'err_messages': err_messages})


class MyincoReinstallRequestListView(ListView):
    model = ReinstallRequest
    template_name = "myinco_admin/cs/reinstall_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by('-ctime')
        return queryset


class MyincoReinstallRequestDetailView(DetailView):
    model = ReinstallRequest
    template_name = "myinco_admin/cs/reinstall_detail.html"

    def get(self, request, *args, **kwargs):
        rr = self.get_object()
        manager = ''
        if rr.user.profile.manager:
            manager = rr.user.profile.manager.profile.name
        ctime = get_strftime(rr.ctime, '%Y-%m-%d %H:%M:%S')
        fixed_time = ''
        if rr.fixed_time:
            fixed_time = get_strftime(rr.fixed_time, '%Y-%m-%d %H:%M:%S')
        data = {
            'product_name': rr.product.product_name,
            'organization': rr.user.profile.organization.place_name,
            'name': rr.user.profile.name,
            'phone_number': rr.user.profile.phone_number.as_national,
            'email': rr.user.username,
            'license_key': rr.license_key,
            'host_id': rr.host_id,
            'reason': rr.reason,
            'manager': manager,
            'ctime': ctime,
            'fixed_time': fixed_time,
            'is_fixed': 'y' if rr.is_fixed else 'n',
        }
        return JsonResponse(data)


class MyincoReinstallRequestUpdateForm(forms.ModelForm):
    TRUE_FALSE_CHOICES = (
        ('y', 'Yes'),
        ('n', 'No')
    )
    is_fixed = forms.ChoiceField(
        choices=TRUE_FALSE_CHOICES,
    )

    class Meta:
        model = ReinstallRequest
        fields = []


class MyincoReinstallRequestUpdateView(UpdateView):
    model = ReinstallRequest
    form_class = MyincoReinstallRequestUpdateForm
    template_name = "myinco_admin/cs/reinstall_update.html"

    def form_valid(self, form):
        data = form.cleaned_data
        rr = self.get_object()
        before_is_fixed = 'y' if rr.is_fixed else 'n'
        if data.get('is_fixed') == 'y':
            rr.is_fixed = True
            rr.fixed_user = self.request.user
            rr.fixed_time = timezone.now()
            """
            if before_is_fixed:
                pass
            else:
                pass
            """
        else:
            rr.is_fixed = False
            """
            if before_is_fixed:
                pass
            else:
                pass
            """
        rr.save()
        return JsonResponse({'is_success': True})

    def form_invalid(self, form):
        err_messages = '-'
        return JsonResponse({
            'is_success': False,
            'err_messages': err_messages})


class MyincoDownloadCenterListView(ListView):
    model = DownloadCenter
    template_name = "myinco_admin/cs/download_list.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["main_categories"] = ProductCategory.objects.filter(
            category_type="main"
        )
        context["sub_categories"] = ProductCategory.objects.filter(
            category_type="sub"
        )
        return context


class MyincoDownloadCenterDetailView(DetailView):
    model = DownloadCenter
    template_name = "myinco_admin/cs/download_detail.html"


class MyincoDownloadCenterDeleteView(DeleteView):
    model = DownloadCenter

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return JsonResponse({'is_success': True})

    def form_valid(self, form):
        self.object.delete()
        return JsonResponse({'is_success': True})

    def form_invalid(self, form):
        return JsonResponse({'is_success': False})


class DownloadCenterCreateForm(forms.ModelForm):
    # sub_category = forms.ModelChoiceField(
    #     queryset=ProductCategory.objects.filter(category_type="sub"),
    # )

    class Meta:
        model = DownloadCenter
        fields = ('product', 'version', 'is_active')


class MyincoDownloadCenterCreateView(CreateView):
    model = DownloadCenter
    form_class = DownloadCenterCreateForm
    template_name = 'myinco_admin/cs/dc_create.html'
    success_url = reverse_lazy('myinco_admin-download-list')

    @transaction.atomic
    def form_valid(self, form):
        # print(self.request.POST)
        # print(self.request.FILES)
        # print('data', form.cleaned_data)
        self.object = form.save()
        self.object.user = self.request.user
        self.object.save()
        self.create_installfile()
        self.create_manuallink()
        return JsonResponse({'is_success': True})

    def create_installfile(self):
        install_name = self.request.POST.getlist('install_name')
        install_os_description = self.request.POST.getlist('install_os_description')
        attachment_list = self.request.FILES.getlist('attachment')
        for i, name in enumerate(install_name):
            try:
                os_description = install_os_description[i]
            except IndexError:
                break
            try:
                attachment = attachment_list[i]
            except IndexError:
                break
            if name and os_description and attachment:
                InstallFile.objects.create(
                        download_center=self.object,
                        name=name,
                        os_description=os_description,
                        attachment=attachment)

    def create_manuallink(self):
        manual_name = self.request.POST.getlist('manual_name')
        manual_link = self.request.POST.getlist('manual_link')
        for i, name in enumerate(manual_name):
            try:
                link = manual_link[i]
            except IndexError:
                break
            if name and link:
                ManualLink.objects.create(
                        download_center=self.object,
                        name=name,
                        link=link)

    def form_invalid(self, form):
        print(self.request.POST)
        print(self.request.FILES)
        print(form.errors)
        return JsonResponse({'is_success': False})


class DownloadCenterUpdateForm(forms.ModelForm):

    class Meta:
        model = DownloadCenter
        fields = ('version', 'is_active')


class MyincoDownloadCenterUpdateView(UpdateView):
    model = DownloadCenter
    form_class = DownloadCenterUpdateForm

    @transaction.atomic
    def form_valid(self, form):
        # print(self.request.POST)
        # print(self.request.FILES)
        # print('deleted_installfile:', self.request.POST.getlist('deleted_installfile'))
        # print('deleted_manual:', self.request.POST.getlist('deleted_manual'))
        self.object = form.save()
        self.update_installfile()
        self.update_manuallink()
        return JsonResponse({'is_success': True})

    def update_installfile(self):
        install_name = self.request.POST.getlist('install_name')
        install_os_description = self.request.POST.getlist('install_os_description')
        # 파일은.. 변경 있을 때만.. 파일 변경 있을 때만 pop으로 가져오기
        attachment_list = self.request.FILES.getlist('attachment')
        installfile_ids = self.request.POST.getlist('installfile')
        is_update_installfile = self.request.POST.getlist('is_update_installfile')
        new_installfile = self.request.POST.getlist('new_installfile')
        deleted_installfile = self.request.POST.get('deleted_installfile')
        # 신규 or 업데이트
        for i, name in enumerate(install_name):
            try:
                os_description = install_os_description[i]
            except IndexError:
                break
            try:
                installfile_id = installfile_ids[i]
                if installfile_id == 'none':
                    installfile_id = ''
            except IndexError:
                break
            try:
                is_file_update = is_update_installfile[i]
                if is_file_update == 'True':
                    is_file_update = True
                else:
                    is_file_update = False
            except IndexError:
                break
            try:
                is_new = new_installfile[i]
                if is_new == 'True':
                    is_new = True
                else:
                    is_new = False
            except IndexError:
                break
            # print(name, os_description, installfile_id, is_file_update, is_new)
            # 추가 시 파일 정보만 업데이트 안할 수도.... 아니.. 파일 추가만 안했을 수도 ....
            if is_new:
                if name and os_description:
                    attachment = attachment_list.pop(0)
                    InstallFile.objects.create(
                            download_center=self.object,
                            name=name,
                            os_description=os_description,
                            attachment=attachment)
            else:
                obj = InstallFile.objects.get(id=installfile_id)
                obj.name = name
                obj.os_description = os_description
                if is_file_update:
                    attachment = attachment_list.pop(0)
                    obj.attachment = attachment
                obj.save()
        # 삭제
        if deleted_installfile:
            for delete_id in deleted_installfile.split('__'):
                InstallFile.objects.get(id=delete_id).delete()

    def update_manuallink(self):
        manual_name = self.request.POST.getlist('manual_name')
        manual_link = self.request.POST.getlist('manual_link')
        manual_ids = self.request.POST.getlist('manual')
        new_manual = self.request.POST.getlist('new_manual')
        deleted_manual = self.request.POST.get('deleted_manual')
        # 신규 or 업데이트
        for i, name in enumerate(manual_name):
            try:
                link = manual_link[i]
            except IndexError:
                break
            try:
                manual_id = manual_ids[i]
                if manual_id == 'none':
                    manual_id = ''
            except IndexError:
                break
            try:
                is_new = new_manual[i]
                if is_new == 'True':
                    is_new = True
                else:
                    is_new = False
            except IndexError:
                break
            # print(name, link, manual_id, is_new)
            if is_new:
                if name and link:
                    ManualLink.objects.create(
                            download_center=self.object,
                            name=name,
                            link=link)
            else:
                obj = ManualLink.objects.get(id=manual_id)
                obj.name = name
                obj.link = link
                obj.save()
        # 삭제
        if deleted_manual:
            for delete_id in deleted_manual.split('__'):
                ManualLink.objects.get(id=delete_id).delete()

    def form_invalid(self, form):
        print(self.request.POST)
        print(self.request.FILES)
        print(form.errors)
        return JsonResponse({'is_success': False})
