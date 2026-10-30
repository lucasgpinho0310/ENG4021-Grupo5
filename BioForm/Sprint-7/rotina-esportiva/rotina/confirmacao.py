"""
Confirmação mensal da rotina: a cada 30 dias o app pergunta se a rotina esportiva continua a mesma.
"Sim" grava a data; "Ajustar" leva ao passo 3 do perfil, e salvar lá também conta como confirmação.
"""
from datetime import timedelta

from django.utils import timezone

DIAS_PARA_CONFIRMAR = 30


def precisa_confirmar(usuario, hoje=None):
    hoje = hoje or timezone.localdate()
    ultima = usuario.rotina_confirmada_em
    return ultima is None or hoje - ultima >= timedelta(days=DIAS_PARA_CONFIRMAR)


def confirmar_rotina(usuario, hoje=None):
    usuario.rotina_confirmada_em = hoje or timezone.localdate()
    usuario.save(update_fields=['rotina_confirmada_em'])


def proxima_confirmacao(usuario):
    if usuario.rotina_confirmada_em is None:
        return None
    return usuario.rotina_confirmada_em + timedelta(days=DIAS_PARA_CONFIRMAR)
