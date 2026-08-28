def somar(a, b):
    return a + b

def dividir(,a b):
    if b == 0:
       Return "Erro: divisão por zero!"
    return a / b

def subtrair(a, b)
    return a - b

def calculadora():
    print("=== Calculadora Simples ===")
    a = float(input("Digite o valor de a: "))
    b = float(input("Digite o valor de b: "))
    
    resultado = somar(a, b)
    print(f"Resultado da soma: {resultado}")

    resultado_divisao = dividir(a, b)
    print(f"Resultado da divisão: {resultado_divisao}")

    resultado_subtracao = subtrair(a, b)
    print(f"Resultado da subtração:{resultado_subtracao}")
if __name__ == "__main__":
    calculadora()
