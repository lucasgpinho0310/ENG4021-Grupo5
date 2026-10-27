from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import DiarioBemEstarForm, DorFormSet
from .models import DiarioBemEstar


def _dia_da_url(request):
    """Dia pedido em ?data=AAAA-MM-DD. Sem data, ou com data inválida ou futura, usa hoje."""
    hoje = timezone.localdate()
    try:
        dia = date.fromisoformat(request.GET.get("data", ""))
    except ValueError:
        return hoje
    return min(dia, hoje)


@login_required
def registro(request):
    """Registrar (ou corrigir) o bem-estar de um dia: humor, sono e dores."""
    hoje = timezone.localdate()
    dia = _dia_da_url(request)
    diario = (
        DiarioBemEstar.objects.filter(usuario=request.user, data_referencia=dia).first()
        or DiarioBemEstar(usuario=request.user, data_referencia=dia)
    )

    if request.method == "POST":
        form = DiarioBemEstarForm(request.POST, instance=diario)
        formset = DorFormSet(request.POST, instance=diario, prefix="dores")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                diario = form.save()
                formset.instance = diario
                formset.save()
            messages.success(request, "Registro salvo.")
            return redirect(f"{request.path}?data={dia.isoformat()}")
    else:
        form = DiarioBemEstarForm(instance=diario)
        formset = DorFormSet(instance=diario, prefix="dores")

    return render(request, "bem_estar/registro.html", {
        "form": form,
        "formset": formset,
        "dia": dia,
        "anterior": dia - timedelta(days=1),
        "proximo": dia + timedelta(days=1) if dia < hoje else None,
    })


@login_required
def historico(request):
    """Últimos 60 registros do usuário."""
    diarios = DiarioBemEstar.objects.filter(usuario=request.user).prefetch_related("dores")[:60]
    return render(request, "bem_estar/historico.html", {"diarios": diarios})