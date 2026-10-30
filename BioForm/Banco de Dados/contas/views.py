from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from metas.calculo import salvar_meta
from rotina.campos import DIAS, DURACOES, TEM_DIAS_FIXOS
from rotina.confirmacao import confirmar_rotina
from saude.models import INTENSIDADES, EsporteUsuario, HistoricoMedida, MetaNutricional, Usuario

from .forms import (
    FREQUENCIAS,
    CadastroForm,
    ContaForm,
    DadosForm,
    EntrarForm,
    EsportesForm,
    ExcluirContaForm,
    ObjetivoForm,
    so_digitos,
)
from .onboarding import SESSAO_ONBOARDING, SESSAO_PESO, em_onboarding, perfil_obrigatorio, proximo_passo


def depois_de_salvar(request, usuario, proximo):
    """No onboarding segue para o próximo passo; editando, recalcula as metas e volta para elas."""
    if em_onboarding(request, usuario):
        return redirect(proximo)
    salvar_meta(usuario)
    messages.success(request, 'Perfil atualizado. Suas metas foram recalculadas.')
    return redirect('perfil_metas')


def registrar_medida(usuario, peso=None, objetivo=None):
    """
    Atualiza o histórico de medidas (gráfico de evolução): se já há registro hoje, corrige o
    de hoje; se não, cria um ponto novo copiando o que não mudou do registro anterior.
    """
    atual = usuario.medida_atual()
    peso = peso if peso is not None else atual.peso_kg
    objetivo = objetivo or atual.objetivo_momento
    if atual and atual.peso_kg == peso and atual.objetivo_momento == objetivo:
        return atual
    if atual and timezone.localdate(atual.data_registro) == timezone.localdate():
        atual.peso_kg, atual.objetivo_momento = peso, objetivo
        atual.save()
        return atual
    return HistoricoMedida.objects.create(
        usuario=usuario, data_registro=timezone.now(), peso_kg=peso, objetivo_momento=objetivo,
    )


# =====================================================================
# Conta: entrar, sair, cadastro
# =====================================================================

def inicio(request):
    if not request.user.is_authenticated:
        return redirect('entrar')
    usuario = Usuario.objects.filter(conta=request.user).first()
    if usuario is None:
        return redirect('usuarios' if request.user.is_staff else 'cadastro')
    return redirect(proximo_passo(usuario) or 'perfil_metas')


class EntrarView(auth_views.LoginView):
    template_name = 'contas/entrar.html'
    authentication_form = EntrarForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        resposta = super().form_valid(form)
        if not form.cleaned_data.get('lembrar'):
            self.request.session.set_expiry(0)  # sai ao fechar o navegador
        return resposta


def cadastro(request):
    if request.user.is_authenticated:
        return redirect('inicio')
    form = CadastroForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        conta = form.save()
        login(request, conta, backend='contas.backends.EmailOuCPFBackend')
        request.session[SESSAO_ONBOARDING] = True
        messages.success(request, 'Conta criada! Agora vamos montar seu perfil.')
        return redirect('perfil_dados')
    return render(request, 'contas/cadastro.html', {'form': form})


# =====================================================================
# Perfil: passos 1 a 3 (servem tanto para o onboarding quanto para editar depois)
# =====================================================================

@perfil_obrigatorio
def perfil_dados(request, usuario):
    medida = usuario.medida_atual()
    peso_inicial = medida.peso_kg if medida else request.session.get(SESSAO_PESO)
    form = DadosForm(request.POST or None, instance=usuario, initial={'peso_kg': peso_inicial})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
            peso = form.cleaned_data['peso_kg']
            if medida:
                registrar_medida(usuario, peso=peso)
            else:
                # O peso só vira histórico no passo 2, junto com o objetivo
                request.session[SESSAO_PESO] = str(peso)
        return depois_de_salvar(request, usuario, 'perfil_objetivo')
    return render(request, 'contas/perfil_dados.html', {
        'form': form, 'usuario': usuario, 'passo': 1, 'onboarding': em_onboarding(request, usuario),
    })


@perfil_obrigatorio
def perfil_objetivo(request, usuario):
    if proximo_passo(usuario) == 'perfil_dados':
        return redirect('perfil_dados')
    medida = usuario.medida_atual()
    if medida is None and SESSAO_PESO not in request.session:
        messages.error(request, 'Informe seu peso atual para continuar.')
        return redirect('perfil_dados')

    form = ObjetivoForm(request.POST or None, instance=usuario,
                        initial={'objetivo': medida.objetivo_momento if medida else None})
    if request.method == 'POST' and form.is_valid():
        objetivo = form.cleaned_data['objetivo']
        with transaction.atomic():
            form.save()
            if medida:
                registrar_medida(usuario, objetivo=objetivo)
            else:
                HistoricoMedida.objects.create(
                    usuario=usuario, data_registro=timezone.now(),
                    peso_kg=request.session[SESSAO_PESO], objetivo_momento=objetivo,
                )
                del request.session[SESSAO_PESO]
        return depois_de_salvar(request, usuario, 'perfil_esportes')
    return render(request, 'contas/perfil_objetivo.html', {
        'form': form, 'usuario': usuario, 'passo': 2, 'onboarding': em_onboarding(request, usuario),
    })


