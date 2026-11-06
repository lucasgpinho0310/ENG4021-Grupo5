// Cronômetro de descanso do treino do dia: ao marcar uma série que tem intervalo,
// mostra a contagem regressiva no rodapé. O formulário funciona igual sem JavaScript.
(function () {
  var caixa = document.getElementById('descanso');
  var tempo = document.getElementById('descanso-tempo');
  var pular = document.getElementById('descanso-pular');
  var relogio = null;

  function mostrar(segundos) {
    tempo.textContent = Math.floor(segundos / 60) + ':' + String(segundos % 60).padStart(2, '0');
  }

  function parar() {
    clearInterval(relogio);
    caixa.hidden = true;
  }

  function comecar(segundos) {
    clearInterval(relogio);
    caixa.hidden = false;
    caixa.classList.remove('acabou');
    mostrar(segundos);
    relogio = setInterval(function () {
      segundos -= 1;
      if (segundos <= 0) {
        clearInterval(relogio);
        tempo.textContent = 'Bora!';
        caixa.classList.add('acabou');
        if (navigator.vibrate) navigator.vibrate(300);
        setTimeout(parar, 4000);
        return;
      }
      mostrar(segundos);
    }, 1000);
  }

  document.querySelectorAll('.check-serie[data-descanso]').forEach(function (check) {
    check.addEventListener('change', function () {
      if (check.checked) comecar(parseInt(check.dataset.descanso, 10));
    });
  });
  pular.addEventListener('click', parar);
})();
