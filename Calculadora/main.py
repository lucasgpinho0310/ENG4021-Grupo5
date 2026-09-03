from Soma import somar
from Subtracao import subtrair
from Multiplicacao import multiplicar
from Divisao import dividir

print("--- CALCULADORA ---")
print("1 - Soma")
print("2 - Subtração")
print("3 - Multiplicação")
print("4 - Divisão")

operacao = input("Qual operação você deseja fazer? (1, 2, 3 ou 4): ").strip()

a = float(input("Digite o valor de a: "))
b = float(input("Digite o valor de b: "))

if operacao == '1' or operacao.lower() == 'soma':
    resultado = somar(a, b)
elif operacao == '2' or operacao.lower() in ['subtracao', 'subtração']:
    resultado = subtrair(a, b)
elif operacao == '3' or operacao.lower() in ['multiplicacao', 'multiplicação']:
    resultado = multiplicar(a, b)
elif operacao == '4' or operacao.lower() in ['divisao', 'divisão']:
    resultado = dividir(a, b)
else:
    resultado = "Operação inválida!"

print(f"Resultado: {resultado}")