@perfil_obrigatorio
def perfil_esportes(request, usuario):
    passo = proximo_passo(usuario)
    if passo in ('perfil_dados', 'perfil_objetivo'):
        return redirect(passo)
    onboarding = em_onboarding(request, usuario)
    form = EsportesForm(request.POST or None, usuario=usuario)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            usuario.esportes.all().delete()
            EsporteUsuario.objects.bulk_create([
                EsporteUsuario(
                    usuario=usuario, esporte=esporte, frequencia_semanal=freq, intensidade=intensidade,
                    duracao_minutos=minutos, dias_fixos=dias_fixos,
                )
                for esporte, freq, intensidade, minutos, dias_fixos in form.escolhidos()
            ])
            salvar_meta(usuario)
            confirmar_rotina(usuario)
        if not onboarding:
            messages.success(request, 'Esportes atualizados. Suas metas foram recalculadas.')
        return redirect('perfil_metas')
    return render(request, 'contas/perfil_esportes.html', {
        'form': form, 'usuario': usuario, 'passo': 3, 'onboarding': onboarding,
        'frequencias': FREQUENCIAS, 'intensidades': INTENSIDADES.items(),
        'duracoes': DURACOES, 'dias': DIAS, 'tem_dias_fixos': TEM_DIAS_FIXOS,
    })


@perfil_obrigatorio
def perfil_concluir(request, usuario):
    request.session.pop(SESSAO_ONBOARDING, None)
    if proximo_passo(usuario):
        return redirect(proximo_passo(usuario))
    messages.success(request, 'Tudo pronto! Suas metas ficam salvas aqui e mudam sempre que você atualizar o perfil.')
    return redirect('perfil_metas')


# =====================================================================
# Editar perfil (dados da conta), trocar senha e excluir conta
# =====================================================================

@perfil_obrigatorio
def conta(request, usuario):
    form = ContaForm(request.POST or None, instance=usuario)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Dados da conta salvos.')
        return redirect('conta')
    return render(request, 'contas/conta.html', {
        'form': form, 'usuario': usuario, 'medida': usuario.medida_atual(),
        'perfil_completo': proximo_passo(usuario) is None,
    })


class TrocarSenhaView(auth_views.PasswordChangeView):
    template_name = 'contas/trocar_senha.html'
    success_url = reverse_lazy('conta')

    def form_valid(self, form):
        resposta = super().form_valid(form)
        messages.success(self.request, 'Senha alterada.')
        return resposta

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for campo in form.fields.values():
            campo.widget.attrs['class'] = 'input'
        return form


@perfil_obrigatorio
def excluir_conta(request, usuario):
    form = ExcluirContaForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        conta = request.user
        logout(request)
        conta.delete()  # apaga o perfil e todos os registros em cascata
        messages.success(request, 'Sua conta e todos os seus dados foram excluídos.')
        return redirect('entrar')
    return render(request, 'contas/excluir_conta.html', {'form': form, 'usuario': usuario})


# =====================================================================
# Listagem de usuários (só para a equipe / staff)
# =====================================================================

POR_PAGINA = 10


@user_passes_test(lambda u: u.is_active and u.is_staff, login_url='entrar')
def usuarios(request):
    busca = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    lista = Usuario.objects.select_related('conta').annotate(
        tem_meta=Exists(MetaNutricional.objects.filter(usuario=OuterRef('pk'))),
    )
    if busca:
        filtro = Q(nome_completo__icontains=busca) | Q(apelido__icontains=busca) | Q(conta__email__icontains=busca)
        if so_digitos(busca):
            filtro |= Q(cpf__contains=so_digitos(busca))
        lista = lista.filter(filtro)
    if status == 'completo':
        lista = lista.filter(tem_meta=True)
    elif status == 'pendente':
        lista = lista.filter(tem_meta=False)

    pagina = Paginator(lista.order_by('nome_completo'), POR_PAGINA).get_page(request.GET.get('pagina'))
    filtros = request.GET.copy()
    filtros.pop('pagina', None)
    return render(request, 'contas/usuarios.html', {
        'pagina': pagina,
        'busca': busca,
        'status': status,
        'filtros': filtros.urlencode(),
        'eu': Usuario.objects.filter(conta=request.user).first(),
    })
