from django.shortcuts import render


def home(request):
    '''
    Home-page do BioForm.
    Renderiza o template home.html, com links para entrar/criar conta
    ou, se o usuário já entrou, para as páginas do site.
    '''
    return render(request, 'home.html')
